"""Unit tests for broker adapter registry."""

from unittest.mock import MagicMock

from quant.trade.brokers.ccxt.adapter import CcxtTradeAdapter
from quant.trade.registry import AdapterRegistry, build_default_registry


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
