"""Pre-fetch the bars scheduled deployments are about to be priced on.

Deployments are scheduled individually, so a dozen trading the same instrument
each reach the same conclusion at the same boundary — that the newest bar is
missing — and race to insert it. All but one lose on the primary key. Running
this once per boundary collapses that to a single fetch per instrument.

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

from quant.strategy.performance import live_lookback_bars
from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.db_repo import TradeRepo

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
    """Warms every instrument scheduled deployments will trade, all intervals."""

    def __init__(
        self,
        repo: TradeRepo,
        bar_services: PriceBarServiceFactory,
        *,
        lookback: int = DEFAULT_WARM_LOOKBACK,
        settle_s: float = DEFAULT_SETTLE_S,
    ) -> None:
        self._repo = repo
        self._bar_services = bar_services
        self._lookback = lookback
        self._settle_s = settle_s

    def run(self, *, now: datetime | None = None) -> WarmReport:
        """One warm pass over every scheduled instrument.

        Sweeping all intervals beats tracking which ones have deployments: an
        empty interval contributes no rows to the read, which is cheaper than
        keeping a subscription list correct across create, pause and reschedule.
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
        rows = self._repo.sp_get_scheduled_instruments()
        if not rows:
            logger.info("bar warm: no scheduled deployments — nothing to warm")
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

        # sync() folds duplicates itself, so the same instrument appearing once
        # per deployment costs one fetch.
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
