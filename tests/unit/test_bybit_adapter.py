"""Unit tests for ccxt broker adapter and exchange wiring."""

from unittest.mock import MagicMock, patch

import pytest

from quant.trade.adapters.base import TradeAdapter
from quant.trade.brokers.ccxt.adapter import CcxtTradeAdapter, create_ccxt_adapter
from quant.trade.brokers.ccxt.config import (
    CCXT_PRESETS,
    ConnectParams,
    _wire_bybit,
    _wire_paper_sandbox,
)
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import (
    BrokerConnectionError,
    SymbolMappingError,
    TradeValidationError,
)
from quant.trade.models.order import (
    IntendedAction,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)


@pytest.fixture
def inst_cache():
    cache = MagicMock()
    cache.get_product_by_cusip.return_value = {
        "product_id": 1,
        "internal_cusip": "btcusdt.crypto",
    }
    cache.resolve_internal_cusip.return_value = "BTCUSDT"
    return cache


class TestExchangeWiring:
    def test_default_paper_enables_sandbox(self):
        exchange = MagicMock()
        _wire_paper_sandbox(exchange, ConnectParams(paper=True))
        exchange.set_sandbox_mode.assert_called_once_with(True)

    def test_default_live_skips_sandbox(self):
        exchange = MagicMock()
        _wire_paper_sandbox(exchange, ConnectParams(paper=False))
        exchange.set_sandbox_mode.assert_not_called()

    def test_bybit_demo_enables_demo_not_sandbox(self):
        exchange = MagicMock()
        exchange.has = {"fetchCurrencies": True}
        _wire_bybit(exchange, ConnectParams(paper=True, demo=True))
        assert exchange.has["fetchCurrencies"] is False
        exchange.enable_demo_trading.assert_called_once_with(True)
        exchange.set_sandbox_mode.assert_not_called()

    def test_bybit_paper_enables_sandbox_not_demo(self):
        exchange = MagicMock()
        exchange.has = {"fetchCurrencies": True}
        _wire_bybit(exchange, ConnectParams(paper=True, demo=False))
        assert exchange.has["fetchCurrencies"] is False
        exchange.set_sandbox_mode.assert_called_once_with(True)
        exchange.enable_demo_trading.assert_not_called()

    def test_bybit_live_skips_demo_and_sandbox(self):
        exchange = MagicMock()
        exchange.has = {"fetchCurrencies": True}
        _wire_bybit(exchange, ConnectParams(paper=False, demo=False))
        exchange.set_sandbox_mode.assert_not_called()
        exchange.enable_demo_trading.assert_not_called()


class TestIntendedSide:
    """TradeAdapter.intended_side — covers long, flat, and short positions."""

    def test_long_signal_flat_position(self):
        assert TradeAdapter.intended_side(1.0, 0.0) == "BUY"

    def test_long_signal_existing_long(self):
        assert TradeAdapter.intended_side(1.0, 0.01) == "HOLD"

    def test_long_signal_existing_short(self):
        assert TradeAdapter.intended_side(1.0, -0.5) == "CLOSE_SHORT"

    def test_flat_signal_with_long(self):
        assert TradeAdapter.intended_side(0.0, 0.01) == "SELL"

    def test_flat_signal_no_position(self):
        assert TradeAdapter.intended_side(0.0, 0.0) == "HOLD"

    def test_flat_signal_with_short(self):
        assert TradeAdapter.intended_side(0.0, -0.5) == "CLOSE_SHORT"

    def test_sell_signal_with_long(self):
        assert TradeAdapter.intended_side(-1.0, 1.0) == "SELL"

    def test_sell_signal_flat(self):
        assert TradeAdapter.intended_side(-1.0, 0.0) == "OPEN_SHORT"

    def test_sell_signal_already_short(self):
        assert TradeAdapter.intended_side(-1.0, -0.5) == "HOLD"

    def test_returns_intended_action_enum(self):
        assert TradeAdapter.intended_side(1.0, 0.0) is IntendedAction.BUY

    def test_float_dust_position_treated_as_flat(self):
        assert TradeAdapter.intended_side(1.0, 1e-12) == "BUY"
        assert TradeAdapter.intended_side(0.0, -1e-12) == "HOLD"
        assert TradeAdapter.intended_side(-1.0, 1e-12) == "OPEN_SHORT"


