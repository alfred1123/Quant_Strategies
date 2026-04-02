"""Unit tests for the FutuTrader module."""

import sys
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from trade import FutuTrader, OrderResult


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def mock_env():
    """Provide required env vars and suppress load_dotenv."""
    with patch("trade.load_dotenv"), \
         patch.dict("os.environ", {
             "FUTU_HOST": "127.0.0.1", "FUTU_PORT": "11111",
         }):
        yield


@pytest.fixture
def mock_ctx():
    """Mock the OpenSecTradeContext and connection check so no real connection is made."""
    with patch("trade.futu.OpenSecTradeContext") as MockCtx, \
         patch.object(FutuTrader, "_check_connection"):
        instance = MagicMock()
        MockCtx.return_value = instance
        yield instance


@pytest.fixture
def trader(mock_env, mock_ctx):
    """Create a FutuTrader in paper mode with mocked connection."""
    return FutuTrader(paper=True)


# ── Init Tests ──────────────────────────────────────────────────────

class TestFutuTraderInit:
    def test_init_paper_mode(self, mock_env, mock_ctx):
        t = FutuTrader(paper=True)
        assert t._paper is True

    def test_init_live_mode(self, mock_env, mock_ctx):
        t = FutuTrader(paper=False)
        assert t._paper is False

    def test_init_default_market_us(self, mock_env, mock_ctx):
        t = FutuTrader(paper=True)
        assert t._market == "US"

    def test_init_hk_market(self, mock_env, mock_ctx):
        t = FutuTrader(paper=True, market="HK")
        assert t._market == "HK"

    def test_init_invalid_market_raises(self, mock_env, mock_ctx):
        with pytest.raises(ValueError, match="Unsupported market"):
            FutuTrader(paper=True, market="INVALID")

    def test_init_raises_without_env(self):
        with patch("trade.load_dotenv"), \
             patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="FUTU_HOST and FUTU_PORT"):
                FutuTrader(paper=True)

    def test_init_raises_missing_port(self):
        with patch("trade.load_dotenv"), \
             patch.dict("os.environ", {"FUTU_HOST": "127.0.0.1"}, clear=True):
            with pytest.raises(ValueError, match="FUTU_HOST and FUTU_PORT"):
                FutuTrader(paper=True)


# ── Market Detection ───────────────────────────────────────────────

class TestDetectMarket:
    def test_us_symbol(self):
        assert FutuTrader.detect_market("US.WEAT") == "US"

    def test_hk_symbol(self):
        assert FutuTrader.detect_market("HK.00700") == "HK"

    def test_no_prefix_defaults_us(self):
        assert FutuTrader.detect_market("AAPL") == "US"

    def test_sg_symbol(self):
        assert FutuTrader.detect_market("SG.D05") == "SG"

    def test_case_insensitive(self):
        assert FutuTrader.detect_market("hk.00700") == "HK"


# ── Context Manager ────────────────────────────────────────────────

class TestContextManager:
    def test_context_manager_calls_close(self, mock_env, mock_ctx):
        with FutuTrader(paper=True) as t:
            pass
        mock_ctx.close.assert_called_once()


# ── Unlock ──────────────────────────────────────────────────────────

class TestUnlock:
    def test_unlock_success(self, trader, mock_ctx):
        mock_ctx.unlock_trade.return_value = (0, "OK")
        assert trader.unlock("password123") is True

    def test_unlock_failure(self, trader, mock_ctx):
        mock_ctx.unlock_trade.return_value = (-1, "Bad password")
        assert trader.unlock("wrong") is False


# ── Place Order ─────────────────────────────────────────────────────

class TestPlaceOrder:
    def test_place_market_buy_success(self, trader, mock_ctx):
        mock_ctx.place_order.return_value = (
            0,
            pd.DataFrame({"order_id": ["12345"]}),
        )
        result = trader.place_order("US.WEAT", 100, "BUY")
        assert result.success is True
        assert result.order_id == "12345"
        mock_ctx.place_order.assert_called_once()

    def test_place_market_sell_success(self, trader, mock_ctx):
        mock_ctx.place_order.return_value = (
            0,
            pd.DataFrame({"order_id": ["67890"]}),
        )
        result = trader.place_order("US.WEAT", 50, "SELL")
        assert result.success is True
        assert result.order_id == "67890"

    def test_place_order_failure(self, trader, mock_ctx):
        mock_ctx.place_order.return_value = (-1, "Insufficient funds")
        result = trader.place_order("US.WEAT", 100, "BUY")
        assert result.success is False
        assert result.order_id is None

    def test_limit_order_without_price_fails(self, trader, mock_ctx):
        result = trader.place_order("US.WEAT", 100, "BUY", order_type="NORMAL")
        assert result.success is False
        assert "Limit price required" in result.message
        mock_ctx.place_order.assert_not_called()

    def test_limit_order_with_price(self, trader, mock_ctx):
        mock_ctx.place_order.return_value = (
            0,
            pd.DataFrame({"order_id": ["LMT001"]}),
        )
        result = trader.place_order(
            "US.WEAT", 100, "BUY", order_type="NORMAL", price=5.50,
        )
        assert result.success is True


# ── Cancel Order ────────────────────────────────────────────────────

