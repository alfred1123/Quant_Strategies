"""What to place, and how often to try — the policy layer above broker mechanics.

A :class:`~quant.trade.adapters.base.TradeAdapter` places the order it is
handed. Deciding that order from a signal and a live position is this
module's job, so a second broker cannot grow its own reading of ``+1`` on a
short position.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from quant.trade.adapters.base import TradeAdapter
from quant.trade.models.order import (
    IntendedAction,
    OrderFailureStage,
    OrderRejectReason,
    OrderRequest,
    OrderResult,
    OrderSide,
)

logger = logging.getLogger(__name__)

# Positions smaller than this are float noise, not real exposure — treat as flat.
_FLAT_EPS = 1e-9


def intended_action(signal: float, position_qty: float) -> IntendedAction:
    """Map ``(signal, signed_position)`` to an action.

    Handles long, flat, and short positions::

        signal  position   →  action
        ──────  ─────────  ─  ──────
         +1      0 (flat)  →  BUY
         +1     >0 (long)  →  HOLD          (already long)
         +1     <0 (short) →  CLOSE_SHORT   (cover before buying)
          0     >0 (long)  →  SELL           (flatten)
          0      0 (flat)  →  HOLD
          0     <0 (short) →  CLOSE_SHORT    (flatten)
         -1     >0 (long)  →  SELL
         -1      0 (flat)  →  OPEN_SHORT     (enter short)
         -1     <0 (short) →  HOLD           (already short)

    Positions within ``_FLAT_EPS`` of zero are treated as flat so float
    dust never triggers a flatten order the exchange would reject.
    """
    sig = int(round(signal))
    if abs(position_qty) <= _FLAT_EPS:
        position_qty = 0.0
    if sig > 0:
        if position_qty < 0:
            return IntendedAction.CLOSE_SHORT
        return IntendedAction.BUY if position_qty == 0 else IntendedAction.HOLD
    if sig == 0:
        if position_qty > 0:
            return IntendedAction.SELL
        if position_qty < 0:
            return IntendedAction.CLOSE_SHORT
        return IntendedAction.HOLD
    # sig < 0
    if position_qty > 0:
        return IntendedAction.SELL
    if position_qty == 0:
        return IntendedAction.OPEN_SHORT
    return IntendedAction.HOLD


def order_for(
    symbol: str, action: IntendedAction, qty: float, position_qty: float,
) -> OrderRequest | None:
    """At most one market order for *action*, or ``None`` when nothing is due.

    ``position_qty`` must be the same reading *action* was derived from:
    a flatten sells what is held, so sizing it from a second broker read
    could place an order that no longer matches the decision.
    """
    match action:
        case IntendedAction.HOLD:
            return None
        case IntendedAction.BUY:
            req = OrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY)
        case IntendedAction.OPEN_SHORT:
            req = OrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL)
        case IntendedAction.SELL:
            req = OrderRequest(symbol=symbol, qty=abs(position_qty), side=OrderSide.SELL)
        case IntendedAction.CLOSE_SHORT:
            req = OrderRequest(symbol=symbol, qty=abs(position_qty), side=OrderSide.BUY)
        case _:  # pragma: no cover — exhaustive per IntendedAction
            raise ValueError(f"unhandled intended action: {action!r}")
    return req if req.qty > 0 else None


@dataclass(frozen=True)
class ApplyAttempt:
    """One broker apply attempt — owns its own audit-column mapping."""

    action: IntendedAction
    position_qty: float
    result: OrderResult | None

    @property
    def buy_sell_cd(self) -> str:
        if self.action is IntendedAction.HOLD:
            return IntendedAction.HOLD.value
        side = self.action.order_side()
        if side is not None:
            return side.value
        return self.action.value

    @property
    def is_success_ind(self) -> str:
        if self.result is None:
            return "Y"
        return "Y" if self.result.success else "N"

    @property
    def vendor_order_id(self) -> str | None:
        return self.result.vendor_order_id if self.result else None

    def quantity(self, default_qty: float) -> float | None:
        if self.result is None:
            return None
        if self.result.filled_qty is not None:
            return self.result.filled_qty
        if self.result.requested_qty is not None:
            return self.result.requested_qty
        return default_qty


@dataclass(frozen=True)
class OrderRetryResult:
    """Outcome of the bounded retry executor — owns outcome semantics."""

    action: IntendedAction
    position_qty: float
    result: OrderResult | None
    attempts: tuple[ApplyAttempt, ...]
    max_attempts: int
    #: The alert title reads this. It is :meth:`pauses_deployment` for this
    #: stage and reason, so a cancel on a later attempt is the same pause
    #: as the tick. A place that does not need an operator is not one.
    permanent_failure: bool
    #: Set when the attempt failed. PLACE is the submit; CANCEL is a withdraw
    #: that did not succeed. None when no order failed.
    failure_stage: OrderFailureStage | None = None

    @staticmethod
    def pauses_deployment(
        failure_stage: OrderFailureStage | None,
        reason: OrderRejectReason | None,
    ) -> bool:
        """Whether the tick should stop on this outcome.

        A failed cancel may still be resting, whatever venue label it
        carried. A place pauses only when the reason itself needs an
        operator. The tick has the stage and the reason on the report, not
        this result, so both are arguments and there is one copy of the rule.
        """
        return failure_stage is OrderFailureStage.CANCEL or (
            reason is not None and reason.requires_operator_fix
        )

    @property
    def no_order_message(self) -> str:
        if self.action is IntendedAction.HOLD:
            return "no order needed (HOLD)"
        return "no order needed (qty resolved to 0)"

    @property
    def vendor_order_ids(self) -> list[str]:
        return [
            attempt.result.vendor_order_id
            for attempt in self.attempts
            if attempt.result and attempt.result.vendor_order_id
        ]


class OrderRetryPolicy:
    """Decide retry vs fail-fast from what the broker layer typed.

    A refusal arrives with an :class:`OrderRejectReason` set where it was
    decided — the gateway, the fill poller, the adapter — and any typed reject
    is final for this apply. Only a failure nobody could classify (a dropped
    connection, a timeout) is judged from its prose, and then only to tell a
    transient fault from an unknown one.
    """

    _TRANSIENT_MARKERS = ("unreachable", "rate", "timeout")

    def __init__(self, *, max_attempts: int, backoff_s: float) -> None:
        self._max_attempts = max_attempts
        self._backoff_s = backoff_s

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def backoff_s(self) -> float:
        return self._backoff_s

    def is_unconfirmed(self, result: OrderResult) -> bool:
        """Fill state unknown after bounded poll — candidate for cancel + retry."""
        msg = result.message.lower()
        return "fill unconfirmed" in msg or "requires manual reconciliation" in msg

    def is_retryable(self, result: OrderResult) -> bool:
        """Transient / ambiguous failures may be retried; a typed reject fails fast."""
        if result.success:
            return False
        if result.reason is not None:
            return False
        if self.is_unconfirmed(result):
            return True
        if result.vendor_order_id:
            return True
        msg = result.message.lower()
        return any(marker in msg for marker in self._TRANSIENT_MARKERS)


class OrderRetryExecutor:
    """Retry cancel-before-retry on ambiguous fills; fail fast on permanent errors.

    A cancel that returns failure is final. The call is not proof the order
    is gone: the book can still read flat while that order rests, and the
    next place is then a second order. The result keeps the cancel's typed
    reason when the adapter set one, and carries
    :attr:`OrderRejectReason.CANCEL_FAILED` only when it did not. The
    outcome's failure stage is CANCEL, and :meth:`OrderRetryResult.pauses_deployment`
    is what stops the tick: overwriting a typed reason with ``CANCEL_FAILED``
    would hide why the cancel was refused, and a reason such as
    ``KEY_REFUSED`` does not itself pause a place. ``permanent_failure`` is
    that method, so the alert title — it already reads the field — does not
    keep a second rule about how many attempts ran. The result message
    becomes the reason, and ``ApplyReport.message`` copies that field.
    The alert prints it through the existing formatter. The warning log
    still has the cancel's own message.

    The returned :class:`OrderRetryResult` carries everything callers need —
    they never reach into the nested policy.
    """

    def __init__(self, policy: OrderRetryPolicy) -> None:
        self._policy = policy

    def execute(
        self,
        adapter: TradeAdapter,
        vendor_symbol: str,
        signal: float,
        qty: float,
    ) -> OrderRetryResult:
        policy = self._policy
        attempts: list[ApplyAttempt] = []

        for attempt_num in range(1, policy.max_attempts + 1):
            position_qty = adapter.get_position_qty(vendor_symbol)
            action = intended_action(signal, position_qty)
            req = order_for(vendor_symbol, action, qty, position_qty)

            if req is None:
                attempts.append(ApplyAttempt(action, position_qty, None))
                return self._outcome(action, position_qty, None, attempts)

            result = adapter.place_order(req)
            attempts.append(ApplyAttempt(action, position_qty, result))

            if result is None or result.success:
                return self._outcome(action, position_qty, result, attempts)
            if not policy.is_retryable(result):
                return self._outcome(
                    action, position_qty, result, attempts, OrderFailureStage.PLACE,
                )
            if policy.is_unconfirmed(result) and result.vendor_order_id:
                cancel = adapter.cancel_order(result.vendor_order_id, vendor_symbol)
                if not cancel.success:
                    logger.warning(
                        "cancel failed vendor_order_id=%s symbol=%s — stopping retries: %s",
                        result.vendor_order_id,
                        vendor_symbol,
                        cancel.message,
                    )
                    reason = (
                        cancel.reason
                        if cancel.reason is not None
                        else OrderRejectReason.CANCEL_FAILED
                    )
                    result = replace(result, reason=reason, message=reason.value)
                    attempts[-1] = ApplyAttempt(action, position_qty, result)
                    return self._outcome(
                        action, position_qty, result, attempts, OrderFailureStage.CANCEL,
                    )
            if attempt_num >= policy.max_attempts:
                return self._outcome(
                    action, position_qty, result, attempts, OrderFailureStage.PLACE,
                )
            time.sleep(policy.backoff_s)

        raise AssertionError("unreachable — loop always returns")

    def _outcome(
        self,
        action: IntendedAction,
        position_qty: float,
        result: OrderResult | None,
        attempts: list[ApplyAttempt],
        failure_stage: OrderFailureStage | None = None,
    ) -> OrderRetryResult:
        permanent = OrderRetryResult.pauses_deployment(
            failure_stage, None if result is None else result.reason,
        )
        return OrderRetryResult(
            action=action,
            position_qty=position_qty,
            result=result,
            attempts=tuple(attempts),
            max_attempts=self._policy.max_attempts,
            permanent_failure=permanent,
            failure_stage=failure_stage,
        )