class TestIntendedActionOrderSide:
    """IntendedAction.order_side — collapses position-aware action to raw side."""

    @pytest.mark.parametrize("action,expected", [
        (IntendedAction.BUY, OrderSide.BUY),
        (IntendedAction.CLOSE_SHORT, OrderSide.BUY),
        (IntendedAction.SELL, OrderSide.SELL),
        (IntendedAction.OPEN_SHORT, OrderSide.SELL),
        (IntendedAction.HOLD, None),
    ])
    def test_mapping(self, action, expected):
        assert action.order_side() == expected


class TestSessionConfigRepr:
    def test_secrets_hidden_from_repr(self):
        cfg = CcxtSessionConfig(
            api_key="AKIA-VISIBLE-KEY",
            api_secret="super-secret-value",
            preset=CCXT_PRESETS["bybit"],
        )
        assert "AKIA-VISIBLE-KEY" not in repr(cfg)
        assert "super-secret-value" not in repr(cfg)


class TestCcxtTradeGateway:
    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_bybit_validate_credentials_success(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["bybit"],
                paper=True,
            )
        )
        gw.connect()
        gw.validate_credentials()

        exchange.set_sandbox_mode.assert_called_once_with(True)
        assert exchange.has["fetchCurrencies"] is False
        exchange.load_markets.assert_called_once()
        exchange.fetch_balance.assert_called_once()

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_bybit_demo_wiring(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["bybit"],
                paper=True,
                demo=True,
            )
        )
        gw.connect()

        exchange.enable_demo_trading.assert_called_once_with(True)
        exchange.set_sandbox_mode.assert_not_called()

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_binance_validate_credentials_success(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTC/USDT:USDT": {}}
        mock_ccxt.binanceusdm.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["binance"],
                paper=True,
            )
        )
        gw.connect()
        gw.validate_credentials()

        exchange.set_sandbox_mode.assert_called_once_with(True)
        mock_ccxt.binanceusdm.assert_called_once()
        exchange.fetch_balance.assert_called_once()

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_fetch_position_qty_matches_unified_symbol(self, mock_ccxt):
        """fetch_positions returns ccxt unified symbol (BTC/USDT:USDT), not
        the raw vendor_symbol (BTCUSDT) — must still match."""
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.market.return_value = {"symbol": "BTC/USDT:USDT"}
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0.001, "side": "long", "info": {"symbol": "BTCUSDT"}}
        ]
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True,
            )
        )
        gw.connect()
        assert gw.fetch_position_qty("BTCUSDT") == 0.001

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_fetch_position_qty_short_is_negative(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.market.return_value = {"symbol": "BTC/USDT:USDT"}
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0.002, "side": "short", "info": {"symbol": "BTCUSDT"}}
        ]
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True,
            )
        )
        gw.connect()
        assert gw.fetch_position_qty("BTCUSDT") == -0.002

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_fetch_position_qty_no_position_returns_zero(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.market.return_value = {"symbol": "BTC/USDT:USDT"}
        exchange.fetch_positions.return_value = []
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True,
            )
        )
        gw.connect()
        assert gw.fetch_position_qty("BTCUSDT") == 0.0

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_auth_failure_raises(self, mock_ccxt):
        import ccxt

        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.fetch_balance.side_effect = ccxt.AuthenticationError("bad key")
        mock_ccxt.bybit.return_value = exchange
        mock_ccxt.AuthenticationError = ccxt.AuthenticationError
        mock_ccxt.BaseError = ccxt.BaseError

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["bybit"],
                paper=True,
            )
        )
        gw.connect()
        with pytest.raises(BrokerConnectionError, match="authentication"):
            gw.validate_credentials()


