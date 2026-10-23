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
    permanent_failure: bool

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
    decided — the gateway, the fill poller, the adapter. A typed reject is
    final for this apply, except :attr:`OrderRejectReason.UNCONFIRMED`: the
    fill is unknown, so the executor cancels that id and places again. Only a
    failure nobody could classify (a dropped connection, a timeout) is judged
    from its prose, and then only to tell a transient fault from an unknown
    one.
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
        """True when the fill poll typed :attr:`OrderRejectReason.UNCONFIRMED`.

        The executor cancels that vendor id before placing again. The sentence
        on the result is for the alert; this does not read it. Not an operator
        pause — :attr:`OrderRejectReason.requires_operator_fix` stays false.
        """
        return result.reason is OrderRejectReason.UNCONFIRMED

    def is_retryable(self, result: OrderResult) -> bool:
        """An unconfirmed fill is retried after cancel; every other typed reject fails fast."""
        if result.success:
            return False
        if self.is_unconfirmed(result):
            return True
        if result.reason is not None:
            return False
        if result.vendor_order_id:
            return True
        msg = result.message.lower()
        return any(marker in msg for marker in self._TRANSIENT_MARKERS)


class OrderRetryExecutor:
    """Retry cancel-before-retry on ambiguous fills; fail fast on permanent errors.

    A cancel that returns failure is final. The call is not proof the order
    is gone: the book can still read flat while that order rests, and the
    next place is then a second order. The result carries
    :attr:`OrderRejectReason.CANCEL_FAILED`, which pauses the deployment
    until someone reconciles it.

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
                return self._outcome(action, position_qty, result, attempts)
            if policy.is_unconfirmed(result) and result.vendor_order_id:
                cancel = adapter.cancel_order(result.vendor_order_id, vendor_symbol)
                if not cancel.success:
                    logger.warning(
                        "cancel failed vendor_order_id=%s symbol=%s — stopping retries: %s",
                        result.vendor_order_id,
                        vendor_symbol,
                        cancel.message,
                    )
                    result = replace(result, reason=OrderRejectReason.CANCEL_FAILED)
                    attempts[-1] = ApplyAttempt(action, position_qty, result)
                    return self._outcome(action, position_qty, result, attempts)
            if attempt_num >= policy.max_attempts:
                return self._outcome(action, position_qty, result, attempts)
            time.sleep(policy.backoff_s)

        raise AssertionError("unreachable — loop always returns")

    def _outcome(
        self,
        action: IntendedAction,
        position_qty: float,
        result: OrderResult | None,
        attempts: list[ApplyAttempt],
    ) -> OrderRetryResult:
        permanent = (
            result is not None
            and not result.success
            and len(attempts) == 1
            and not self._policy.is_retryable(result)
        )
        return OrderRetryResult(
            action=action,
            position_qty=position_qty,
            result=result,
            attempts=tuple(attempts),
            max_attempts=self._policy.max_attempts,
            permanent_failure=permanent,
        )
