"""Unit tests for :mod:`quant.trade.brokers.ccxt.confirm`."""

from unittest.mock import MagicMock, patch

import ccxt
import pytest

from quant.trade.brokers.ccxt.config import CCXT_PRESETS
from quant.trade.brokers.ccxt.confirm import (
    _extract_fee,
    _parse_terminal,
    confirm_market_order,
)
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import (
    BrokerAuthError,
    BrokerConnectionError,
    OrderNotFoundError,
)
from quant.trade.models.order import (
    OrderRejectReason,
    OrderRequest,
    OrderResult,
    OrderSide,
)
from quant.trade.order_policy import OrderRetryExecutor


class TestExtractFee:
    def test_dict_fee(self):
        assert _extract_fee({"fee": {"cost": 0.25, "currency": "USDT"}}) == (0.25, "USDT")

    def test_base_coin_fee_keeps_its_currency(self):
        assert _extract_fee({"fee": {"cost": 0.001, "currency": " BTC "}}) == (0.001, "BTC")

    def test_none_cost(self):
        assert _extract_fee({"fee": {"cost": None}}) == (None, None)

    def test_no_fee_key(self):
        assert _extract_fee({}) == (None, None)

    def test_non_dict_fee(self):
        assert _extract_fee({"fee": 0.1}) == (None, None)


class TestParseTerminal:
    def test_closed_order_is_terminal_success(self):
        order = {
            "id": "o1",
            "status": "closed",
            "filled": 0.01,
            "average": 64000.0,
            "fee": {"cost": 0.25, "currency": "USDT"},
        }
        result = _parse_terminal(order, vendor_order_id="o1")
        assert result is not None
        assert result.success is True
        assert result.filled_qty == 0.01
        assert result.avg_price == 64000.0
        assert result.fee == 0.25
        assert result.fee_ccy == "USDT"

    def test_partial_fill_on_cancel_is_success(self):
        order = {"id": "o2", "status": "canceled", "filled": 0.005, "average": 63000.0}
        result = _parse_terminal(order, vendor_order_id="o2")
        assert result is not None
        assert result.success is True
        assert result.filled_qty == 0.005

    def test_zero_fill_cancel_is_failure(self):
        order = {"id": "o3", "status": "canceled", "filled": 0}
        result = _parse_terminal(order, vendor_order_id="o3")
        assert result is not None
        assert result.success is False
        assert "rejected" in result.message

    def test_rejected_is_failure(self):
        order = {"id": "o4", "status": "rejected", "filled": 0}
        result = _parse_terminal(order, vendor_order_id="o4")
        assert result is not None
        assert result.success is False
        assert result.reason is OrderRejectReason.VENUE_REJECTED

    def test_open_order_returns_none(self):
        order = {"id": "o5", "status": "open", "filled": 0}
        assert _parse_terminal(order, vendor_order_id="o5") is None

    def test_empty_status_returns_none(self):
        order = {"id": "o6", "status": "", "filled": 0}
        assert _parse_terminal(order, vendor_order_id="o6") is None

    def test_expired_zero_fill_is_failure(self):
        order = {"id": "o7", "status": "expired", "filled": 0}
        result = _parse_terminal(order, vendor_order_id="o7")
        assert result is not None
        assert result.success is False

    def test_expired_with_fill_is_success(self):
        order = {"id": "o8", "status": "expired", "filled": 0.01, "average": 65000.0}
        result = _parse_terminal(order, vendor_order_id="o8")
        assert result is not None
        assert result.success is True


