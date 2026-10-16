"""The API composition that calls the Glassnode xref pass."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from quant.data.glassnode_xref import (
    ASSET_LIST_UNAVAILABLE,
    MARKETS_UNAVAILABLE,
    XREF_NOT_WRITTEN,
    GlassnodeXrefOutcome,
)
from quant.market_data.fetcher import VenueMarket
from tests.unit.test_glassnode_xref import BYBIT, ETH_MARKET, FakeInstruments, _product


@pytest.fixture(autouse=True)
def _reset_asset_cache():
    import quant.api.glassnode_xrefs as boundary

    # getattr so this file still collects against a tree that has no cache.
    # The hang and the per-write reload are what that tree gets wrong.
    clear = getattr(boundary, "clear_glassnode_asset_cache", None)
    wait = getattr(boundary, "wait_for_glassnode_xref_workers", None)
    if wait is not None:
        wait(0)
    if clear is not None:
        clear()
    yield
    if wait is not None:
        wait(2)
    if clear is not None:
        clear()


def test_a_product_without_a_ccxt_listing_does_not_read_glassnode(monkeypatch):
    from quant.api.glassnode_xrefs import apply_listing_glassnode_xrefs

    monkeypatch.setattr(
        "quant.api.glassnode_xrefs.ccxt_apps",
        lambda refdata: [(34, None)],
    )
    monkeypatch.setattr(
        "quant.api.glassnode_xrefs.read_glassnode_asset_symbols",
        MagicMock(side_effect=AssertionError("asset list should not be read")),
    )
    cache = MagicMock()
    cache.get_xrefs.return_value = [
        {"product_id": 4, "app_id": 1, "vendor_symbol": "IBIT"},
    ]
    caches = SimpleNamespace(refdata=object(), instrument_cache=cache)

    assert apply_listing_glassnode_xrefs(caches, MagicMock(), product_id=4) == []


def _caches(cache):
    refdata = MagicMock()
    refdata.resolve_app_id.return_value = 2
    return SimpleNamespace(refdata=refdata, instrument_cache=cache)


def _price_bars(*, cached, live=None):
    price_bars = MagicMock()
    service = price_bars.for_app.return_value
    service.cached_venue_symbols.return_value = cached
    service.venue_symbols.return_value = live if live is not None else cached
    return price_bars


def test_a_cached_catalog_is_confirmed_before_the_write(monkeypatch):
    from quant.api.glassnode_xrefs import (
        apply_listing_glassnode_xrefs,
        store_glassnode_asset_symbols,
    )

    seen = {}

    def map_xrefs(*_args, **kwargs):
        seen["listed_symbols"] = kwargs["listed_symbols"]
        return []

    def reader():
        raise AssertionError("the live catalog must not be read")

    monkeypatch.setattr("quant.api.glassnode_xrefs.ccxt_apps", lambda refdata: [(34, None)])
    monkeypatch.setattr("quant.api.glassnode_xrefs.map_glassnode_xrefs", map_xrefs)
    monkeypatch.setattr("quant.api.glassnode_xrefs.live_glassnode_asset_reader", reader)
    store_glassnode_asset_symbols(["ETH"])
    cache = MagicMock()
    cache.get_xrefs.return_value = [
        {"product_id": 2, "app_id": 34, "vendor_symbol": "ETHUSDT"},
    ]
    price_bars = _price_bars(cached=[VenueMarket("ETHUSDT", "ETH", "USDT", ("spot",))])

    apply_listing_glassnode_xrefs(_caches(cache), price_bars, product_id=2)

    assert seen["listed_symbols"] == ["ETH"]
    price_bars.for_app.return_value.venue_symbols.assert_not_called()


def test_create_does_not_wait_on_a_slow_catalog(monkeypatch):
    from quant.api.glassnode_xrefs import apply_listing_glassnode_xrefs

    release = threading.Event()

    def block(*_args, **_kwargs):
        release.wait(1.0)
        return ["ETH"]

    monkeypatch.setattr("quant.api.glassnode_xrefs.ccxt_apps", lambda refdata: [(34, None)])
    monkeypatch.setattr("quant.api.glassnode_xrefs.read_glassnode_asset_symbols", block)
    monkeypatch.setattr(
        "quant.api.glassnode_xrefs.asset_list_timeout_s",
        lambda: 0.05,
        raising=False,
    )
    cache = MagicMock()
    cache.get_xrefs.return_value = [
        {"product_id": 2, "app_id": 34, "vendor_symbol": "ETHUSDT"},
    ]
    cache.get_product_by_id.return_value = {
        "product_id": 2,
        "internal_cusip": "ethusdt.crypto",
    }
    price_bars = _price_bars(cached=None, live=[ETH_MARKET])

    started = time.perf_counter()
    outcomes = apply_listing_glassnode_xrefs(_caches(cache), price_bars, product_id=2)
    elapsed = time.perf_counter() - started
    release.set()

    assert elapsed < 0.3
    assert outcomes[0].skip_reason == ASSET_LIST_UNAVAILABLE
    assert outcomes[0].wrote is False
    price_bars.for_app.return_value.venue_symbols.assert_not_called()


def test_create_does_not_wait_on_a_slow_venue_when_the_catalog_is_cached(monkeypatch):
    from quant.api.glassnode_xrefs import (
        apply_listing_glassnode_xrefs,
        store_glassnode_asset_symbols,
    )

    release = threading.Event()

    def block_markets():
        release.wait(1.0)
        return [ETH_MARKET]

    monkeypatch.setattr("quant.api.glassnode_xrefs.ccxt_apps", lambda refdata: [(34, None)])
    monkeypatch.setattr(
        "quant.api.glassnode_xrefs.asset_list_timeout_s",
        lambda: 0.05,
        raising=False,
    )
    monkeypatch.setattr(
        "quant.api.glassnode_xrefs.live_glassnode_asset_reader",
        MagicMock(side_effect=AssertionError("catalog is cached")),
        raising=False,
    )
    store_glassnode_asset_symbols(["ETH"])
    cache = MagicMock()
    cache.get_xrefs.return_value = [
        {"product_id": 2, "app_id": 34, "vendor_symbol": "ETHUSDT"},
    ]
    cache.get_product_by_id.return_value = {
        "product_id": 2,
        "internal_cusip": "ethusdt.crypto",
    }
    price_bars = _price_bars(cached=None)
    price_bars.for_app.return_value.venue_symbols.side_effect = block_markets

    started = time.perf_counter()
    outcomes = apply_listing_glassnode_xrefs(_caches(cache), price_bars, product_id=2)
    elapsed = time.perf_counter() - started
    release.set()

    assert elapsed < 0.3
    assert outcomes[0].skip_reason == MARKETS_UNAVAILABLE
    assert outcomes[0].wrote is False


def test_a_fast_catalog_writes_before_create_returns(monkeypatch):
    from quant.api.glassnode_xrefs import apply_listing_glassnode_xrefs

    monkeypatch.setattr("quant.api.glassnode_xrefs.ccxt_apps", lambda refdata: [(BYBIT, None)])
    monkeypatch.setattr("quant.api.glassnode_xrefs.asset_list_timeout_s", lambda: 1.0)
    cache = FakeInstruments(
        [_product(2, "ethusdt.crypto")],
        [{"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"}],
    )
    price_bars = _price_bars(cached=None, live=[ETH_MARKET])

    outcomes = apply_listing_glassnode_xrefs(
        _caches(cache),
        price_bars,
        product_id=2,
        asset_reader=lambda: ["ETH"],
    )

    assert outcomes[0].wrote is True
    assert outcomes[0].vendor_symbol == "ETH"
    assert outcomes[0].skip_reason is None
    assert cache.inserted[0]["vendor_symbol"] == "ETH"


def test_a_fast_catalog_reports_a_base_glassnode_does_not_list(monkeypatch):
    from quant.api.glassnode_xrefs import apply_listing_glassnode_xrefs

    monkeypatch.setattr("quant.api.glassnode_xrefs.ccxt_apps", lambda refdata: [(BYBIT, None)])
    monkeypatch.setattr("quant.api.glassnode_xrefs.asset_list_timeout_s", lambda: 1.0)
    cache = FakeInstruments(
        [_product(2, "ethusdt.crypto")],
        [{"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"}],
    )
    price_bars = _price_bars(cached=None, live=[ETH_MARKET])

    outcomes = apply_listing_glassnode_xrefs(
        _caches(cache),
        price_bars,
        product_id=2,
        asset_reader=lambda: ["BTC"],
    )

    assert cache.inserted == []
    assert outcomes[0].skip_reason == "ETH is not on Glassnode"
    assert outcomes[0].wrote is False


def test_asset_list_timeout_rejects_zero_and_accepts_one(monkeypatch):
    from quant.api.glassnode_xrefs import asset_list_timeout_s

    monkeypatch.delenv("GLASSNODE_ASSET_LIST_TIMEOUT_S", raising=False)
    assert asset_list_timeout_s() == 2.0

    monkeypatch.setenv("GLASSNODE_ASSET_LIST_TIMEOUT_S", "")
    assert asset_list_timeout_s() == 2.0

    monkeypatch.setenv("GLASSNODE_ASSET_LIST_TIMEOUT_S", "1")
    assert asset_list_timeout_s() == 1.0

    monkeypatch.setenv("GLASSNODE_ASSET_LIST_TIMEOUT_S", "0")
    with pytest.raises(ValueError, match="positive"):
        asset_list_timeout_s()

    monkeypatch.setenv("GLASSNODE_ASSET_LIST_TIMEOUT_S", "-1")
    with pytest.raises(ValueError, match="positive"):
        asset_list_timeout_s()

    monkeypatch.setenv("GLASSNODE_ASSET_LIST_TIMEOUT_S", "nope")
    with pytest.raises(ValueError):
        asset_list_timeout_s()


def test_backfill_endpoint_returns_the_pass_report():
    outcome = GlassnodeXrefOutcome(
        product_id=2,
        internal_cusip="ethusdt.crypto",
        vendor_symbol=None,
        skip_reason="ETH is not on Glassnode",
        wrote=False,
    )
    with patch("quant.shared.db.open_pool"), patch(
        "quant.api.admin.router.apply_listing_glassnode_xrefs",
        return_value=[outcome],
    ) as mapped:
        from quant.api.auth.dependencies import require_user_or_service
        from quant.api.deps import get_data_caches
        from quant.api.main import app

        caches = MagicMock()
        app.state.data_caches = caches
        app.state.price_bars = MagicMock()
        app.dependency_overrides[get_data_caches] = lambda: caches
        app.dependency_overrides[require_user_or_service] = lambda: "scheduler"
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/admin/glassnode/product-xrefs")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["mapped"] == []
    assert body["already_mapped"] == []
    assert body["skipped"] == [
        {
            "product_id": 2,
            "internal_cusip": "ethusdt.crypto",
            "vendor_symbol": None,
            "reason": "ETH is not on Glassnode",
        }
    ]
    mapped.assert_called_once()
    assert mapped.call_args.kwargs.get("product_id") is None
    assert body["error"] is None


def test_a_glassnode_blip_does_not_500_the_backfill():
    with patch("quant.shared.db.open_pool"), patch(
        "quant.api.admin.router.apply_listing_glassnode_xrefs",
        side_effect=RuntimeError("glassnode down"),
    ):
        from quant.api.auth.dependencies import require_user_or_service
        from quant.api.deps import get_data_caches
        from quant.api.main import app

        caches = MagicMock()
        app.state.data_caches = caches
        app.state.price_bars = MagicMock()
        app.dependency_overrides[get_data_caches] = lambda: caches
        app.dependency_overrides[require_user_or_service] = lambda: "scheduler"
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/admin/glassnode/product-xrefs")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["mapped"] == []
    assert body["already_mapped"] == []
    assert body["skipped"] == []
    assert body["error"] == XREF_NOT_WRITTEN
