"""One scheduler tick for a single interval — apply what is due, then advance.

The tick is the whole state machine and knows nothing about *how* it was
woken: EventBridge and the dev poller both land here. Each pass:

1. ``SP_GET_MISSED_DUE_DEPLOYMENTS`` — enabled, not paused, ``PENDING`` with
   ``SCHEDULED_TS <= NOW()``. Every row carries ``NEXT_SCHEDULED_TS``.
2. Apply each row.
3. Advance the cursor to ``NEXT_SCHEDULED_TS`` once the interval is closed —
   applied, or out of attempts.

A failure that still has attempts left writes nothing, so the row stays due
and the next pass retries it against the same ``SCHEDULED_TS``. Advancing
from the *stored* due time rather than from ``now()`` is what makes a backlog
drain one interval per pass instead of collapsing into a single apply.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from quant.schemas.apply import ApplyReport
from quant.trade.db_repo import TradeRepo

logger = logging.getLogger(__name__)

# ``TradeService.apply_deployment`` — injected so a tick can be tested, and
# driven, without building the whole trade stack.
ApplyDeployment = Callable[[UUID, UUID], ApplyReport]

DEFAULT_MAX_ATTEMPTS = 3


def _position_of(report) -> float | None:
    """``position_qty`` off an :class:`ApplyReport`, or None if unreadable.

    ``apply_deployment`` is injected, so the tick cannot assume the shape of
    what comes back. Anything that is not a number becomes None rather than
    travelling into the response as-is — a wrong position is worse than a
    missing one.
    """
    qty = getattr(report, "position_qty", None)
    try:
        return None if qty is None else float(qty)
    except (TypeError, ValueError):
        return None


class TickOutcome(StrEnum):
    """What one due deployment did on this pass."""

    APPLIED = "APPLIED"      # traded; cursor moved to the next interval
    RETRYING = "RETRYING"    # failed with budget left; still due
    ABANDONED = "ABANDONED"  # out of attempts; cursor moved on untraded
    STUCK = "STUCK"          # applied but the cursor did not move — see below


@dataclass(frozen=True)
class TickResult:
    deployment_id: UUID
    outcome: TickOutcome
    attempt: int
    error: str | None = None
    #: Signed broker position the apply decided against — negative short, 0.0
    #: flat, None when the apply never got far enough to read it. Carried up so
    #: an unattended tick reports the number behind its decision; the durable
    #: record is TRADE.EXECUTION_EVENT.POSITION_QTY, written per attempt.
    position_qty: float | None = None


@dataclass(frozen=True)
class TickReport:
    tm_interval_id: int
    results: list[TickResult]

    @property
    def due(self) -> int:
        return len(self.results)

    @property
    def advanced(self) -> int:
        """Rows whose cursor moved — a non-zero count means a backlog may remain."""
        return sum(
            1
            for r in self.results
            if r.outcome in (TickOutcome.APPLIED, TickOutcome.ABANDONED)
        )


class ScheduleTickRunner:
    """Applies the deployments due on one interval and advances their cursors.

    ``max_attempts`` is spent across passes, not within one: a failure leaves
    the row due so the *next* pass retries it. This is deliberately unlike
    ``OrderRetryExecutor``, which retries a broker order inside a single apply.
    Attempts are counted per ``(deployment, scheduled_ts)`` in memory, so a
    restart forgives earlier failures — acceptable because the budget only
    bounds how long a broken deployment stalls its own schedule.
    """

    def __init__(
        self,
        repo: TradeRepo,
        apply_deployment: ApplyDeployment,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._repo = repo
        self._apply = apply_deployment
        self._max_attempts = max_attempts
        # deployment_id -> (scheduled_ts it is failing against, attempts so far)
        self._attempts: dict[UUID, tuple[datetime, int]] = {}

    def run_interval(self, tm_interval_id: int) -> TickReport:
        """One pass over the deployments due on *tm_interval_id*.

        Repeat calls to drain a backlog; each pass advances a due deployment by
        exactly one interval. Read failures propagate — the caller owns the
        retry cadence.
        """
        rows = self._repo.sp_get_missed_due_deployments(tm_interval_id=tm_interval_id)
        results = [self._run_one(row) for row in rows]

        if results:
            logger.info(
                "tick interval=%s due=%d applied=%d",
                tm_interval_id,
                len(results),
                sum(1 for r in results if r.outcome is TickOutcome.APPLIED),
            )
        return TickReport(tm_interval_id=tm_interval_id, results=results)

    def _run_one(self, row: dict) -> TickResult:
        deployment_id = row["deployment_id"]
        scheduled_ts = row["scheduled_ts"]
        attempt = self._count_attempt(deployment_id, scheduled_ts)

        try:
            report = self._apply(row["app_user_id"], deployment_id)
        except Exception as exc:
            # No position: the apply raised, so it may never have reached the
            # broker read at all.
            return self._on_failure(row, attempt, exc)

        self._attempts.pop(deployment_id, None)
        return self._advance(
            row, TickOutcome.APPLIED, attempt, position_qty=_position_of(report)
        )

    def _on_failure(self, row: dict, attempt: int, exc: Exception) -> TickResult:
        deployment_id = row["deployment_id"]

        if attempt < self._max_attempts:
            logger.warning(
                "apply failed for deployment=%s attempt=%d/%d — staying due: %s",
                deployment_id,
                attempt,
                self._max_attempts,
                exc,
            )
            return TickResult(
                deployment_id=deployment_id,
                outcome=TickOutcome.RETRYING,
                attempt=attempt,
                error=str(exc),
            )

        logger.error(
            "apply failed for deployment=%s on the last of %d attempts — "
            "skipping this interval: %s",
            deployment_id,
            self._max_attempts,
            exc,
        )
        self._attempts.pop(deployment_id, None)
        return self._advance(row, TickOutcome.ABANDONED, attempt, error=str(exc))

    def _advance(
        self,
        row: dict,
        outcome: TickOutcome,
        attempt: int,
        *,
        error: str | None = None,
        position_qty: float | None = None,
    ) -> TickResult:
        """Move the cursor to NEXT_SCHEDULED_TS from the due row.

        The next due time comes off the cursor rather than being recomputed, so
        the schedule keeps its original phase no matter how late the tick ran.
        """
        deployment_id = row["deployment_id"]
        try:
            self._repo.sp_ins_deployment_schedule_status(
                # Stable per deployment — the schedule id *is* the deployment id.
                deployment_schedule_id=deployment_id,
                deployment_id=deployment_id,
                deployment_vid=row["deployment_vid"],
                status="PENDING",
                scheduled_ts=row["next_scheduled_ts"],
                user_id=row["user_id"],
            )
        except Exception as exc:
            # The deployment stays due, so the next pass applies it again. That
            # is a re-trade, not a replay: guarding it needs an in-flight lease
            # or an idempotent client order id, neither of which exists yet.
            logger.critical(
                "deployment=%s applied but its schedule did not advance — it "
                "will come due again and re-trade: %s",
                deployment_id,
                exc,
            )
            return TickResult(
                deployment_id=deployment_id,
                outcome=TickOutcome.STUCK,
                attempt=attempt,
                error=str(exc),
                position_qty=position_qty,
            )

        return TickResult(
            deployment_id=deployment_id,
            outcome=outcome,
            attempt=attempt,
            error=error,
            position_qty=position_qty,
        )

    def _count_attempt(self, deployment_id: UUID, scheduled_ts: datetime) -> int:
        """Attempts spent on this due time; a new due time starts over."""
        failing_ts, spent = self._attempts.get(deployment_id, (None, 0))
        attempt = spent + 1 if failing_ts == scheduled_ts else 1
        self._attempts[deployment_id] = (scheduled_ts, attempt)
        return attempt
