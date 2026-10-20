"""Unit tests for broker adapter registry."""

from unittest.mock import MagicMock

import pytest

from quant.trade.brokers.ccxt.adapter import CcxtTradeAdapter
from quant.trade.brokers.ccxt.config import CCXT_PRESETS
from quant.trade.errors import TradeValidationError
from quant.trade.registry import (
    AdapterRegistry,
    build_default_registry,
    exchange_id_for_app,
    instrument_default_type,
    preset_for_app,
)


class TestAdapterRegistry:
    def test_build_default_registry_registers_bybit_and_binance(self):
        refdata = MagicMock()
        refdata.resolve_app_id.side_effect = lambda name: {
            "bybit": 34,
            "binance": 35,
        }[name]

        registry = build_default_registry(refdata)

        assert registry.has_adapter(34)
        assert registry.has_adapter(35)

    def test_create_bybit_adapter(self):
        refdata = MagicMock()
        refdata.resolve_app_id.side_effect = lambda name: {
            "bybit": 34,
            "binance": 35,
        }[name]
        registry = build_default_registry(refdata)
        inst_cache = MagicMock()

        adapter = registry.create(
            34,
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )

        assert isinstance(adapter, CcxtTradeAdapter)
        assert adapter.gateway._config.preset.exchange_id == "bybit"

    def test_create_binance_adapter(self):
        refdata = MagicMock()
        refdata.resolve_app_id.side_effect = lambda name: {
            "bybit": 34,
            "binance": 35,
        }[name]
        registry = build_default_registry(refdata)
        inst_cache = MagicMock()

        adapter = registry.create(
            35,
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
        )

        assert isinstance(adapter, CcxtTradeAdapter)
        assert adapter.gateway._config.preset.exchange_id == "binanceusdm"

    def test_unknown_app_id_raises(self):
        registry = AdapterRegistry()
        try:
            registry.create(999, api_key="k", api_secret="s", paper=True)
        except Exception as exc:
            assert "no adapter registered" in str(exc)
        else:
            raise AssertionError("expected AdapterNotFoundError")


class TestExchangeIdForApp:
    """Market data must reach the same venue the orders go to."""

    def _refdata(self):
        refdata = MagicMock()
        refdata.resolve_app_id.side_effect = lambda name: {
            "bybit": 34,
            "binance": 35,
        }[name]
        return refdata

    def test_resolves_each_broker_to_its_ccxt_id(self):
        refdata = self._refdata()

        assert exchange_id_for_app(34, refdata=refdata) == "bybit"
        assert preset_for_app(34, refdata=refdata).default_type_for("spot") == "spot"
        assert preset_for_app(34, refdata=refdata).default_type_for("future") == "linear"
        # Binance trades under a different ccxt class than its REFDATA name.
        assert exchange_id_for_app(35, refdata=refdata) == "binanceusdm"
        assert preset_for_app(35, refdata=refdata).default_type is None

    def test_non_broker_app_returns_none(self):
        # e.g. the glassnode data app — it has an APP_ID but no venue.
        assert exchange_id_for_app(2, refdata=self._refdata()) is None


class TestInstrumentDefaultType:
    """One resolver: the order session, the bar fetcher and the qty editor read it."""

    def _instruments(self, product):
        inst = MagicMock()
        inst.get_product_by_cusip.return_value = product
        return inst

    def test_issue_type_selects_the_default_type(self):
        inst = self._instruments({"issue_type": "future"})
        assert instrument_default_type(CCXT_PRESETS["bybit"], inst, "btcusdt.crypto") == "linear"
        inst.get_product_by_cusip.assert_called_once_with("btcusdt.crypto")

    def test_a_venue_without_a_map_pins_nothing_and_does_not_read_the_product(self):
        inst = self._instruments({"issue_type": "future"})
        assert instrument_default_type(CCXT_PRESETS["binance"], inst, "btcusdt.crypto") is None
        inst.get_product_by_cusip.assert_not_called()

    @pytest.mark.parametrize("product", [None, {"issue_type": None}, {"issue_type": "option"}])
    def test_an_unmapped_product_is_refused_as_a_trade_validation_error(self, product):
        with pytest.raises(TradeValidationError, match="ISSUE_TYPE"):
            instrument_default_type(CCXT_PRESETS["bybit"], self._instruments(product), "x.crypto")

    def test_no_caller_keeps_its_own_copy(self):
        import inspect

        from quant.trade import bar_source, service
        from quant.trade.brokers.ccxt import adapter

        for module in (bar_source, service, adapter):
            src = inspect.getsource(module)
            assert "default_type_for(issue_type)" not in src, module.__name__
            assert "instrument_default_type" in src, module.__name__
