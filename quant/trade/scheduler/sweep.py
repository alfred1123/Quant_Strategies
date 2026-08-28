"""One tick across every interval — the unit both schedulers drive.

:class:`~quant.trade.scheduler.tick.ScheduleTickRunner` applies the deployments
due on *one* interval. Something has to decide which intervals to visit, and
both drivers want the same answer: all of them.

Sweeping every interval in ``REFDATA.TM_INTERVAL`` beats subscribing to the
ones that have deployments. An interval with nothing due costs one indexed read
returning no rows, which is cheaper than keeping a subscription list correct as
deployments are created, paused and rescheduled. It is also what lets a single
hourly wakeup serve a DAILY strategy: the daily deployment is simply not due on
most passes, and surfaces on the one where its cursor has come up.

Prod drives this from EventBridge through
``POST /api/v1/scheduler/tick``; a laptop drives it from
:class:`~quant.trade.scheduler.poller.SchedulePoller`. Neither owns the sweep.
"""

from __future__ import annotations

import logging
import time

from quant.refdata.reader import RedisRefData
from quant.trade.scheduler.tick import ScheduleTickRunner, TickOutcome, TickReport

logger = logging.getLogger(__name__)

#: Seconds to wait before reading which deployments are due, for a caller that
#: fires *on* the interval boundary. Two edges sit there:
#:
#: - A cursor stands at exactly the boundary (22:00:00) and the tick asks for
#:   ``SCHEDULED_TS <= NOW()``. Delivery a few milliseconds early answers "not
#:   yet" and the deployment then waits a whole interval for the next wakeup.
#: - ``price_bar_sync`` takes the same boundary, and the apply wants the warm to
#:   have landed. Overlap is safe rather than fatal — the bar insert treats a
#:   unique violation as a concurrent write — but a warm bar spares the apply
#:   a fetch it would otherwise make itself.
#:
#: Zero for the dev poller, which wakes on its own cadence and has no boundary
#: to clear.
DEFAULT_SETTLE_S = 10.0


class ScheduleSweeper:
    """Runs one tick per interval, absorbing a failure in any single one."""

    def __init__(
        self,
        runner: ScheduleTickRunner,
        refdata: RedisRefData,
        *,
        settle_s: float = 0.0,
    ) -> None:
        self._runner = runner
        self._refdata = refdata
        self._settle_s = settle_s

    def sweep(self) -> list[TickReport]:
        """One pass over every interval.

        A read that fails takes its interval down for this pass only: the row
        stays due, so the next pass picks it up, and one broken interval must
        not stop the others from trading.
        """
        if self._settle_s:
            time.sleep(self._settle_s)

        reports: list[TickReport] = []
        for interval_id in self._refdata.interval_ids():
            try:
                reports.append(self._runner.run_interval(interval_id))
            except Exception:
                logger.exception(
                    "tick failed for interval=%s — skipping this pass", interval_id
                )
        return reports

    @staticmethod
    def has_stuck(reports: list[TickReport]) -> bool:
        """Whether any deployment applied without its cursor advancing.

        Worth interrupting a drain for: the row is still due, so another pass
        would re-trade it within seconds.
        """
        return any(
            result.outcome is TickOutcome.STUCK
            for report in reports
            for result in report.results
        )
