"""Keep ``MARKET_DATA.PRICE_BAR`` current and hand bars to the signal pipeline.

The database stores and returns bars; deciding *which* bars are needed, pulling
the missing ones from the exchange and persisting them is this module's job.

The governing rule on the trade path is **fail closed**: if the window a signal
needs cannot be completed, raise rather than let the caller compute a position
from a series with holes in it.

Maintenance is the deliberate exception. ``ensure_fresh`` repairs only the
lookback a signal needs, so an outage longer than that window leaves older bars
missing for good; ``backfill`` takes an explicit range and reports what it could
not fill instead of aborting, because there a hole is ordinary — pre-listing
history, or beyond what the exchange retains — and refusing would discard the
bars that *were* recoverable.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import pandas as pd

from quant.market_data.fetcher import BarFetcher
from quant.market_data.repo import PriceBarRepo
from quant.shared.db import ProcedureError
from quant.shared.intervals import as_utc, bar_starts, last_closed_bar

logger = logging.getLogger(__name__)

_UNIQUE_VIOLATION = "23505"

#: Fraction of the requested lookback a window must reach before a signal may be
#: computed on it. Not 1.0: the newest bar is what matters and the oldest edge of
#: a padded lookback is slack, so a recently listed instrument should not be
#: permanently untradeable. Not much lower either — the padding is roughly 3x the
#: indicator window, so falling far below it starves the indicator itself.
_MIN_WINDOW_COVERAGE = 0.8

#: Most bar boundaries one :meth:`PriceBarService.backfill` call may span.
#:
#: Backfill is synchronous and blocking, and its cost is set by the interval
#: rather than the calendar: the history Bybit retains for BTCUSDT is ~2,300
#: daily bars, ~56,000 hourly and ~3.4 million 1-minute. Storing runs one
#: ``SP_INS_PRICE_BAR`` round trip per bar, measured at ~200 bar/s against a
#: local database and slower against Aurora, so the ceiling is a *time* budget
#: in disguise — roughly 50s here and more in production, against the ~100s a
#: proxy allows before it abandons the request and the caller learns nothing.
#:
#: Set so a full daily history fits in one pass with room to spare, while the
#: intervals that genuinely cannot be filled this way are refused up front
#: rather than attempted and killed mid-write. Raising it does not make a
#: minute-scale fill work; that needs a background job with progress, which
#: this design deliberately does not have.
MAX_BACKFILL_BARS = 10_000


class StaleBarsError(RuntimeError):
    """The required bar window could not be completed — do not trade on it."""


class BackfillTooLargeError(ValueError):
    """The requested range spans more boundaries than one blocking call may fill."""


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a batch warm-up: what was stored, and what could not be."""

    instruments: int
    inserted: int
    failures: dict[str, str]


@dataclass(frozen=True)
class BackfillPlan:
    """The next pass toward ``target``, and how many more it would take.

    ``MAX_BACKFILL_BARS`` makes deep intraday history unreachable in one call,
    and the advice that replaced it — fill a nearer date and repeat — does not
    work, because every fill runs to the last closed bar. For an hourly series
    already holding a year, *no* start both reaches further back and stays
    under the ceiling: the nearer the start, the more of the range is bars
    already stored, and the span is counted either way.

    Working backwards fixes that. Each pass ends where coverage currently
    begins, so it spans only bars that are actually absent, and the next pass
    starts from the ground the last one gained. ``start``/``end`` are ``None``
    when the target is already reached — the caller has nothing to do.
    """

    start: datetime | None
    end: datetime | None
    bars: int
    passes_remaining: int
    target: datetime

    @property
    def is_complete(self) -> bool:
        return self.start is None


@dataclass(frozen=True)
class BackfillResult:
    """Outcome of a continuity repair over an explicit range.

    ``unfilled`` holds the boundaries the exchange could not supply. Usually
    empty or a leading run that predates the listing; a hole in the middle
    means the series is genuinely not continuous and cannot be made so from
    this source.
    """

    start: datetime
    end: datetime
    expected: int
    missing: int
    inserted: int
    unfilled: tuple[datetime, ...]

    @property
    def is_continuous(self) -> bool:
        """True when every boundary in the range is now stored."""
        return not self.unfilled

    @property
    def oldest_unfilled(self) -> datetime | None:
        return self.unfilled[0] if self.unfilled else None


