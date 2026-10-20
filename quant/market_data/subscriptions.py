"""Standing requests to keep a bar series warm, with no deployment behind them.

Capture used to be a side effect of trading: the warmer read
``TRADE.SP_GET_SCHEDULED_INSTRUMENTS``, so history for a product only began
accruing once a strategy was already deployed against it — after the decision
the history was supposed to inform. A subscription is the second answer to
*which instruments matter*, and it needs no credential, no strategy and no
quantity, because bars are public and ``PriceBarService`` already knows how to
fetch and store them.

Subscriptions are **platform-wide**, not per user. A bar is a shared fact, so
one row per series is the honest model: whoever subscribes captures for
everybody, and the list is visible to everybody. Disabling one therefore stops
the capture for all of them — accepted, and the reason the row and its version
history are not hidden behind an owner.

What is deliberately **not** here is any background crawler. ``BACKFILL_FROM_TS``
records how far back history is wanted; filling toward it stays an explicit call
that reports what it could not get.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from uuid import UUID

from quant.market_data.series_subscr import SeriesSubscrRepo
from quant.market_data.service import (
    MAX_BACKFILL_BARS,
    BackfillResult,
    BarServiceFactory,
)
from quant.schemas.market_data import BackfillPlan

logger = logging.getLogger(__name__)

_OPEN_ROW_UNIQUE_VIOLATION = "23505"


class SubscriptionError(ValueError):
    """The subscription cannot be honoured — the caller has to change it."""


def _bar_row(row: dict) -> dict:
    """A venue row from ``SERIES_SUBSCR``, named the way capture reads it."""
    return {
        "series_subscr_id": row["series_subscr_id"],
        "series_subscr_vid": row["series_subscr_vid"],
        "internal_cusip": row["internal_cusip"],
        "tm_interval_id": row["tm_interval_id"],
        "source_app_id": row["app_id"],
        "is_enabled_ind": row["is_enabled_ind"],
        "backfill_from_ts": row.get("backfill_from_ts"),
        "transact_from_ts": row["transact_from_ts"],
    }


class SubscriptionInstrumentSource:
    """The subscribed half of the warmer's instrument list."""

    def __init__(self, repo: SeriesSubscrRepo) -> None:
        self._repo = repo

    def instruments(self) -> list[dict]:
        return self._repo.sp_get_active_bar_subscriptions()


