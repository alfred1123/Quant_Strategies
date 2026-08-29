"""Pre-fetch the bars somebody is going to want, before they ask for them.

Two kinds of caller want a series kept current: a scheduled deployment about to
be priced on it, and a user capturing history for a product they are still
deciding whether to trade. Both are answers to the same question — *which
instruments matter* — so both feed one loop here, and each contributes rows
through :class:`InstrumentSource` rather than being read directly.

That indirection is what lets this live in ``quant/market_data/`` at all. The
loop used to sit in ``quant/trade/`` because the only answer came from
``TRADE.DEPLOYMENT``; now that a subscription is an equally good answer, warming
is a market-data job with a trading input, and this module still knows nothing
about deployments.

**Nothing downstream depends on it.** Every apply still calls
``PriceBarService.ensure_fresh`` and still fails closed on an incomplete window,
so a warm pass that fails costs a redundant fetch later, never a bad trade. That
is what licenses the broad ``except`` here: one unreachable venue must not stop
the rest of the estate from being warmed.

Because it is an optimisation, *when* it runs decides whether it is worth
anything. A pass that lands after the applies have already fetched their own
bars has done nothing — see ``config/scheduler/price_bar_sync.yml`` (:00 fire,
10s settle) and ``trade_apply_tick`` at :05.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from quant.market_data.service import BarServiceFactory
from quant.strategy.performance import live_lookback_bars

logger = logging.getLogger(__name__)

#: Bars to warm per instrument. The warmer cannot know each deployment's
#: indicator windows without reading every strategy config, so it warms a fixed
#: span sized by the same rule the live path uses, for a window comfortably
#: above the common indicator set. Warming short is safe by construction:
#: ``ensure_fresh`` at apply time completes whatever the real window needs.
DEFAULT_WARM_LOOKBACK = live_lookback_bars(110)

#: Seconds to let the interval boundary settle before deciding which bar is the
#: newest closed one. The schedule fires *on* the boundary (`cron(0 …)`), so
#: the warm can land before `trade_apply_tick` at `:05`. Sleeping *before*
#: reading the clock clears two edges — see :meth:`BarWarmer.run`.
DEFAULT_SETTLE_S = 10.0


class InstrumentSource(Protocol):
    """Somewhere that says which bar series are worth keeping current.

    Rows are dicts carrying ``tm_interval_id``, ``internal_cusip`` and
    ``app_id`` — the ``MARKET_DATA.PRICE_BAR`` key minus the timestamp. Both
    implementations already read that shape out of their own procedure, which
    is why combining them is a concatenation rather than a translation.

    Duplicates across sources are expected and are not the source's problem: a
    deployment trading a series a user also subscribes to should cost one fetch,
    and :meth:`PriceBarService.sync` folds the repeats.
    """

    def instruments(self) -> list[dict]: ...


@dataclass(frozen=True)
class WarmResult:
    """Outcome for one ``(interval, venue)`` group.

    Grouped by venue as well as interval because ``failures`` is keyed by
    instrument, and one ``INTERNAL_CUSIP`` can trade on several — a single
    per-interval dict would let one venue's failure overwrite another's.
    """

    tm_interval_id: int
    app_id: int
    instruments: int
    inserted: int
    failures: dict[str, str]


@dataclass(frozen=True)
class WarmReport:
    results: list[WarmResult]

    @property
    def instruments(self) -> int:
        return sum(r.instruments for r in self.results)

    @property
    def inserted(self) -> int:
        return sum(r.inserted for r in self.results)

    @property
    def failed(self) -> int:
        return sum(len(r.failures) for r in self.results)


class BarWarmer:
    """Warms every series any source asks for, across all intervals and venues."""

    def __init__(
        self,
        sources: list[InstrumentSource],
        bar_services: BarServiceFactory,
        *,
        lookback: int = DEFAULT_WARM_LOOKBACK,
        settle_s: float = DEFAULT_SETTLE_S,
    ) -> None:
        self._sources = sources
        self._bar_services = bar_services
        self._lookback = lookback
        self._settle_s = settle_s

    def run(self, *, now: datetime | None = None) -> WarmReport:
        """One warm pass over every instrument any source named.

        Sweeping all intervals beats tracking which ones are in use: an empty
        interval contributes no rows to the read, which is cheaper than keeping
        a list correct across create, pause, reschedule and unsubscribe.
        """
        if now is None:
            # Firing on the boundary is what makes the warm useful, and it also
            # lands on two edges. Sleeping *before* reading the clock is what
            # settles both, because everything downstream derives the newest
            # closed bar from this one instant:
            #   - the exchange closed the candle a moment ago and may not serve
            #     it yet, which ensure_fresh treats as a hole and refuses;
            #   - delivery can be a shade early, and floor_to_period would then
            #     land a period back, targeting a bar already stored.
            time.sleep(self._settle_s)
            now = datetime.now(UTC)

        # One instant for the whole sweep: a slow pass must not compute a
        # different "newest bar" for the groups it reaches after a boundary.
        rows = [row for source in self._sources for row in source.instruments()]
        if not rows:
            logger.info("bar warm: nothing scheduled or subscribed — nothing to warm")
            return WarmReport(results=[])

        grouped: dict[tuple[int, int], list[str]] = defaultdict(list)
        for row in rows:
            key = (int(row["tm_interval_id"]), int(row["app_id"]))
            grouped[key].append(row["internal_cusip"])

        results = [
            self._warm_group(tm_interval_id, app_id, cusips, now=now)
            for (tm_interval_id, app_id), cusips in sorted(grouped.items())
        ]
        report = WarmReport(results=results)
        logger.info(
            "bar warm: %d instrument(s) across %d group(s), %d bar(s) inserted, %d failed",
            report.instruments, len(results), report.inserted, report.failed,
        )
        return report

    def _warm_group(
        self,
        tm_interval_id: int,
        app_id: int,
        cusips: list[str],
        *,
        now: datetime | None,
    ) -> WarmResult:
        """Warm one interval on one venue, absorbing whatever goes wrong."""
        try:
            service = self._bar_services.for_app(app_id)
        except Exception as exc:
            # An app_id with no market data venue cannot be warmed at all. The
            # apply path raises the same way and *there* it stops the trade;
            # here it only means these bars stay cold.
            logger.warning(
                "bar warm: no price bar service for app_id=%s interval=%s: %s",
                app_id, tm_interval_id, exc,
            )
            return WarmResult(
                tm_interval_id=tm_interval_id,
                app_id=app_id,
                instruments=len(set(cusips)),
                inserted=0,
                failures={cusip: str(exc) for cusip in set(cusips)},
            )

        # sync() folds duplicates itself, so an instrument named by several
        # deployments and a subscription still costs one fetch.
        outcome = service.sync(
            instruments=[(cusip, app_id) for cusip in cusips],
            tm_interval_id=tm_interval_id,
            lookback=self._lookback,
            now=now,
        )
        return WarmResult(
            tm_interval_id=tm_interval_id,
            app_id=app_id,
            instruments=outcome.instruments,
            inserted=outcome.inserted,
            failures=outcome.failures,
        )