class TestCancelOrder:
    def test_cancel_success(self, trader, mock_ctx):
        mock_ctx.modify_order.return_value = (0, "OK")
        assert trader.cancel_order("12345") is True

    def test_cancel_failure(self, trader, mock_ctx):
        mock_ctx.modify_order.return_value = (-1, "Not found")
        assert trader.cancel_order("99999") is False

    def test_cancel_all_success(self, trader, mock_ctx):
        mock_ctx.cancel_all_order.return_value = (0, "OK")
        assert trader.cancel_all_orders() is True

    def test_cancel_all_failure(self, trader, mock_ctx):
        mock_ctx.cancel_all_order.return_value = (-1, "Error")
        assert trader.cancel_all_orders() is False


# ── Queries ─────────────────────────────────────────────────────────

class TestQueries:
    def test_get_positions_success(self, trader, mock_ctx):
        mock_ctx.position_list_query.return_value = (
            0,
            pd.DataFrame({"code": ["US.WEAT"], "qty": [100]}),
        )
        positions = trader.get_positions()
        assert positions is not None
        assert len(positions) == 1

    def test_get_positions_failure(self, trader, mock_ctx):
        mock_ctx.position_list_query.return_value = (-1, "Error")
        assert trader.get_positions() is None

    def test_get_orders_success(self, trader, mock_ctx):
        mock_ctx.order_list_query.return_value = (
            0,
            pd.DataFrame({"order_id": ["123"], "status": ["FILLED"]}),
        )
        orders = trader.get_orders()
        assert orders is not None

    def test_get_orders_failure(self, trader, mock_ctx):
        mock_ctx.order_list_query.return_value = (-1, "Error")
        assert trader.get_orders() is None

    def test_get_account_info_success(self, trader, mock_ctx):
        mock_ctx.accinfo_query.return_value = (
            0,
            pd.DataFrame({"total_assets": [10000.0]}),
        )
        acct = trader.get_account_info()
        assert acct is not None

    def test_get_account_info_failure(self, trader, mock_ctx):
        mock_ctx.accinfo_query.return_value = (-1, "Error")
        assert trader.get_account_info() is None


# ── Apply Signal ────────────────────────────────────────────────────

class TestApplySignal:
    def test_signal_long_from_flat(self, trader, mock_ctx):
        # No existing position
        mock_ctx.position_list_query.return_value = (
            0, pd.DataFrame(columns=["code", "qty"]),
        )
        mock_ctx.place_order.return_value = (
            0, pd.DataFrame({"order_id": ["BUY001"]}),
        )
        result = trader.apply_signal("US.WEAT", 1, 100)
        assert result is not None
        assert result.success is True

    def test_signal_flat_from_long(self, trader, mock_ctx):
        mock_ctx.position_list_query.return_value = (
            0, pd.DataFrame({"code": ["US.WEAT"], "qty": [100]}),
        )
        mock_ctx.place_order.return_value = (
            0, pd.DataFrame({"order_id": ["SELL001"]}),
        )
        result = trader.apply_signal("US.WEAT", 0, 100)
        assert result is not None
        assert result.success is True

    def test_signal_no_action_when_already_long(self, trader, mock_ctx):
        mock_ctx.position_list_query.return_value = (
            0, pd.DataFrame({"code": ["US.WEAT"], "qty": [100]}),
        )
        result = trader.apply_signal("US.WEAT", 1, 100)
        assert result is None  # already long, no trade needed

    def test_signal_no_action_when_already_flat(self, trader, mock_ctx):
        mock_ctx.position_list_query.return_value = (
            0, pd.DataFrame(columns=["code", "qty"]),
        )
        result = trader.apply_signal("US.WEAT", 0, 100)
        assert result is None  # already flat


# ── OrderResult ─────────────────────────────────────────────────────

class TestOrderResult:
    def test_success_result(self):
        r = OrderResult(True, "123", "OK")
        assert r.success is True
        assert r.order_id == "123"

    def test_failure_result(self):
        r = OrderResult(False, None, "Failed")
        assert r.success is False
        assert r.order_id is None


# ── Connection Timeout ──────────────────────────────────────────────

class TestConnectionTimeout:
    def test_raises_connection_error_when_gateway_down(self, mock_env):
        with patch("trade.socket.socket") as mock_sock_cls:
            import socket
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = socket.timeout("timed out")
            mock_sock_cls.return_value = mock_sock
            with pytest.raises(ConnectionError, match="Cannot reach Futu OpenD"):
                FutuTrader(paper=True)

    def test_raises_connection_error_on_refused(self, mock_env):
        with patch("trade.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_sock_cls.return_value = mock_sock
            with pytest.raises(ConnectionError, match="Cannot reach Futu OpenD"):
                FutuTrader(paper=True)

    def test_custom_timeout_value(self, mock_env):
        with patch("trade.socket.socket") as mock_sock_cls, \
             patch("trade.futu.OpenSecTradeContext"):
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            t = FutuTrader(paper=True, timeout=10)
            assert t._timeout == 10
            mock_sock.settimeout.assert_called_with(10)

    def test_default_timeout(self, mock_env):
        with patch("trade.socket.socket") as mock_sock_cls, \
             patch("trade.futu.OpenSecTradeContext"):
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            t = FutuTrader(paper=True)
            assert t._timeout == 5
            mock_sock.settimeout.assert_called_with(5)
