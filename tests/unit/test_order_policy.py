"""Unit tests for quant.trade.order_policy."""

from unittest.mock import MagicMock, patch

from quant.trade.models.order import IntendedAction, OrderResult, OrderSide
from quant.trade.order_policy import (
    ApplyAttempt,
    OrderRetryExecutor,
    OrderRetryPolicy,
)


def _result(message: str, *, success: bool = False, vendor_order_id: str | None = "1") -> OrderResult:
    return OrderResult(
        success=success,
        vendor_order_id=vendor_order_id,
        message=message,
        side=OrderSide.BUY,
        requested_qty=0.01,
    )


class TestOrderRetryPolicy:
    def setup_method(self) -> None:
        self.policy = OrderRetryPolicy()

    def test_unconfirmed_message(self):
        assert self.policy.is_unconfirmed(_result("fill unconfirmed after 8s"))

    def test_rejected_not_unconfirmed(self):
        assert not self.policy.is_unconfirmed(_result("order rejected status=rejected"))

    def test_success_not_retryable(self):
        assert not self.policy.is_retryable(_result("ok", success=True))

    def test_insufficient_funds_permanent(self):
        assert not self.policy.is_retryable(_result("insufficient funds: ..."))

    def test_permission_denied_permanent(self):
        assert not self.policy.is_retryable(_result("10005 permission denied"))

    def test_unconfirmed_retryable(self):
        assert self.policy.is_retryable(
            _result("fill unconfirmed after 8s — vendor_order_id=abc requires manual reconciliation")
        )

    def test_unreachable_retryable(self):
        assert self.policy.is_retryable(_result("broker unreachable: timeout"))

    def test_defaults(self):
        assert self.policy.max_attempts == 5
        assert self.policy.backoff_s == 2.0


class TestApplyAttempt:
    def test_hold_maps_to_hold_cd(self):
        attempt = ApplyAttempt(IntendedAction.HOLD, 0.0, None)
        assert attempt.buy_sell_cd == "HOLD"
        assert attempt.is_success_ind == "Y"
        assert attempt.quantity(0.01) is None

    def test_open_short_maps_to_sell(self):
        attempt = ApplyAttempt(IntendedAction.OPEN_SHORT, 0.0, _result("filled", success=True))
        assert attempt.buy_sell_cd == "SELL"

    def test_failed_attempt(self):
        attempt = ApplyAttempt(IntendedAction.BUY, 0.0, _result("insufficient funds"))
        assert attempt.is_success_ind == "N"
        assert attempt.quantity(0.01) == 0.01  # falls back to requested_qty
        assert attempt.vendor_order_id == "1"


def _adapter(apply_result: OrderResult | None, action: IntendedAction = IntendedAction.BUY) -> MagicMock:
    adapter = MagicMock()
    adapter.get_position_qty.return_value = 0.0
    adapter.intended_side.return_value = action
    adapter.apply_signal.return_value = apply_result
    return adapter


class TestOrderRetryExecutor:
    def test_hold_short_circuits(self):
        adapter = _adapter(None, action=IntendedAction.HOLD)
        outcome = OrderRetryExecutor().execute(adapter, "BTCUSDT", 0.0, 0.01)
        assert outcome.action is IntendedAction.HOLD
        assert outcome.result is None
        assert len(outcome.attempts) == 1
        assert "HOLD" in outcome.no_order_message
        adapter.apply_signal.assert_not_called()

    def test_success_returns_first_attempt(self):
        adapter = _adapter(_result("filled", success=True))
        outcome = OrderRetryExecutor().execute(adapter, "BTCUSDT", 1.0, 0.01)
        assert outcome.result is not None and outcome.result.success
        assert not outcome.permanent_failure
        assert len(outcome.attempts) == 1

    def test_permanent_failure_no_retry(self):
        adapter = _adapter(_result("insufficient funds"))
        outcome = OrderRetryExecutor().execute(adapter, "BTCUSDT", 1.0, 0.01)
        assert outcome.permanent_failure
        assert len(outcome.attempts) == 1
        adapter.cancel_order.assert_not_called()

    @patch("quant.trade.order_policy.time.sleep")
    def test_unconfirmed_cancels_and_retries_to_exhaustion(self, mock_sleep):
        adapter = _adapter(
            _result("fill unconfirmed after 8s requires manual reconciliation")
        )
        outcome = OrderRetryExecutor(OrderRetryPolicy(max_attempts=3)).execute(
            adapter, "BTCUSDT", 1.0, 0.01
        )
        assert not outcome.permanent_failure
        assert len(outcome.attempts) == 3
        assert outcome.max_attempts == 3
        assert adapter.cancel_order.call_count == 3
        assert outcome.vendor_order_ids == ["1", "1", "1"]
