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
from quant.trade.errors import BrokerConnectionError, SymbolMappingError
from quant.trade.models.order import OrderRequest, OrderSide, OrderType


@pytest.fixture
def inst_cache():
    cache = MagicMock()
    cache.get_product_by_cusip.return_value = {
        "product_id": 1,
        "internal_cusip": "btc-usd.crypto",
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
        symbol = adapter.validate_for_dry_run("btc-usd.crypto", 34)
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
        symbol = adapter.validate_for_dry_run("btc-usd.crypto", 35)
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

    def test_place_order_not_implemented(self, inst_cache):
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )
        req = OrderRequest(
            symbol="BTCUSDT",
            qty=0.01,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
        )
        with pytest.raises(NotImplementedError):
            adapter.place_order(req)
