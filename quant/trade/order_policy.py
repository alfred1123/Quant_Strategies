"""Live-apply retry classification and execution — policy layer above broker mechanics."""

from __future__ import annotations

import time
from dataclasses import dataclass

from quant.trade.adapters.base import TradeAdapter
from quant.trade.models.order import IntendedAction, OrderResult


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
    """Classify order failures and decide retry vs fail-fast."""

    _PERMANENT_MARKERS = (
        "permission denied",
        "10005",
        "10024",
        "regulatory",
        "insufficient funds",
        "invalid order",
        "not supported",
        "order rejected",
        "create_order returned no order id",
    )

    def __init__(self, *, max_attempts: int = 5, backoff_s: float = 2.0) -> None:
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
        """Transient / ambiguous failures may be retried; permanent ones fail fast."""
        if result.success:
            return False
        msg = result.message.lower()
        if any(marker in msg for marker in self._PERMANENT_MARKERS):
            return False
        if self.is_unconfirmed(result):
            return True
        if result.vendor_order_id and "rejected" not in msg:
            return True
        return "unreachable" in msg or "rate" in msg or "timeout" in msg


class OrderRetryExecutor:
    """Retry cancel-before-retry on ambiguous fills; fail fast on permanent errors.

    The returned :class:`OrderRetryResult` carries everything callers need —
    they never reach into the nested policy.
    """

    def __init__(self, policy: OrderRetryPolicy | None = None) -> None:
        self._policy = policy or OrderRetryPolicy()

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
            action = adapter.intended_side(signal, position_qty)

            if action is IntendedAction.HOLD:
                attempts.append(ApplyAttempt(action, position_qty, None))
                return self._outcome(action, position_qty, None, attempts)

            result = adapter.apply_signal(vendor_symbol, signal, qty)
            attempts.append(ApplyAttempt(action, position_qty, result))

            if result is None or result.success:
                return self._outcome(action, position_qty, result, attempts)
            if not policy.is_retryable(result):
                return self._outcome(action, position_qty, result, attempts)
            if policy.is_unconfirmed(result) and result.vendor_order_id:
                adapter.cancel_order(result.vendor_order_id, vendor_symbol)
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
