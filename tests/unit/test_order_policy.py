"""Unit tests for quant.trade.order_policy."""

from unittest.mock import MagicMock, patch

import pytest

from quant.trade.models.order import (
    IntendedAction,
    OrderRejectReason,
    OrderResult,
    OrderSide,
)
from quant.trade.order_policy import (
    ApplyAttempt,
    OrderRetryExecutor,
    OrderRetryPolicy,
    intended_action,
    order_for,
)


class TestIntendedAction:
    """``intended_action`` — covers long, flat, and short positions."""

    def test_long_signal_flat_position(self):
        assert intended_action(1.0, 0.0) == "BUY"

    def test_long_signal_existing_long(self):
        assert intended_action(1.0, 0.01) == "HOLD"

    def test_long_signal_existing_short(self):
        assert intended_action(1.0, -0.5) == "CLOSE_SHORT"

    def test_flat_signal_with_long(self):
        assert intended_action(0.0, 0.01) == "SELL"

    def test_flat_signal_no_position(self):
        assert intended_action(0.0, 0.0) == "HOLD"

    def test_flat_signal_with_short(self):
        assert intended_action(0.0, -0.5) == "CLOSE_SHORT"

    def test_sell_signal_with_long(self):
        assert intended_action(-1.0, 1.0) == "SELL"

    def test_sell_signal_flat(self):
        assert intended_action(-1.0, 0.0) == "OPEN_SHORT"

    def test_sell_signal_already_short(self):
        assert intended_action(-1.0, -0.5) == "HOLD"

    def test_returns_intended_action_enum(self):
        assert intended_action(1.0, 0.0) is IntendedAction.BUY

    def test_float_dust_position_treated_as_flat(self):
        assert intended_action(1.0, 1e-12) == "BUY"
        assert intended_action(0.0, -1e-12) == "HOLD"
        assert intended_action(-1.0, 1e-12) == "OPEN_SHORT"


class TestOrderFor:
    """``order_for`` sizes the one order an action calls for, or none."""

    def test_hold_is_no_order(self):
        assert order_for("BTCUSDT", IntendedAction.HOLD, 0.01, 0.0) is None

    def test_buy_opens_the_deployment_qty(self):
        req = order_for("BTCUSDT", IntendedAction.BUY, 0.01, 0.0)
        assert (req.side, req.qty) == (OrderSide.BUY, 0.01)

    def test_open_short_sells_the_deployment_qty(self):
        req = order_for("BTCUSDT", IntendedAction.OPEN_SHORT, 0.01, 0.0)
        assert (req.side, req.qty) == (OrderSide.SELL, 0.01)

    def test_sell_flattens_what_is_held(self):
        req = order_for("BTCUSDT", IntendedAction.SELL, 0.01, 0.03)
        assert (req.side, req.qty) == (OrderSide.SELL, 0.03)

    def test_close_short_buys_back_what_is_short(self):
        req = order_for("BTCUSDT", IntendedAction.CLOSE_SHORT, 0.01, -0.02)
        assert (req.side, req.qty) == (OrderSide.BUY, 0.02)

    def test_flattening_nothing_is_no_order(self):
        assert order_for("BTCUSDT", IntendedAction.SELL, 0.01, 0.0) is None

    def test_adapter_contract_has_no_decision_surface(self):
        """Placing is the adapter's; deciding is this module's."""
        from quant.trade.adapters.base import TradeAdapter

        for name in ("intended_side", "apply_signal", "execute_action"):
            assert not hasattr(TradeAdapter, name)


def _result(
    message: str,
    *,
    success: bool = False,
    vendor_order_id: str | None = "1",
    reason: OrderRejectReason | None = None,
) -> OrderResult:
    return OrderResult(
        success=success,
        vendor_order_id=vendor_order_id,
        message=message,
        reason=reason,
        side=OrderSide.BUY,
        requested_qty=0.01,
    )


#: The seeded CONFIG.SETTING budget — what live_apply builds from the snapshot.
_POLICY = OrderRetryPolicy(max_attempts=5, backoff_s=2.0)