class BarSubscriptionService:
    """Subscribe, list with coverage, and fill history on request.

    The venue view of ``MARKET_DATA.SERIES_SUBSCR``: the rows with no metric.
    The procedures are :class:`SeriesSubscrRepo`'s; this class only chooses
    the venue rows and names their columns the way capture reads them.
    """

    def __init__(
        self,
        repo: SeriesSubscrRepo,
        instruments,
        bar_services: BarServiceFactory,
    ) -> None:
        self._repo = repo
        self._instruments = instruments
        self._bar_services = bar_services

    def subscribe(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        is_enabled_ind: str = "Y",
        backfill_from_ts: datetime | None = None,
        series_subscr_id: UUID | None = None,
    ) -> dict:
        """Create a subscription, or version an existing one.

        Validation happens here rather than at warm time. A series is only
        warmable if the venue resolves to an exchange this platform can read and
        the product maps to a symbol that exchange knows; leaving both to the
        warmer turns one immediate, fixable error into a silent failure repeated
        every tick, in a log nobody is watching.
        """
        self._reject_unwarmable(
            internal_cusip=internal_cusip, source_app_id=source_app_id
        )
        try:
            row = self._repo.sp_ins_series_subscr(
                series_subscr_id=series_subscr_id or uuid.uuid4(),
                internal_cusip=internal_cusip,
                app_id=source_app_id,
                app_metric_id=None,
                tm_interval_id=tm_interval_id,
                is_enabled_ind=is_enabled_ind,
                backfill_from_ts=backfill_from_ts,
            )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) != _OPEN_ROW_UNIQUE_VIOLATION:
                raise
            # The partial unique index caught a second open row for this series.
            # Reached by subscribing to something already being captured — and
            # since subscriptions are shared, that may be somebody else's row.
            raise SubscriptionError(
                f"{internal_cusip} on interval {tm_interval_id} from app "
                f"{source_app_id} is already being captured — edit that "
                f"subscription instead of creating a second one"
            ) from exc
        return _bar_row(row)

    def venue_rows(self) -> list[dict]:
        """Current venue rows, disabled ones included — the series with no metric."""
        return [
            _bar_row(row)
            for row in self._repo.sp_get_series_subscr()
            if row.get("app_metric_id") is None
        ]

    def list_subscriptions(self) -> list[dict]:
        """Every subscription, each with what has actually been captured.

        The question the page has to answer is not "am I subscribed" but "do I
        have enough continuous history to backtest this", so every row carries
        its coverage. Coverage is two index probes per row, not a scan.

        Each row also carries the **vendor symbol**, resolved the same way the
        fetcher resolves it. An internal CUSIP alone cannot be checked against
        anything: `btcusdt.crypto` on Bybit is `BTCUSDT`, and the ticker a venue
        actually prints is the one worth reading beside a venue name.
        """
        return [
            row | {
                "coverage": self._coverage(row),
                "vendor_symbol": self.vendor_symbol(
                    internal_cusip=row["internal_cusip"],
                    source_app_id=int(row["source_app_id"]),
                ),
            }
            for row in self.venue_rows()
        ]

    def vendor_symbol(self, *, internal_cusip: str, source_app_id: int) -> str | None:
        """What the venue calls this product, or ``None`` if it no longer maps.

        A cache lookup, not a query — the same `InstrumentCache` the fetcher
        uses, so the page cannot disagree with what gets requested. ``None``
        rather than an error: an xref withdrawn after subscribing breaks capture
        but must not blank the list that shows you why.
        """
        return self._instruments.resolve_internal_cusip(internal_cusip, source_app_id)

    def coverage(
        self, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> dict:
        """First bar, last bar and gap count for one series."""
        return self._coverage(
            {
                "internal_cusip": internal_cusip,
                "tm_interval_id": tm_interval_id,
                "source_app_id": source_app_id,
            }
        )

    def venue_depth(
        self, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> dict:
        """What the exchange will serve, and whether one fill could take it.

        The page asks this before offering a date, so the target it defaults to
        is the venue's own floor rather than a guess. ``bars_available`` is what
        makes the interval's cost visible: the same six years is ~2,200 daily
        bars and ~3.4 million 1-minute ones, and only one of those is a fill.
        """
        earliest, bars_available = self._bar_service(source_app_id).venue_depth(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        return {
            "earliest": earliest,
            "bars_available": bars_available,
            "max_backfill_bars": MAX_BACKFILL_BARS,
        }

    def plan_backfill(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        target: datetime,
    ) -> BackfillPlan:
        """The next pass toward ``target``, so deep history can be filled in stages.

        Separate from ``venue_depth`` because it costs no exchange call: depth
        asks the venue what it retains, this reads what is stored and does
        arithmetic, so the dialog can re-ask after every fill.
        """
        return self._bar_service(source_app_id).plan_backfill(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            target=target,
        )

    def backfill(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        start: datetime,
        end: datetime | None = None,
    ) -> BackfillResult:
        """Fill an explicit range, reporting whatever the venue would not serve.

        Depth is bounded by the exchange, not by us: how far ``fetch_ohlcv``
        reaches varies by venue and timeframe, and deep intraday history is
        often unavailable at any price. Subscribing today does not retroactively
        create history — it starts a series and lets you fill backward as far as
        the venue will go.
        """
        service = self._bar_service(source_app_id)
        return service.backfill(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=start,
            end=end,
        )

    def _coverage(self, row: dict) -> dict:
        """Stored bounds and hole count, or empty bounds when nothing is stored."""
        internal_cusip = row["internal_cusip"]
        tm_interval_id = int(row["tm_interval_id"])
        source_app_id = int(row["source_app_id"])
        try:
            service = self._bar_service(source_app_id)
            bounds = service.stored_bounds(
                internal_cusip=internal_cusip,
                tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
            )
        except Exception as exc:
            # A page listing ten series must still render when one venue has
            # gone away; the row says why instead of the request failing.
            logger.warning(
                "coverage unavailable for %s interval=%s app=%s: %s",
                internal_cusip, tm_interval_id, source_app_id, exc,
            )
            return {"first_bar": None, "last_bar": None, "gaps": None, "error": str(exc)}

        if bounds is None:
            return {"first_bar": None, "last_bar": None, "gaps": None, "error": None}

        first_bar, last_bar = bounds
        gaps = service.find_gaps(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=first_bar,
            end=last_bar,
        )
        return {
            "first_bar": first_bar,
            "last_bar": last_bar,
            "gaps": len(gaps),
            "error": None,
        }

    def _bar_service(self, source_app_id: int):
        try:
            return self._bar_services.for_app(source_app_id)
        except Exception as exc:
            raise SubscriptionError(
                f"app {source_app_id} is not an exchange this platform can read "
                f"bars from"
            ) from exc

    def _reject_unwarmable(self, *, internal_cusip: str, source_app_id: int) -> None:
        self._bar_service(source_app_id)
        vendor_symbol = self._instruments.resolve_internal_cusip(
            internal_cusip, source_app_id
        )
        if vendor_symbol is None:
            raise SubscriptionError(
                f"no INST.PRODUCT_XREF row maps {internal_cusip!r} to a symbol on "
                f"app {source_app_id} — the venue would be asked for a symbol it "
                f"does not know"
            )