class TestConfirmMarketOrder:
    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_immediate_fill(self, mock_sleep):
        gw = MagicMock()
        gw.fetch_order.return_value = {
            "id": "abc", "status": "closed", "filled": 0.01,
            "average": 64000.0, "fee": {"cost": 0.256, "currency": "BTC"},
        }
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is True
        assert result.filled_qty == 0.01
        assert result.avg_price == 64000.0
        assert result.fee == 0.256
        assert result.fee_ccy == "BTC"
        assert result.side == OrderSide.BUY
        assert result.requested_qty == 0.01
        mock_sleep.assert_called_once()

    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_fill_after_retry(self, mock_sleep):
        gw = MagicMock()
        gw.fetch_order.side_effect = [
            {"id": "abc", "status": "open", "filled": 0},
            {"id": "abc", "status": "closed", "filled": 0.01, "average": 65000.0},
        ]
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.SELL)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is True
        assert result.side == OrderSide.SELL
        assert mock_sleep.call_count == 2

    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_timeout_returns_unconfirmed(self, mock_sleep):
        gw = MagicMock()
        gw.fetch_order.return_value = {"id": "abc", "status": "open", "filled": 0}
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is False
        assert "unconfirmed" in result.message
        assert result.raw_status == "open"
        assert result.side == OrderSide.BUY
        assert result.requested_qty == 0.01

    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_order_not_found_retries(self, mock_sleep):
        gw = MagicMock()
        gw.fetch_order.side_effect = [
            OrderNotFoundError("order not found: xxx"),
            {"id": "abc", "status": "closed", "filled": 0.01, "average": 64000.0},
        ]
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is True

    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_non_retryable_error_returns_failure(self, mock_sleep):
        gw = MagicMock()
        exc = BrokerConnectionError(
            "auth failed", reason=OrderRejectReason.KEY_REFUSED,
        )
        gw.fetch_order.side_effect = exc
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="ord-confirm-abc")

        assert result.success is False
        assert "auth failed" in result.message
        assert result.reason is exc.reason
        assert result.vendor_order_id == "ord-confirm-abc"

    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_untyped_fetch_error_keeps_a_missing_reason(self, mock_sleep):
        gw = MagicMock()
        exc = BrokerConnectionError("")
        assert exc.reason is None
        gw.fetch_order.side_effect = exc
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="ord-untyped-9")

        assert result.success is False
        assert result.reason is None
        assert result.vendor_order_id == "ord-untyped-9"
        assert "fill unconfirmed" in result.message
        assert result.message != str(exc)


class _ConfirmingAdapter:
    """One place goes through the real confirm path and records broker calls."""

    def __init__(self, gateway: MagicMock, vendor_order_id: str) -> None:
        self._gateway = gateway
        self._vendor_order_id = vendor_order_id
        self.calls: list[tuple[str, str | None]] = []

    def get_position_qty(self, symbol: str) -> float:
        return 0.0

    def place_order(self, req: OrderRequest) -> OrderResult:
        self.calls.append(("place_order", self._vendor_order_id))
        return confirm_market_order(
            self._gateway, req=req, vendor_order_id=self._vendor_order_id,
        )

    def cancel_order(
        self, vendor_order_id: str, vendor_symbol: str | None = None,
    ) -> OrderResult:
        self.calls.append(("cancel_order", vendor_order_id))
        return OrderResult(
            success=True, vendor_order_id=vendor_order_id, message="order canceled",
        )


def _assert_no_second_place_without_that_cancel(
    calls: list[tuple[str, str | None]],
    vendor_order_id: str,
    actual_reason: OrderRejectReason | None,
    actual_id: str | None,
) -> None:
    """A second ``place_order`` is legal only after ``cancel_order`` of this id."""
    cancelled = False
    seen_place = False
    naked: list[int] = []
    for index, (name, oid) in enumerate(calls):
        if name == "cancel_order" and oid == vendor_order_id:
            cancelled = True
        elif name == "place_order":
            if seen_place and not cancelled:
                naked.append(index)
            seen_place = True
            cancelled = False
    assert (
        vendor_order_id != "1"
        and actual_reason is None
        and actual_id == vendor_order_id
        and seen_place
        and not naked
    ), (
        f"reason={actual_reason!r} id={actual_id!r} naked={naked!r} calls={calls!r}"
    )