class TestOrderRetryPolicy:
    def setup_method(self) -> None:
        self.policy = OrderRetryPolicy(max_attempts=5, backoff_s=2.0)

    def test_unconfirmed_message(self):
        assert self.policy.is_unconfirmed(_result("fill unconfirmed after 8s"))

    def test_rejected_not_unconfirmed(self):
        assert not self.policy.is_unconfirmed(_result("order rejected status=rejected"))

    def test_success_not_retryable(self):
        assert not self.policy.is_retryable(_result("ok", success=True))

    @pytest.mark.parametrize("reason", list(OrderRejectReason))
    def test_every_typed_reject_is_final_for_the_attempt(self, reason):
        assert not self.policy.is_retryable(_result("whatever the venue said", reason=reason))

    def test_the_policy_holds_no_copy_of_the_venue_codes(self):
        """Bybit 10005/10024 are classified in the gateway; the policy never greps them."""
        import inspect

        from quant.trade import order_policy

        src = inspect.getsource(order_policy)
        for marker in ("10005", "10024", "insufficient funds", "order rejected", "regulatory"):
            assert marker not in src, marker

    def test_prose_alone_cannot_make_a_failure_permanent(self):
        """An untyped 'insufficient funds' is just unknown — neither retried nor typed."""
        result = _result("insufficient funds: ...", vendor_order_id=None)
        assert result.reason is None
        assert not self.policy.is_retryable(result)

    def test_unconfirmed_retryable(self):
        assert self.policy.is_retryable(
            _result("fill unconfirmed after 8s — vendor_order_id=abc requires manual reconciliation")
        )

    def test_unreachable_retryable(self):
        assert self.policy.is_retryable(_result("broker unreachable: timeout"))

    def test_a_reject_needing_an_operator_is_not_retryable(self):
        """Classified at the source — the policy reads the reason, not the prose."""
        assert not self.policy.is_retryable(
            _result(
                "qty 0.0001 is below BTCUSDT min qty 0.001",
                reason=OrderRejectReason.SIZE_BELOW_MINIMUM,
            )
        )

    def test_an_unclassified_timeout_stays_retryable(self):
        assert self.policy.is_retryable(_result("fetch timeout"))

    def test_carries_the_configured_budget(self):
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
        attempt = ApplyAttempt(IntendedAction.BUY, 0.0, _result("insufficient funds", reason=OrderRejectReason.INSUFFICIENT_FUNDS))
        assert attempt.is_success_ind == "N"
        assert attempt.quantity(0.01) == 0.01  # falls back to requested_qty
        assert attempt.vendor_order_id == "1"


def _adapter(place_result: OrderResult | None, position_qty: float = 0.0) -> MagicMock:
    adapter = MagicMock()
    adapter.get_position_qty.return_value = position_qty
    adapter.place_order.return_value = place_result
    return adapter


