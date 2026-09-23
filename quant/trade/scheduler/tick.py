"""One scheduler tick for a single interval — apply what is due, then advance.

The tick is the whole state machine and knows nothing about *how* it was
woken: EventBridge and the dev poller both land here. Each pass:

1. ``SP_GET_MISSED_DUE_DEPLOYMENTS`` — enabled, not paused, ``PENDING`` with
   ``SCHEDULED_TS <= NOW()``. Every row carries ``NEXT_SCHEDULED_TS``.
2. Apply each row, retrying a failed apply a few seconds later within the pass.
3. Advance the cursor to ``NEXT_SCHEDULED_TS`` once the interval is closed
   (applied). Exhausted retries auto-pause the deployment instead — it drops
   off the missed-due list until someone re-enables it.

Retries happen inside the pass, not on the next one: the next wakeup is an
hour away, and a signal from the bar that just closed goes stale while it
waits. A broker refusal no retry can clear (a qty under the venue's min lot,
say) pauses on the first attempt. Advancing from the *stored* due time rather
than from ``now()`` is what makes a backlog drain one interval per pass instead
of collapsing into a single apply.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import DeploymentStatus
from quant.trade.db_repo import TradeRepo
from quant.trade.models.order import OrderRejectReason

logger = logging.getLogger(__name__)

# ``TradeService.apply_deployment`` — injected so a tick can be tested, and
# driven, without building the whole trade stack.
ApplyDeployment = Callable[[UUID, UUID], ApplyReport]

DEFAULT_MAX_ATTEMPTS = 3
#: Long enough for a dropped connection or a venue blip to clear, short enough
#: that three attempts stay well inside the Lambda's 110 s HTTP timeout on top
#: of the order executor's own retries.
DEFAULT_RETRY_BACKOFF_S = 5.0


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


def _reject_reason_of(report) -> OrderRejectReason | None:
    """Typed reject reason off an :class:`ApplyReport`; None when unclassified.

    ``apply_deployment`` is injected, so the field may arrive as a bare string
    or not at all. Anything that is not a reason we know counts as unclassified
    and takes the ordinary retry budget.
    """
    try:
        return OrderRejectReason(getattr(report, "reject_reason", None))
    except ValueError:
        return None


def _reject_reason_of_exception(exc: Exception) -> OrderRejectReason | None:
    """Typed reason off a raised :class:`BrokerConnectionError`; None otherwise."""
    reason = getattr(exc, "reason", None)
    return reason if isinstance(reason, OrderRejectReason) else None


@dataclass(frozen=True)
class _OrderFailure:
    """A finished apply cycle whose order failed, as the tick reads it."""

    message: str
    reason: OrderRejectReason | None


def _failed_order(report) -> _OrderFailure | None:
    """The failure an apply came back with; ``None`` if the order did not fail.

    ``order_success is False`` is a finished cycle that rejected or never
    confirmed. ``None`` (HOLD / no order) and ``True`` (fill) are not failures.
    """
    if getattr(report, "order_success", None) is not False:
        return None
    return _OrderFailure(
        message=getattr(report, "message", None) or "order failed",
        reason=_reject_reason_of(report),
    )


class TickOutcome(StrEnum):
    """What one due deployment did on this pass."""

    APPLIED = "APPLIED"      # traded; cursor moved to the next interval
    PAUSED = "PAUSED"        # out of attempts; disabled so it drops off the due list
    ABANDONED = "ABANDONED"  # out of attempts; pause write failed, cursor moved on
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

    ``max_attempts`` is spent within one pass, ``retry_backoff_s`` apart, and a
    deployment still failing at the end is paused. This wraps the whole apply
    (connect, bars, signal, order), where ``OrderRetryExecutor`` retries only
    the broker order inside one. A reject carrying
    :attr:`OrderRejectReason.requires_operator_fix` pauses on the first
    attempt; nothing about a second one would be different.
    """

    def __init__(
        self,
        repo: TradeRepo,
        apply_deployment: ApplyDeployment,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
    ) -> None:
        self._repo = repo
        self._apply = apply_deployment
        self._max_attempts = max_attempts
        self._retry_backoff_s = retry_backoff_s

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
        for attempt in range(1, self._max_attempts + 1):
            try:
                report = self._apply(row["app_user_id"], deployment_id)
            except Exception as exc:
                # No position: the apply raised, so it may never have reached
                # the broker read at all. A broker error still names its reason
                # when the venue classified the refusal (e.g. the key admits
                # none of our egress IPs), and that pauses like a reject would.
                error, reason = str(exc), _reject_reason_of_exception(exc)
            else:
                failure = _failed_order(report)
                if failure is None:
                    return self._advance(
                        row, TickOutcome.APPLIED, attempt,
                        position_qty=_position_of(report),
                    )
                error, reason = failure.message, failure.reason

            if reason is not None and reason.requires_operator_fix:
                break
            if attempt < self._max_attempts:
                logger.warning(
                    "apply failed for deployment=%s attempt=%d/%d — retrying in %.0fs: %s",
                    deployment_id, attempt, self._max_attempts,
                    self._retry_backoff_s, error,
                )
                time.sleep(self._retry_backoff_s)

        return self._auto_pause(row, attempt, error)

    def _auto_pause(self, row: dict, attempt: int, error: str) -> TickResult:
        """Disable the deployment so the next tick does not keep firing it.

        ``write_deployment`` versions the row ``PAUSED`` + ``IS_ENABLED_IND='N'``.
        ``SP_INS_DEPLOYMENT`` then closes the schedule as ``SUCCESS``, which is
        why this path does not also advance to the next ``PENDING`` slot.
        Flattening the broker position is a different question (§6).
        """
        deployment_id = row["deployment_id"]
        try:
            self._repo.write_deployment(
                deployment_id=deployment_id,
                app_user_id=row["app_user_id"],
                strategy_id=row["strategy_id"],
                strategy_vid=row["strategy_vid"],
                api_credential_id=row["api_credential_id"],
                app_id=row["app_id"],
                internal_cusip=row["internal_cusip"],
                qty=row["qty"],
                is_paper_ind=row["is_paper_ind"],
                is_enabled_ind="N",
                deployment_status=DeploymentStatus.PAUSED,
                user_id=row["user_id"],
                schedule_tm_interval_id=row.get("schedule_tm_interval_id"),
            )
        except Exception as exc:
            logger.exception(
                "auto-pause failed for deployment=%s — advancing so the "
                "schedule is not wedged: %s",
                deployment_id,
                exc,
            )
            return self._advance(
                row,
                TickOutcome.ABANDONED,
                attempt,
                error=f"{error}; pause failed: {exc}",
            )

        logger.error(
            "auto-paused deployment=%s after %d failed applies: %s",
            deployment_id,
            attempt,
            error,
        )
        return TickResult(
            deployment_id=deployment_id,
            outcome=TickOutcome.PAUSED,
            attempt=attempt,
            error=error,
        )

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