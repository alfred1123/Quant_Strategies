"""Poll the schedule on a timer — the local stand-in for EventBridge.

In prod a tick fires because AWS decided it was time: each interval owns an
EventBridge schedule that invokes a Lambda. A developer laptop has no such
timer, and WSL stops outright when the lid closes, so this loop supplies the
wakeups instead.

Missed wakeups are therefore the normal case here rather than a fault, and the
loop opens by draining whatever fell due while the process was down. Draining
is only the tick repeated: each pass advances a due deployment by exactly one
interval, so a three-day gap takes three passes and leaves a
``DEPLOYMENT_SCHEDULE_STATUS`` row per owed slot. That per-slot history is the
record of how much the downtime cost — collapsing the backlog into one apply
would reach the same position but erase it.

Every pass reads the *current* bars, so a catch-up apply trades today's signal
at today's price. It does not replay the missed period, and cannot: an order
placed now fills now. Repeated applies converge instead of stacking, because
``intended_side`` compares the signal against the live broker position and
returns ``HOLD`` once the position already matches.
"""

from __future__ import annotations

import asyncio
import logging

from quant.refdata.reader import RedisRefData
from quant.trade.scheduler.tick import ScheduleTickRunner, TickOutcome, TickReport

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_S = 60.0

#: Ceiling on startup drain passes. One pass per missed interval, so this bounds
#: how far back the loop will chase — 2000 minute-bars is ~33 hours, far longer
#: than any gap that matters, while still terminating if a pass keeps reporting
#: progress it is not really making.
DEFAULT_MAX_DRAIN_PASSES = 2000


class SchedulePoller:
    """Drives :class:`ScheduleTickRunner` on a timer, catching up on boot.

    Sweeps every interval in ``REFDATA.TM_INTERVAL`` per pass rather than
    tracking which ones have deployments: an interval with nothing due costs one
    read returning no rows, and that is cheaper than keeping a subscription list
    correct as deployments are created, paused and rescheduled.
    """

    def __init__(
        self,
        runner: ScheduleTickRunner,
        refdata: RedisRefData,
        *,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        max_drain_passes: int = DEFAULT_MAX_DRAIN_PASSES,
    ) -> None:
        self._runner = runner
        self._refdata = refdata
        self._poll_interval_s = poll_interval_s
        self._max_drain_passes = max_drain_passes
        self._running = False

    async def run(self) -> None:
        """Drain the backlog, then tick until :meth:`stop` or cancellation."""
        self._running = True
        logger.info(
            "schedule poller starting — drain, then every %ss", self._poll_interval_s
        )
        try:
            await self.drain()
            while self._running:
                await asyncio.sleep(self._poll_interval_s)
                if not self._running:
                    break
                await self.poll_once()
        except asyncio.CancelledError:
            logger.info("schedule poller cancelled")
            raise
        finally:
            self._running = False
            logger.info("schedule poller stopped")

    async def drain(self) -> int:
        """Apply everything already overdue, one interval per pass.

        Returns the number of cursor advances. Stops as soon as a pass moves
        nothing: a deployment that failed with attempts left is deliberately
        left due, so the steady loop retries it on its own cadence instead of
        burning its whole budget in a tight loop here.
        """
        advanced_total = 0
        for _ in range(self._max_drain_passes):
            reports = await self.poll_once()
            if self._has_stuck(reports):
                # Applied but the cursor would not move, so the row is still
                # due. Another pass would re-trade it within seconds; the
                # steady loop is slow enough to be survivable and the CRITICAL
                # from the tick is already on the record.
                logger.critical("drain aborted — a deployment applied without advancing")
                return advanced_total

            advanced = sum(r.advanced for r in reports)
            if not advanced:
                if advanced_total:
                    logger.info("drain complete — %d interval(s) caught up", advanced_total)
                return advanced_total
            advanced_total += advanced

        logger.warning(
            "drain hit its %d-pass ceiling with work still due — the steady loop "
            "will carry on from here",
            self._max_drain_passes,
        )
        return advanced_total

    async def poll_once(self) -> list[TickReport]:
        """One tick across every interval.

        A read that fails takes its interval down for this pass only: the loop
        outlives any single broken interval, and the row stays due so the next
        pass picks it up.
        """
        reports: list[TickReport] = []
        for interval_id in self._refdata.interval_ids():
            try:
                # run_interval blocks on HTTP and DB; keep it off the event loop
                # so an apply cannot stall the API sharing this process.
                reports.append(
                    await asyncio.to_thread(self._runner.run_interval, interval_id)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("tick failed for interval=%s — skipping this pass", interval_id)
        return reports

    def stop(self) -> None:
        """Ask :meth:`run` to finish after the pass in flight."""
        if self._running:
            logger.info("schedule poller stop requested")
            self._running = False

    @staticmethod
    def _has_stuck(reports: list[TickReport]) -> bool:
        return any(
            result.outcome is TickOutcome.STUCK
            for report in reports
            for result in report.results
        )
