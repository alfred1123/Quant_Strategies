"""HTTP boundary for the scheduler tick — the platform's own wakeup.

One endpoint, driven hourly by EventBridge through the scheduled-task Lambda,
that applies every deployment currently due. Deliberately *not* a schedule per
deployment: the database is then the only place a deployment's schedule lives,
so stopping one stops it trading, rather than leaving an AWS schedule that has
to be deleted separately and keeps firing if that delete ever fails.

Auth is the other reason this exists. The Lambda holds a service token, while
``/trade/deployments/{id}/apply`` requires a human — it acts on *your* account.
The tick resolves each deployment's owner from the database and applies as that
owner, so the platform can trade on a schedule without a human token and
without loosening the human-facing route.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from quant.api.auth.dependencies import require_user_or_service
from quant.trade.scheduler.sweep import ScheduleSweeper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _get_sweeper(request: Request) -> ScheduleSweeper:
    # Built at startup, not here: the tick counts apply attempts per deployment
    # in memory, and rebuilding it per request would reset that budget on every
    # wakeup — see quant.api.main.
    return request.app.state.schedule_sweeper


@router.post("/tick")
def run_schedule_tick(
    caller: str = Depends(require_user_or_service),
    sweeper: ScheduleSweeper = Depends(_get_sweeper),
) -> dict:
    """Apply every deployment due now, across all intervals.

    Always 200. A deployment that fails is reported in its own result and left
    due so the next wakeup retries it; reporting the pass as failed would make
    the Lambda log a whole sweep as broken because one deployment could not
    trade. A caller that needs to know looks at the outcome counts.
    """
    reports = sweeper.sweep()

    outcomes: dict[str, int] = {}
    for report in reports:
        for result in report.results:
            outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1

    due = sum(report.due for report in reports)
    logger.info(
        "scheduler/tick: %d interval(s), %d due, outcomes=%s, caller=%s",
        len(reports), due, outcomes or "{}", caller,
    )
    return {
        "intervals": len(reports),
        "due": due,
        "advanced": sum(report.advanced for report in reports),
        "outcomes": outcomes,
        "results": [
            {
                "tm_interval_id": report.tm_interval_id,
                "deployments": [
                    {
                        "deployment_id": str(result.deployment_id),
                        "outcome": result.outcome,
                        "attempt": result.attempt,
                        # The position the decision was made against. Nothing
                        # else in an unattended run reports it, and without it a
                        # HOLD reads the same as a tick that did nothing.
                        "position_qty": result.position_qty,
                        "error": result.error,
                    }
                    for result in report.results
                ],
            }
            for report in reports
        ],
    }