class TestOrderRetryExecutor:
    def test_hold_short_circuits(self):
        adapter = _adapter(None)
        outcome = OrderRetryExecutor(_POLICY).execute(adapter, "BTCUSDT", 0.0, 0.01)
        assert outcome.action is IntendedAction.HOLD
        assert outcome.result is None
        assert len(outcome.attempts) == 1
        assert "HOLD" in outcome.no_order_message
        adapter.place_order.assert_not_called()

    def test_the_position_read_once_sizes_the_order(self):
        """One broker read drives both the decision and the flatten size."""
        adapter = _adapter(_result("filled", success=True), position_qty=0.03)
        outcome = OrderRetryExecutor(_POLICY).execute(adapter, "BTCUSDT", 0.0, 0.01)
        assert outcome.action is IntendedAction.SELL
        assert adapter.get_position_qty.call_count == 1
        req = adapter.place_order.call_args.args[0]
        assert (req.side, req.qty) == (OrderSide.SELL, 0.03)

    def test_success_returns_first_attempt(self):
        adapter = _adapter(_result("filled", success=True))
        outcome = OrderRetryExecutor(_POLICY).execute(adapter, "BTCUSDT", 1.0, 0.01)
        assert outcome.result is not None and outcome.result.success
        assert not outcome.permanent_failure
        assert len(outcome.attempts) == 1

    def test_permanent_failure_no_retry(self):
        adapter = _adapter(_result("insufficient funds", reason=OrderRejectReason.INSUFFICIENT_FUNDS))
        outcome = OrderRetryExecutor(_POLICY).execute(adapter, "BTCUSDT", 1.0, 0.01)
        assert outcome.permanent_failure
        assert len(outcome.attempts) == 1
        adapter.cancel_order.assert_not_called()

    def test_a_size_reject_is_submitted_once(self):
        adapter = _adapter(
            _result(
                "qty 0.0001 is below BTCUSDT min qty 0.001",
                vendor_order_id=None,
                reason=OrderRejectReason.SIZE_BELOW_MINIMUM,
            )
        )
        outcome = OrderRetryExecutor(_POLICY).execute(adapter, "BTCUSDT", 1.0, 0.0001)
        assert adapter.place_order.call_count == 1
        assert outcome.permanent_failure
        assert outcome.result is not None
        assert outcome.result.reason is OrderRejectReason.SIZE_BELOW_MINIMUM

    @patch("quant.trade.order_policy.time.sleep")
    def test_unconfirmed_cancels_and_retries_to_exhaustion(self, mock_sleep):
        adapter = _adapter(
            _result("fill unconfirmed after 8s requires manual reconciliation")
        )
        outcome = OrderRetryExecutor(OrderRetryPolicy(max_attempts=3, backoff_s=2.0)).execute(
            adapter, "BTCUSDT", 1.0, 0.01
        )
        assert not outcome.permanent_failure
        assert len(outcome.attempts) == 3
        assert outcome.max_attempts == 3
        assert adapter.cancel_order.call_count == 3
        assert outcome.vendor_order_ids == ["1", "1", "1"]

    @pytest.mark.parametrize("max_attempts", [1, 5])
    @pytest.mark.parametrize(
        "cancel_message",
        [
            "cancel_order failed: timeout",
            pytest.param("", id="empty-message"),
        ],
    )
    @patch("quant.trade.order_policy.time.sleep")
    def test_failed_cancel_with_a_flat_book_places_once(
        self, mock_sleep, cancel_message, max_attempts,
    ):
        """A cancel that returns failure is not proof the order is gone.

        The book still reads flat, so another place would be a second order
        on top of one that may still be open. One and five are the attempt
        budget's ends: five is where the ignored return was measured.
        """
        adapter = _adapter(
            _result("fill unconfirmed after 8s requires manual reconciliation"),
            position_qty=0.0,
        )
        adapter.cancel_order.return_value = OrderResult(
            success=False,
            vendor_order_id="1",
            message=cancel_message,
        )
        outcome = OrderRetryExecutor(
            OrderRetryPolicy(max_attempts=max_attempts, backoff_s=2.0),
        ).execute(adapter, "BTCUSDT", 1.0, 0.01)

        assert adapter.place_order.call_count == 1
        assert adapter.cancel_order.call_count == 1
        assert adapter.get_position_qty.call_count == 1
        assert adapter.get_position_qty.return_value == 0.0
        assert outcome.permanent_failure
        assert len(outcome.attempts) == 1
        assert outcome.result is not None
        assert outcome.result is outcome.attempts[0].result
        assert outcome.result.reason is OrderRejectReason.CANCEL_FAILED
        assert outcome.result.reason.requires_operator_fix
        assert outcome.result.vendor_order_id == "1"
        assert outcome.result.success is False
        mock_sleep.assert_not_called()

    @patch("quant.trade.order_policy.time.sleep")
    def test_a_successful_cancel_still_retries(self, mock_sleep):
        """Cancel succeeded, so the next attempt is the same retry as before."""
        adapter = _adapter(
            _result("fill unconfirmed after 8s requires manual reconciliation"),
            position_qty=0.0,
        )
        adapter.cancel_order.return_value = OrderResult(
            success=True,
            vendor_order_id="1",
            message="order canceled",
        )
        outcome = OrderRetryExecutor(
            OrderRetryPolicy(max_attempts=3, backoff_s=2.0),
        ).execute(adapter, "BTCUSDT", 1.0, 0.01)

        assert adapter.place_order.call_count == 3
        assert adapter.cancel_order.call_count == 3
        assert len(outcome.attempts) == 3
        assert not outcome.permanent_failure
        assert outcome.result is not None
        assert outcome.result.reason is None
        assert mock_sleep.call_count == 2

    def test_a_raising_cancel_does_not_place_again(self):
        """An exception is not a cancel result. It leaves before a second place.

        The ccxt adapter turns a broker refusal into ``success=False``. A raise
        is a broken adapter, and swallowing it would hide that.
        """
        adapter = _adapter(
            _result("fill unconfirmed after 8s requires manual reconciliation"),
            position_qty=0.0,
        )
        adapter.cancel_order.side_effect = RuntimeError("cancel transport died")

        with pytest.raises(RuntimeError, match="cancel transport died"):
            OrderRetryExecutor(_POLICY).execute(adapter, "BTCUSDT", 1.0, 0.01)

        assert adapter.place_order.call_count == 1
        assert adapter.cancel_order.call_count == 1
        assert adapter.get_position_qty.call_count == 1