class TestCreateCcxtAdapter:
    @patch.object(CcxtTradeGateway, "validate_credentials")
    @patch.object(CcxtTradeGateway, "connect")
    @patch.object(CcxtTradeGateway, "market_exists", return_value=True)
    def test_bybit_dry_run(self, _market, _conn, _val, inst_cache):
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )
        symbol = adapter.validate_for_dry_run("btcusdt.crypto", 34)
        assert symbol == "BTCUSDT"
        assert adapter.gateway._config.preset.exchange_id == "bybit"

    @patch.object(CcxtTradeGateway, "validate_credentials")
    @patch.object(CcxtTradeGateway, "connect")
    @patch.object(CcxtTradeGateway, "market_exists", return_value=True)
    def test_binance_dry_run(self, _market, _conn, _val, inst_cache):
        inst_cache.resolve_internal_cusip.return_value = "BTC/USDT:USDT"
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["binance"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )
        symbol = adapter.validate_for_dry_run("btcusdt.crypto", 35)
        assert symbol == "BTC/USDT:USDT"
        assert adapter.gateway._config.preset.exchange_id == "binanceusdm"

    def test_unknown_cusip_raises(self, inst_cache):
        inst_cache.resolve_internal_cusip.return_value = None
        inst_cache.get_product_by_cusip.return_value = None
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )
        with pytest.raises(SymbolMappingError, match="unknown product"):
            adapter.validate_for_dry_run("missing.crypto", 34)

class TestPlaceOrder:
    def _adapter(self, inst_cache):
        return create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )

    @patch("quant.trade.brokers.ccxt.adapter.confirm_market_order")
    def test_place_order_buy_success(self, mock_confirm, inst_cache):
        adapter = self._adapter(inst_cache)
        mock_confirm.return_value = OrderResult(
            success=True, vendor_order_id="abc123", message="order filled",
            raw_status="closed", side=OrderSide.BUY, requested_qty=0.01,
            filled_qty=0.01, avg_price=64000.0, fee=0.256,
        )
        with patch.object(
            adapter.gateway, "create_market_order",
            return_value={"id": "abc123", "status": "open"},
        ) as mock_create:
            req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            result = adapter.place_order(req)

        mock_create.assert_called_once_with("BTCUSDT", "buy", 0.01)
        mock_confirm.assert_called_once_with(
            adapter.gateway, req=req, vendor_order_id="abc123",
        )
        assert result.success is True
        assert result.vendor_order_id == "abc123"
        assert result.filled_qty == 0.01

    @patch("quant.trade.brokers.ccxt.adapter.confirm_market_order")
    def test_place_order_sell_maps_side(self, mock_confirm, inst_cache):
        adapter = self._adapter(inst_cache)
        mock_confirm.return_value = OrderResult(
            success=True, vendor_order_id="xyz", message="filled",
            side=OrderSide.SELL, requested_qty=0.01,
        )
        with patch.object(
            adapter.gateway, "create_market_order", return_value={"id": "xyz"},
        ) as mock_create:
            adapter.place_order(OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.SELL))
        mock_create.assert_called_once_with("BTCUSDT", "sell", 0.01)

    def test_place_order_rejects_limit_orders(self, inst_cache):
        adapter = self._adapter(inst_cache)
        req = OrderRequest(
            symbol="BTCUSDT",
            qty=0.01,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=50_000.0,
        )
        with pytest.raises(TradeValidationError, match="market only"):
            adapter.place_order(req)

    def test_place_order_broker_error_returns_failed_result(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "create_market_order",
            side_effect=BrokerConnectionError("insufficient funds"),
        ):
            req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            result = adapter.place_order(req)

        assert result.success is False
        assert result.vendor_order_id is None
        assert result.side == OrderSide.BUY
        assert result.requested_qty == 0.01
        assert "insufficient funds" in result.message

    def test_place_order_no_order_id_returns_failed(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "create_market_order",
            return_value={"id": None, "status": "unknown"},
        ):
            req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            result = adapter.place_order(req)

        assert result.success is False
        assert "no order id" in result.message

    def test_cancel_order_success(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "cancel_order", return_value={"status": "canceled"},
        ) as mock_cancel:
            result = adapter.cancel_order("order-1", "BTCUSDT")
        mock_cancel.assert_called_once_with("order-1", "BTCUSDT")
        assert result.success is True
        assert result.vendor_order_id == "order-1"

    def test_get_open_orders_delegates_to_gateway(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter.gateway, "fetch_open_orders", return_value=[{"id": "1"}]) as mock_fetch:
            orders = adapter.get_open_orders("BTCUSDT")
        mock_fetch.assert_called_once_with("BTCUSDT")
        assert orders == [{"id": "1"}]