def _assert_kept_reason_and_did_not_replace(
    calls: list[tuple[str, str | None]],
    vendor_order_id: str,
    actual_reason: OrderRejectReason | None,
    expected_reason: OrderRejectReason,
) -> None:
    """Typed confirm failure keeps ``expected_reason`` and does not place again.

    A second ``place_order`` is only legal after ``cancel_order`` for the same
    id. These failures stop instead, so that second place never happens.
    """
    places = [i for i, (name, _) in enumerate(calls) if name == "place_order"]
    cancels = [i for i, (name, oid) in enumerate(calls) if name == "cancel_order"]
    replaced_without_cancel = [
        second for second in places[1:]
        if not any(index < second for index in cancels)
    ]
    assert (
        vendor_order_id != "1"
        and actual_reason is expected_reason
        and places == [0]
        and not replaced_without_cancel
        and all(calls[index][1] == vendor_order_id for index in cancels)
    ), (
        f"reason={actual_reason!r} expected={expected_reason!r} calls={calls!r}"
    )


class TestConfirmFailureDoesNotReplace:
    @pytest.mark.parametrize(
        ("exc", "vendor_order_id"),
        [
            (
                BrokerConnectionError(
                    "fetch_order failed: ExchangeNotAvailable",
                    reason=OrderRejectReason.REGION_RESTRICTED,
                ),
                "ord-conn-8588c162",
            ),
            (
                BrokerAuthError(
                    "authentication failed during fetch_order: Invalid Api-Key",
                    reason=OrderRejectReason.KEY_REFUSED,
                ),
                "ord-auth-8588c162",
            ),
        ],
    )
    def test_fetch_error_keeps_gateway_reason_and_does_not_replace(
        self, exc: BrokerConnectionError, vendor_order_id: str,
    ):
        gw = MagicMock()
        gw.fetch_order.side_effect = exc
        adapter = _ConfirmingAdapter(gw, vendor_order_id)
        with (
            patch("quant.trade.brokers.ccxt.confirm.time.sleep"),
            patch("quant.trade.order_policy.time.sleep"),
        ):
            outcome = OrderRetryExecutor().execute(adapter, "BTCUSDT", 1.0, 0.01)

        assert outcome.result is not None
        assert outcome.result.vendor_order_id == vendor_order_id
        assert exc.reason is not None
        assert exc.reason.value not in outcome.result.message
        _assert_kept_reason_and_did_not_replace(
            adapter.calls, vendor_order_id, outcome.result.reason, exc.reason,
        )

    def test_fetched_venue_reject_stops_before_a_second_place(self):
        vendor_order_id = "ord-venue-8588c162"
        gw = MagicMock()
        gw.fetch_order.return_value = {
            "id": vendor_order_id, "status": "rejected", "filled": 0,
        }
        adapter = _ConfirmingAdapter(gw, vendor_order_id)
        with (
            patch("quant.trade.brokers.ccxt.confirm.time.sleep"),
            patch("quant.trade.order_policy.time.sleep"),
        ):
            outcome = OrderRetryExecutor().execute(adapter, "BTCUSDT", 1.0, 0.01)

        assert outcome.result is not None
        assert outcome.result.vendor_order_id == vendor_order_id
        _assert_kept_reason_and_did_not_replace(
            adapter.calls,
            vendor_order_id,
            outcome.result.reason,
            OrderRejectReason.VENUE_REJECTED,
        )

    def test_fetch_timeout_does_not_replace_without_cancel(self):
        """An untyped ccxt timeout after an id exists must not place again naked."""
        vendor_order_id = "ord-timeout-8588c162"
        exchange = MagicMock()
        exchange.fetch_order.side_effect = ccxt.RequestTimeout("timeout")
        gateway = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"],
            )
        )
        gateway._exchange = exchange
        adapter = _ConfirmingAdapter(gateway, vendor_order_id)
        with (
            patch("quant.trade.brokers.ccxt.confirm.time.sleep"),
            patch("quant.trade.order_policy.time.sleep"),
        ):
            outcome = OrderRetryExecutor().execute(adapter, "BTCUSDT", 1.0, 0.01)

        assert outcome.result is not None
        _assert_no_second_place_without_that_cancel(
            adapter.calls,
            vendor_order_id,
            outcome.result.reason,
            outcome.result.vendor_order_id,
        )
