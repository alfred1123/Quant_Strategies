"""Build the e2e Bybit adapter fixture without live keys or a venue connect.

``bybit_adapter`` lives in an ``e2e`` module, so the default suite never
requests it. This constructs that fixture through ``AdapterRegistry.create``
and stops before ``connect``.
"""

from __future__ import annotations

import inspect

from quant.trade.brokers.ccxt.adapter import CcxtTradeAdapter
from quant.trade.registry import build_default_registry
from scripts.bybit_local_testnet import BYBIT_APP_ID
from tests.integration.test_ccxt_dry_run import bybit_adapter
from tests.unit.test_bybit_local_testnet import _BybitRefData


def test_bybit_adapter_fixture_builds_through_registry(monkeypatch):
    monkeypatch.setattr(CcxtTradeAdapter, "connect", lambda self: None)
    monkeypatch.setattr(CcxtTradeAdapter, "disconnect", lambda self: None)
    refdata = _BybitRefData()
    registry = build_default_registry(refdata)
    inst = object()
    # Pytest refuses a direct fixture call. unwrap is the fixture body.
    fixture = inspect.unwrap(bybit_adapter)(
        ("k", "s"),
        inst,
        {"app_id": BYBIT_APP_ID, "paper": True},
        registry,
    )
    adapter = next(fixture)
    try:
        assert isinstance(adapter, CcxtTradeAdapter)
        assert adapter._inst is inst
        assert adapter._confirm_delays_s == refdata.setting_floats("fill_confirm_delays_s")
        assert adapter._confirm_delays_s == (9.5, 8.5)
        assert adapter._session.preset.exchange_id == "bybit"
    finally:
        fixture.close()