class TestApplySignal:
    def _adapter(self, inst_cache):
        return create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )

    def test_buy_signal_flat_position_opens_long(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "get_position_qty", return_value=0.0), \
             patch.object(adapter, "place_order") as mock_place:
            mock_place.return_value = OrderResult(success=True, vendor_order_id="1", message="ok")
            result = adapter.apply_signal("BTCUSDT", 1.0, 0.01)

        req = mock_place.call_args[0][0]
        assert req.side == OrderSide.BUY and req.qty == 0.01
        assert result.success is True

    def test_hold_signal_places_no_order(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "get_position_qty", return_value=0.01), \
             patch.object(adapter, "place_order") as mock_place:
            result = adapter.apply_signal("BTCUSDT", 1.0, 0.01)

        mock_place.assert_not_called()
        assert result is None

    def test_flat_signal_with_long_position_sells_full_qty(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "get_position_qty", return_value=0.03), \
             patch.object(adapter, "place_order") as mock_place:
            mock_place.return_value = OrderResult(success=True, vendor_order_id="2", message="ok")
            adapter.apply_signal("BTCUSDT", 0.0, 0.01)

        req = mock_place.call_args[0][0]
        assert req.side == OrderSide.SELL and req.qty == 0.03

    def test_sell_signal_flat_opens_short(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "get_position_qty", return_value=0.0), \
             patch.object(adapter, "place_order") as mock_place:
            mock_place.return_value = OrderResult(success=True, vendor_order_id="3", message="ok")
            adapter.apply_signal("BTCUSDT", -1.0, 0.01)

        req = mock_place.call_args[0][0]
        assert req.side == OrderSide.SELL and req.qty == 0.01

    def test_buy_signal_with_short_position_closes_short(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "get_position_qty", return_value=-0.02), \
             patch.object(adapter, "place_order") as mock_place:
            mock_place.return_value = OrderResult(success=True, vendor_order_id="4", message="ok")
            adapter.apply_signal("BTCUSDT", 1.0, 0.01)

        req = mock_place.call_args[0][0]
        assert req.side == OrderSide.BUY and req.qty == 0.02

    def test_execute_action_uses_passed_position_without_refetch(self, inst_cache):
        """The caller's position reading drives sizing — no second broker read."""
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "get_position_qty") as mock_pos, \
             patch.object(adapter, "place_order") as mock_place:
            mock_place.return_value = OrderResult(success=True, vendor_order_id="5", message="ok")
            adapter.execute_action("BTCUSDT", IntendedAction.SELL, 0.01, 0.04)

        mock_pos.assert_not_called()
        req = mock_place.call_args[0][0]
        assert req.side == OrderSide.SELL and req.qty == 0.04

    def test_execute_action_zero_position_close_returns_none(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "place_order") as mock_place:
            result = adapter.execute_action("BTCUSDT", IntendedAction.SELL, 0.01, 0.0)

        mock_place.assert_not_called()
        assert result is None
