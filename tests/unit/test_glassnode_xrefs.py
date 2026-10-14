"""The API composition that calls the Glassnode xref pass."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from quant.data.glassnode_xref import GlassnodeXrefOutcome
from quant.market_data.fetcher import VenueMarket


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


def test_an_exchange_listing_confirms_the_asset_list_before_the_write(monkeypatch):
    from quant.api.glassnode_xrefs import apply_listing_glassnode_xrefs

    order = []

    def read_assets():
        order.append("assets")
        return ["ETH"]

    def map_xrefs(*_args, **kwargs):
        order.append(kwargs["listed_symbols"])
        return []

    monkeypatch.setattr("quant.api.glassnode_xrefs.ccxt_apps", lambda refdata: [(34, None)])
    monkeypatch.setattr("quant.api.glassnode_xrefs.read_glassnode_asset_symbols", read_assets)
    monkeypatch.setattr("quant.api.glassnode_xrefs.map_glassnode_xrefs", map_xrefs)
    cache = MagicMock()
    cache.get_xrefs.return_value = [
        {"product_id": 2, "app_id": 34, "vendor_symbol": "ETHUSDT"},
    ]
    refdata = MagicMock()
    refdata.resolve_app_id.return_value = 2
    caches = SimpleNamespace(refdata=refdata, instrument_cache=cache)
    price_bars = MagicMock()
    price_bars.for_app.return_value.venue_symbols.return_value = [
        VenueMarket("ETHUSDT", "ETH", "USDT", ("spot",)),
    ]

    apply_listing_glassnode_xrefs(caches, price_bars, product_id=2)

    assert order == ["assets", ["ETH"]]


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
