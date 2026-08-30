"""INST router — the product lists the UI builds its dropdowns from."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

BYBIT = 34
NASDAQ = 7

BTC = {"product_id": 1, "internal_cusip": "btcusdt.crypto", "display_nm": "Bitcoin"}
ETH = {"product_id": 2, "internal_cusip": "ethusdt.crypto", "display_nm": "Ethereum"}
IBIT = {"product_id": 3, "internal_cusip": "ibit.nasdaq", "display_nm": "iShares BTC"}

XREFS = [
    {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
    {"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"},
    {"product_id": 3, "app_id": NASDAQ, "vendor_symbol": "IBIT"},
]

PRODUCTS = {1: BTC, 2: ETH, 3: IBIT}


@pytest.fixture
def client_and_cache():
    """TestClient plus a stand-in InstrumentCache holding the fixtures above."""
    with patch("quant.shared.db.psycopg"):
        from quant.api.auth.dependencies import require_user
        from quant.api.auth.models import CurrentUser
        from quant.api.deps import get_data_caches
        from quant.api.main import app

        cache = MagicMock()
        cache.get_xrefs.side_effect = lambda product_id=None, app_id=None: [
            x
            for x in XREFS
            if (product_id is None or x["product_id"] == product_id)
            and (app_id is None or x["app_id"] == app_id)
        ]
        cache.get_product_by_id.side_effect = PRODUCTS.get
        cache.get_products.return_value = list(PRODUCTS.values())

        caches = MagicMock()
        caches.instrument_cache = cache
        app.state.data_caches = caches
        # Read by `get_auth_service` even with `require_user` overridden.
        app.state.auth_service = MagicMock()
        app.dependency_overrides[get_data_caches] = lambda: caches
        app.dependency_overrides[require_user] = lambda: CurrentUser(
            app_user_id=uuid.uuid4(), username="alice", session_gen=1
        )

        try:
            yield TestClient(app), cache
        finally:
            app.dependency_overrides.clear()


class TestAppProducts:
    """What one venue lists — the only set worth offering once it is chosen."""

    def test_returns_only_what_that_venue_lists(self, client_and_cache):
        # The unscoped list is every instrument the platform knows. Offering a
        # Nasdaq ETF for a Bybit subscription can only produce a row that never
        # captures a bar.
        client, _cache = client_and_cache

        resp = client.get(f"/api/v1/inst/apps/{BYBIT}/products")

        assert resp.status_code == 200
        assert [p["internal_cusip"] for p in resp.json()] == [
            "btcusdt.crypto",
            "ethusdt.crypto",
        ]

    def test_carries_the_symbol_that_venue_prints(self, client_and_cache):
        """Listing and naming are the same fact, so they travel together."""
        client, _cache = client_and_cache

        rows = client.get(f"/api/v1/inst/apps/{BYBIT}/products").json()

        assert {r["internal_cusip"]: r["vendor_symbol"] for r in rows} == {
            "btcusdt.crypto": "BTCUSDT",
            "ethusdt.crypto": "ETHUSDT",
        }

    def test_the_same_product_is_scoped_per_venue(self, client_and_cache):
        client, _cache = client_and_cache

        rows = client.get(f"/api/v1/inst/apps/{NASDAQ}/products").json()

        assert [r["internal_cusip"] for r in rows] == ["ibit.nasdaq"]

    def test_a_venue_listing_nothing_is_an_empty_list_not_a_404(
        self, client_and_cache
    ):
        """Unlike a missing product, listing nothing is a real answer."""
        client, _cache = client_and_cache

        resp = client.get("/api/v1/inst/apps/999/products")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_an_xref_to_a_vanished_product_is_skipped_not_a_crash(
        self, client_and_cache
    ):
        """A dangling xref must not take the whole dropdown down with it."""
        client, cache = client_and_cache
        cache.get_product_by_id.side_effect = lambda pid: (
            None if pid == 2 else PRODUCTS.get(pid)
        )

        rows = client.get(f"/api/v1/inst/apps/{BYBIT}/products").json()

        assert [r["internal_cusip"] for r in rows] == ["btcusdt.crypto"]

    def test_reads_the_cache_rather_than_the_database(self, client_and_cache):
        """This is on the dialog's critical path; it must not be a query."""
        client, cache = client_and_cache

        client.get(f"/api/v1/inst/apps/{BYBIT}/products")

        cache.get_xrefs.assert_called_once_with(app_id=BYBIT)
