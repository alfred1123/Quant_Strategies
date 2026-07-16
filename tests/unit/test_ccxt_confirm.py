"""Unit tests for :mod:`quant.trade.brokers.ccxt.confirm`."""

from unittest.mock import MagicMock, patch

import pytest

from quant.trade.brokers.ccxt.confirm import (
    _FillStatus,
    _extract_fee,
    _parse_terminal,
    buy_sell_cd_for_action,
    confirm_market_order,
)
from quant.trade.errors import BrokerConnectionError
from quant.trade.models.order import IntendedAction, OrderRequest, OrderSide


class TestExtractFee:
    def test_dict_fee(self):
        assert _extract_fee({"fee": {"cost": 0.25, "currency": "USDT"}}) == 0.25

    def test_none_cost(self):
        assert _extract_fee({"fee": {"cost": None}}) is None

    def test_no_fee_key(self):
        assert _extract_fee({}) is None

    def test_non_dict_fee(self):
        assert _extract_fee({"fee": 0.1}) is None


class TestParseTerminal:
    def test_closed_order_is_terminal_success(self):
        order = {"id": "o1", "status": "closed", "filled": 0.01, "average": 64000.0, "fee": {"cost": 0.25}}
        result = _parse_terminal(order, vendor_order_id="o1")
        assert result is not None
        assert result.success is True
        assert result.filled_qty == 0.01
        assert result.avg_price == 64000.0
        assert result.fee == 0.25

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
            "average": 64000.0, "fee": {"cost": 0.256},
        }
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is True
        assert result.filled_qty == 0.01
        assert result.avg_price == 64000.0
        assert result.fee == 0.256
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
            BrokerConnectionError("order not found: xxx"),
            {"id": "abc", "status": "closed", "filled": 0.01, "average": 64000.0},
        ]
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is True

    @patch("quant.trade.brokers.ccxt.confirm.time.sleep")
    def test_non_retryable_error_returns_failure(self, mock_sleep):
        gw = MagicMock()
        gw.fetch_order.side_effect = BrokerConnectionError("auth failed")
        req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
        result = confirm_market_order(gw, req=req, vendor_order_id="abc")

        assert result.success is False
        assert "auth failed" in result.message


class TestBuySellCdForAction:
    @pytest.mark.parametrize("action,expected", [
        (IntendedAction.BUY, "BUY"),
        (IntendedAction.CLOSE_SHORT, "BUY"),
        (IntendedAction.SELL, "SELL"),
        (IntendedAction.OPEN_SHORT, "SELL"),
        (IntendedAction.HOLD, None),
    ])
    def test_enum_values(self, action, expected):
        assert buy_sell_cd_for_action(action) == expected

    @pytest.mark.parametrize("action_str,expected", [
        ("BUY", "BUY"),
        ("SELL", "SELL"),
        ("CLOSE_SHORT", "BUY"),
        ("OPEN_SHORT", "SELL"),
        ("HOLD", None),
    ])
    def test_string_values(self, action_str, expected):
        assert buy_sell_cd_for_action(action_str) == expected