class BarServiceFactory(Protocol):
    """Binds a ``REFDATA.APP`` id to the price bars that venue serves.

    Declared here rather than imported so that callers in this package can take
    the factory without depending on where it is built. It is assembled in
    ``quant/trade/bar_source.py``, because choosing a venue for an ``app_id``
    means reading the broker presets, and market data must not learn about
    brokers to fetch a public candle.
    """

    def for_app(self, app_id: int) -> PriceBarService: ...


class PriceBarService:
    """Freshness check, gap fill and range read for live signal computation."""

    def __init__(
        self,
        repo: PriceBarRepo,
        refdata,
        instruments,
        fetcher: BarFetcher,
    ) -> None:
        self._repo = repo
        self._refdata = refdata
        self._instruments = instruments
        self._fetcher = fetcher

    # ── population ───────────────────────────────────────────────────────

    def ensure_fresh(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        lookback: int,
        now: datetime | None = None,
    ) -> int:
        """Make sure the newest ``lookback`` closed bars are stored.

        Returns the number of bars inserted. Raises :class:`StaleBarsError` if
        the exchange cannot supply the newest closed bar or leaves a hole in
        the middle of the window.
        """
        if lookback < 1:
            raise ValueError(f"lookback must be at least 1, got {lookback}")

        period = self._refdata.get_interval_period(tm_interval_id)
        now = now or datetime.now(UTC)
        newest = last_closed_bar(now, period)
        window_start = newest - period * (lookback - 1)

        coverage = self._repo.get_coverage(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        stored_max = coverage["max_bar_timestamp"] if coverage else None
        if stored_max is not None and stored_max >= newest:
            logger.debug(
                "Bars fresh for %s interval=%s (newest stored %s)",
                internal_cusip, tm_interval_id, stored_max,
            )
            return 0

        missing = self.find_gaps(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=window_start,
            end=newest,
        )
        if not missing:
            return 0

        fetched = self._fetch(
            internal_cusip=internal_cusip,
            source_app_id=source_app_id,
            period=period,
            since=missing[0],
            until=newest,
        )
        self._reject_incomplete(
            internal_cusip=internal_cusip, missing=missing, fetched=fetched, newest=newest
        )

        inserted = self._store(
            missing, fetched,
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        logger.info(
            "Inserted %d bar(s) for %s interval=%s up to %s",
            inserted, internal_cusip, tm_interval_id, newest,
        )
        return inserted

    def sync(
        self,
        *,
        instruments: Iterable[tuple[str, int]],
        tm_interval_id: int,
        lookback: int,
        now: datetime | None = None,
    ) -> SyncResult:
        """Warm bars for a set of ``(internal_cusip, source_app_id)`` pairs.

        Deployments are scheduled individually, so a dozen of them trading the
        same instrument would otherwise each fetch and race to insert the same
        bar. Running this once per interval collapses that to one fetch per
        instrument — duplicates in ``instruments`` are folded here, since the
        caller derives the list from deployment rows.

        Best effort by design: one unreachable symbol must not stop the rest,
        and nothing downstream trusts this. Every apply still calls
        :meth:`ensure_fresh` and still fails closed on its own, so a failure
        here costs a redundant fetch later, never a bad trade.
        """
        seen: set[tuple[str, int]] = set()
        inserted = 0
        failures: dict[str, str] = {}

        for internal_cusip, source_app_id in instruments:
            if (internal_cusip, source_app_id) in seen:
                continue
            seen.add((internal_cusip, source_app_id))
            try:
                inserted += self.ensure_fresh(
                    internal_cusip=internal_cusip,
                    tm_interval_id=tm_interval_id,
                    source_app_id=source_app_id,
                    lookback=lookback,
                    now=now,
                )
            except Exception as exc:
                # Deliberately broad: this is a batch warmer, and the apply
                # path is where a bad instrument is allowed to stop the world.
                failures[internal_cusip] = str(exc)
                logger.warning(
                    "Bar sync failed for %s interval=%s: %s",
                    internal_cusip, tm_interval_id, exc, exc_info=True,
                )

        logger.info(
            "Bar sync interval=%s: %d instrument(s), %d bar(s) inserted, %d failed",
            tm_interval_id, len(seen), inserted, len(failures),
        )
        return SyncResult(instruments=len(seen), inserted=inserted, failures=failures)

    def backfill(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        start: datetime,
        end: datetime | None = None,
        now: datetime | None = None,
    ) -> BackfillResult:
        """Fill every hole in ``[start, end]``, whatever the live lookback is.

        ``ensure_fresh`` only ever repairs the window a signal needs, so an
        outage longer than that lookback leaves bars older than the window
        permanently missing — nothing revisits them. This does: the range is
        given explicitly, so history stays continuous rather than being a
        rolling window maintained as a side effect of trading.

        Deliberately **does not** fail closed. The trade path refuses to price
        a signal on holes because a wrong trade is worse than no trade; here a
        hole is ordinary — the range may predate the listing, or reach past
        what the exchange retains — and aborting would throw away the bars that
        *were* recoverable. What could not be filled is reported instead.
        """
        period = self._refdata.get_interval_period(tm_interval_id)
        start = as_utc(start)
        end = as_utc(end) if end is not None else None
        end = end or last_closed_bar(now or datetime.now(UTC), period)
        if start > end:
            raise ValueError(f"start {start} is after end {end}")

        # Counted by arithmetic, before find_gaps builds a list per boundary —
        # the refusal is pointless if reaching it is what exhausts memory.
        span = int((end - start) / period) + 1
        if span > MAX_BACKFILL_BARS:
            affordable = start + period * (MAX_BACKFILL_BARS - 1)
            raise BackfillTooLargeError(
                f"{start.date()} to {end.date()} is {span:,} bar(s) at this "
                f"interval, over the {MAX_BACKFILL_BARS:,} one fill may span. "
                f"Backfill is a single blocking request, so a range this size "
                f"would time out and store nothing. Fill to {affordable.date()} "
                f"first, or capture this series at a coarser interval"
            )

        missing = self.find_gaps(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=start,
            end=end,
        )
        expected = len(bar_starts(start, end, period))
        if not missing:
            logger.info(
                "Backfill %s interval=%s source=%s: already continuous over %d bar(s)",
                internal_cusip, tm_interval_id, source_app_id, expected,
            )
            return BackfillResult(
                start=start, end=end, expected=expected,
                missing=0, inserted=0, unfilled=(),
            )

        fetched = self._fetch(
            internal_cusip=internal_cusip,
            source_app_id=source_app_id,
            period=period,
            since=missing[0],
            until=end,
        )
        inserted = self._store(
            missing, fetched,
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        unfilled = tuple(ts for ts in missing if ts not in fetched)

        log = logger.warning if unfilled else logger.info
        log(
            "Backfill %s interval=%s source=%s: %d of %d hole(s) filled, %d unavailable",
            internal_cusip, tm_interval_id, source_app_id,
            inserted, len(missing), len(unfilled),
        )
        return BackfillResult(
            start=start, end=end, expected=expected,
            missing=len(missing), inserted=inserted, unfilled=unfilled,
        )

    def plan_backfill(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        target: datetime,
        now: datetime | None = None,
    ) -> BackfillPlan:
        """The next pass that moves this series toward ``target``.

        Two index probes and arithmetic — no exchange call, so a dialog may
        ask on every open and again after each fill.

        Always works backwards from the newest edge. A series with nothing
        stored anchors on the last closed bar rather than on ``target``, so
        the first pass yields bars a strategy can already use; anchoring at
        the target instead would walk forward from history nobody can trade
        on and leave the series worthless until the final pass.
        """
        period = self._refdata.get_interval_period(tm_interval_id)
        target = as_utc(target)
        last_closed = last_closed_bar(now or datetime.now(UTC), period)
        nothing_to_do = BackfillPlan(
            start=None, end=None, bars=0, passes_remaining=0, target=target,
        )
        if target > last_closed:
            return nothing_to_do

        bounds = self.stored_bounds(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        if bounds is None:
            end = last_closed
        else:
            first_bar, _ = bounds
            if first_bar <= target:
                return nothing_to_do
            # The bar before coverage begins: the pass spans only what is
            # absent, instead of re-counting bars already stored.
            end = first_bar - period

        start = max(target, end - period * (MAX_BACKFILL_BARS - 1))
        bars = int((end - start) / period) + 1
        outstanding = int((end - target) / period) + 1
        passes = -(-outstanding // MAX_BACKFILL_BARS)  # ceil, without float
        return BackfillPlan(
            start=start, end=end, bars=bars, passes_remaining=passes, target=target,
        )

    def stored_bounds(
        self, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> tuple[datetime, datetime] | None:
        """Oldest and newest stored bar, or ``None`` when nothing is stored.

        Two index probes. What "have I captured enough to backtest this?"
        starts with — :meth:`find_gaps` over these bounds finishes it, and
        together they are cheaper than counting rows.
        """
        coverage = self._repo.get_coverage(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        if coverage is None:
            return None
        return coverage["min_bar_timestamp"], coverage["max_bar_timestamp"]

    def venue_depth(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        now: datetime | None = None,
    ) -> tuple[datetime | None, int | None]:
        """``(earliest bar the venue serves, how many bars that is)``.

        The counterpart to :meth:`stored_bounds`, which answers what we hold.
        Together they say how much of the obtainable history is captured, and
        they are different questions: a target older than this is not a gap to
        be filled but history that does not exist to fetch.

        The count is what makes the interval's cost visible before anyone
        commits to a fill — the same six years is ~2,200 daily bars and ~3.4
        million 1-minute ones. Costs one network call, so it is asked on demand
        by the pages that offer a date, never per row while listing.
        """
        period = self._refdata.get_interval_period(tm_interval_id)
        earliest = self._fetcher.earliest_bar(
            vendor_symbol=self._vendor_symbol(internal_cusip, source_app_id),
            period=period,
        )
        if earliest is None:
            return None, None
        return earliest, int(((now or datetime.now(UTC)) - earliest) / period) + 1

    def find_gaps(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        start: datetime,
        end: datetime,
    ) -> list[datetime]:
        """Bar boundaries in ``[start, end]`` with no stored row, oldest first.

        Read-only — this is what "is the history continuous?" reduces to, and
        both the freshness gate and :meth:`backfill` ask it before fetching
        anything. The caller bounds the range: one entry per boundary, so a
        decade of minute bars is millions of them.
        """
        period = self._refdata.get_interval_period(tm_interval_id)
        expected = bar_starts(start, end, period)
        stored = {
            row["bar_timestamp"]
            for row in self._repo.get_bars(
                internal_cusip=internal_cusip,
                tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
                range_start=start,
                range_end=end,
            )
        }
        return [ts for ts in expected if ts not in stored]

    def _store(
        self,
        missing: list[datetime],
        fetched: dict[datetime, object],
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
    ) -> int:
        """Persist the fetched bars, oldest first.

        Order matters: a crash part-way through leaves ``MAX_BAR_TIMESTAMP``
        short of the target, so the next pass reconciles from where this one
        stopped rather than stepping over the hole.
        """
        inserted = 0
        for bar_timestamp in missing:
            bar = fetched.get(bar_timestamp)
            if bar is None:
                continue
            if self._insert(
                bar, internal_cusip=internal_cusip, tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
            ):
                inserted += 1
        return inserted

    def _insert(
        self, bar, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> bool:
        """Store one bar. ``False`` if another worker stored it first.

        Deployments sharing an instrument and interval are scheduled at the
        same boundary, so several can decide the same bar is missing before
        any of them writes. They race on the natural primary key and all but
        one lose. Swallowing that is only safe because ``SOURCE_APP_ID`` is
        part of the key: a conflict therefore means the same venue's same bar,
        so the winner's row is the row this call would have written. Were the
        key venue-blind, the same swallow would silently adopt another
        exchange's print.
        """
        try:
            self._repo.ins_bar(
                internal_cusip=internal_cusip,
                tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
                bar_timestamp=bar.bar_timestamp,
                open_px=bar.open_px,
                high_px=bar.high_px,
                low_px=bar.low_px,
                close_px=bar.close_px,
                volume=bar.volume,
            )
        except ProcedureError as exc:
            if exc.sqlstate != _UNIQUE_VIOLATION:
                raise
            logger.debug(
                "Bar %s for %s interval=%s already stored by a concurrent run",
                bar.bar_timestamp, internal_cusip, tm_interval_id,
            )
            return False
        return True

    def _fetch(
        self,
        *,
        internal_cusip: str,
        source_app_id: int,
        period: timedelta,
        since: datetime,
        until: datetime,
    ) -> dict[datetime, object]:
        bars = self._fetcher.fetch_bars(
            vendor_symbol=self._vendor_symbol(internal_cusip, source_app_id),
            period=period,
            since=since,
            until=until,
        )
        return {bar.bar_timestamp: bar for bar in bars}

    def _vendor_symbol(self, internal_cusip: str, source_app_id: int) -> str:
        """What this venue calls the instrument, or refuse to ask it anything."""
        vendor_symbol = self._instruments.resolve_internal_cusip(internal_cusip, source_app_id)
        if vendor_symbol is None:
            raise StaleBarsError(
                f"no INST.PRODUCT_XREF mapping for {internal_cusip!r} on app {source_app_id}"
            )
        return vendor_symbol

    @staticmethod
    def _reject_incomplete(
        *,
        internal_cusip: str,
        missing: list[datetime],
        fetched: dict[datetime, object],
        newest: datetime,
    ) -> None:
        """Fail closed on a hole; tolerate history that predates the listing."""
        unfilled = [ts for ts in missing if ts not in fetched]
        if not unfilled:
            return

        earliest_available = min(fetched) if fetched else None
        holes = [ts for ts in unfilled if earliest_available and ts > earliest_available]
        if holes or newest in unfilled:
            raise StaleBarsError(
                f"exchange did not return {len(unfilled)} bar(s) for {internal_cusip!r} "
                f"(oldest missing {unfilled[0]}, newest closed bar {newest}) — refusing "
                f"to compute a signal on an incomplete window"
            )
        logger.warning(
            "%s has no exchange history before %s — %d leading bar(s) unavailable",
            internal_cusip, earliest_available, len(unfilled),
        )

    # ── read ─────────────────────────────────────────────────────────────

    def load_window(
        self,
        internal_cusip: str,
        lookback: int,
        *,
        tm_interval_id: int,
        source_app_id: int,
        now: datetime | None = None,
    ) -> pd.DataFrame:
        """The newest ``lookback`` closed bars, fetching whatever is missing.

        The entry point for live signal computation: one call that leaves the
        window complete or raises. Positional ``(internal_cusip, lookback)``
        so the caller can bind the interval and app once and pass the rest
        per symbol.
        """
        self.ensure_fresh(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            lookback=lookback,
            now=now,
        )
        period = self._refdata.get_interval_period(tm_interval_id)
        newest = last_closed_bar(now or datetime.now(UTC), period)
        bars = self.read_bars(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=newest - period * (lookback - 1),
            end=newest,
        )

        # ensure_fresh tolerates bars older than the exchange's earliest — that
        # is listing history, not a gap. It stays tolerant because a short
        # window is only a problem for a *signal*, and this is where signals are
        # served: an indicator still computes on a fraction of its intended
        # lookback, quietly, on statistics the strategy was never fitted on.
        required = math.ceil(lookback * _MIN_WINDOW_COVERAGE)
        if len(bars) < required:
            raise StaleBarsError(
                f"only {len(bars)} of {lookback} bar(s) available for "
                f"{internal_cusip!r} on interval {tm_interval_id} (need at least "
                f"{required}) — too little history to compute a comparable signal"
            )
        return bars

    def read_bars(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Bars in ``[start, end]`` shaped the way the pipeline already reads them.

        Same columns as ``fetch_df`` / ``BacktestCache._payload_to_df`` produce,
        so indicator and performance math needs no branch on where bars came
        from: a UTC ``datetime`` index plus ``price``, ``factor`` and the
        ``Open``/``High``/``Low``/``Close``/``Volume`` set.

        One source per window. Venues sharing an ``internal_cusip`` are separate
        order books, so a series mixing them is not one any strategy was fitted
        on and would not reproduce on a re-read.
        """
        rows = self._repo.get_bars(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            range_start=start,
            range_end=end,
        )
        if not rows:
            return pd.DataFrame()

        close = [float(r["close_px"]) for r in rows]
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime([r["bar_timestamp"] for r in rows], utc=True),
                "price": close,
                "factor": close,
                "Open": [float(r["open_px"]) for r in rows],
                "High": [float(r["high_px"]) for r in rows],
                "Low": [float(r["low_px"]) for r in rows],
                "Close": close,
                "Volume": [float(r["volume"]) for r in rows],
            }
        )
        return df.set_index("datetime").sort_index()
