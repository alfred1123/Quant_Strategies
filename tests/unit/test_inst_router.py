"""INST router — the product lists the UI builds its dropdowns from."""

import uuid
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from fastapi.testclient import TestClient

from quant.market_data.fetcher import BarFetchError, VenueMarket
from quant.shared.db import ProcedureError

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
def price_bars():
    """Stand-in for the factory that owns one keyless ccxt client per venue."""
    factory = MagicMock()
    factory.for_app.return_value.venue_symbols.return_value = [
        VenueMarket(
            vendor_symbol="BTCUSDT",
            base="BTC",
            quote="USDT",
            market_types=("spot", "swap"),
        ),
    ]
    return factory


@pytest.fixture
def client_and_cache(price_bars):
    """TestClient plus a stand-in InstrumentCache holding the fixtures above."""
    with patch("quant.shared.db.psycopg"), patch(
        "quant.api.routers.inst.exchange_id_for_app",
        # Only Bybit is a ccxt venue here; NASDAQ lists products but publishes
        # no market table, which is the case the empty answer is for.
        side_effect=lambda app_id, refdata=None: "bybit" if app_id == BYBIT else None,
    ):
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
        app.state.price_bars = price_bars
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


NEW_INSTRUMENT = {
    "internal_cusip": "solusdt.crypto",
    "display_nm": "Solana / USDT",
    "asset_type_id": 1,
    "ccy": "USDT",
    "app_id": BYBIT,
    "vendor_symbol": "SOLUSDT",
}

CREATED = {
    "product_id": 7,
    "product_vid": 1,
    # A column SP_GET_PRODUCT selects but the response does not carry, so
    # widening the cursor cannot quietly widen the public API.
    "is_current_ind": "Y",
    "internal_cusip": "solusdt.crypto",
    "display_nm": "Solana / USDT",
    "asset_type_id": 1,
    "exchange": None,
    "ccy": "USDT",
    "description": None,
    "app_id": BYBIT,
    "vendor_symbol": "SOLUSDT",
    "product_xref_id": 3,
    "product_xref_vid": 1,
}


def _post(client, **overrides):
    return client.post("/api/v1/inst/products", json=NEW_INSTRUMENT | overrides)


class TestCreateInstrument:
    """One submit creates a product and the first venue that lists it.

    Split in two, the product would exist and no venue-scoped list would show
    it — `/apps/{app_id}/products` is built from the xrefs — so it could not be
    subscribed to, backtested or deployed. The gap looks like a bug, which is
    why it is not a state the API can be left in.
    """

    def test_creates_both_halves_in_one_call(self, client_and_cache):
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        resp = _post(client)

        assert resp.status_code == 201
        cache.create_instrument.assert_called_once_with(
            internal_cusip="solusdt.crypto",
            display_nm="Solana / USDT",
            asset_type_id=1,
            exchange=None,
            ccy="USDT",
            description=None,
            app_id=BYBIT,
            vendor_symbol="SOLUSDT",
        )

    def test_returns_the_id_the_procedure_allocated(self, client_and_cache):
        """The caller could not have known it — there is no sequence."""
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        body = _post(client).json()

        assert body["product_id"] == 7
        assert body["product_vid"] == 1
        assert body["product_xref_id"] == 3

    def test_the_response_carries_the_venue_symbol(self, client_and_cache):
        """Proof the product is visible to that venue's list, not just stored."""
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        body = _post(client).json()

        assert body["app_id"] == BYBIT
        assert body["vendor_symbol"] == "SOLUSDT"

    def test_the_response_is_a_projection_not_the_stored_row(self, client_and_cache):
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        assert "is_current_ind" not in _post(client).json()

    def test_201_because_this_route_only_ever_creates(self, client_and_cache):
        """Unlike /market-data/subscriptions, which also enables and retargets."""
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        assert _post(client).status_code == 201


class TestCusipNormalisation:
    """The cusip is the identity every other schema stores.

    Decision #21 makes it lowercase `{symbol}.{suffix}`, and
    `UQ_PRODUCT_CUSIP_CURRENT` is case-sensitive — so `SOLUSDT.crypto` typed
    into a form would be accepted as a second, unrelated instrument and fork
    every downstream lookup silently.
    """

    def test_a_typed_cusip_is_lowercased(self, client_and_cache):
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        _post(client, internal_cusip="SOLUSDT.Crypto")

        assert (
            cache.create_instrument.call_args.kwargs["internal_cusip"]
            == "solusdt.crypto"
        )

    def test_surrounding_whitespace_is_dropped(self, client_and_cache):
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        _post(client, internal_cusip="  solusdt.crypto  ")

        assert (
            cache.create_instrument.call_args.kwargs["internal_cusip"]
            == "solusdt.crypto"
        )

    @pytest.mark.parametrize(
        "bad", ["solusdt", "solusdt.", ".crypto", "sol usdt.crypto", "sol/usdt.crypto"]
    )
    def test_a_cusip_that_is_not_symbol_dot_suffix_is_refused(
        self, client_and_cache, bad
    ):
        client, cache = client_and_cache

        assert _post(client, internal_cusip=bad).status_code == 422
        cache.create_instrument.assert_not_called()

    def test_an_exchange_specific_suffix_is_still_allowed(self, client_and_cache):
        """The docs give suffixes as examples, not a closed set — a perp names
        its venue because margin and settlement genuinely differ there."""
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        assert _post(client, internal_cusip="btc-perp.binance").status_code == 201


class TestOptionalFieldsAndRequirements:
    def test_a_blank_optional_field_is_stored_as_absent(self, client_and_cache):
        """`EXCHANGE = ''` would satisfy "NULL on .crypto spot" to the letter
        and break it in practice — nothing downstream tests for empty."""
        client, cache = client_and_cache
        cache.create_instrument.return_value = CREATED

        _post(client, exchange="  ", description="")

        kwargs = cache.create_instrument.call_args.kwargs
        assert kwargs["exchange"] is None
        assert kwargs["description"] is None

    @pytest.mark.parametrize(
        "field",
        ["internal_cusip", "display_nm", "asset_type_id", "app_id", "vendor_symbol"],
    )
    def test_the_fields_an_instrument_cannot_exist_without_are_required(
        self, client_and_cache, field
    ):
        """The request model is the only thing that checks this.

        The procedures carry no required-field checks — `NOT NULL` on the
        columns is the database's half, and it reports a violation rather than
        naming the field, so a missing value has to be refused here.
        """
        client, cache = client_and_cache
        body = {k: v for k, v in NEW_INSTRUMENT.items() if k != field}

        resp = client.post("/api/v1/inst/products", json=body)

        assert resp.status_code == 422
        cache.create_instrument.assert_not_called()

    def test_a_blank_vendor_symbol_is_refused_before_the_product_is_written(
        self, client_and_cache
    ):
        """Whitespace is not a ticker, and the product would be unlisted."""
        client, cache = client_and_cache

        assert _post(client, vendor_symbol="   ").status_code == 422
        cache.create_instrument.assert_not_called()


class TestProcedureErrorsReachTheCaller:
    """`ProcedureError` already carries the sqlstate the handlers map on.

    `quant.api.exception_handlers` turns `23*` into 409, so a bespoke exception
    type here would only lose that. The messages are the ones Postgres itself
    raises: the procedures do no validation of their own, so a conflict arrives
    as the unique index reporting it rather than as prose naming the row.
    """

    def test_a_cusip_that_already_names_an_instrument_is_a_conflict(
        self, client_and_cache
    ):
        client, cache = client_and_cache
        cache.create_instrument.side_effect = ProcedureError(
            proc="INST.SP_INS_PRODUCT",
            sqlstate="23505",
            message=(
                "duplicate key value violates unique constraint "
                '"uq_product_cusip_current"'
            ),
        )

        resp = _post(client)

        assert resp.status_code == 409
        assert "uq_product_cusip_current" in resp.json()["detail"]["message"]

    def test_a_venue_that_already_lists_this_product_is_a_conflict(
        self, client_and_cache
    ):
        """One venue prints one symbol at a time, and the index is what says so.

        `UQ_PRODUCT_XREF_CURRENT` covers `(PRODUCT_ID, APP_ID)`, so a second
        open mapping for the pair is refused on write.
        """
        client, cache = client_and_cache
        cache.create_instrument.side_effect = ProcedureError(
            proc="INST.SP_INS_PRODUCT_XREF",
            sqlstate="23505",
            message=(
                "duplicate key value violates unique constraint "
                '"uq_product_xref_current"'
            ),
        )

        assert _post(client).status_code == 409


class TestVenueSymbols:
    """What the exchange lists, which is the one thing the caches cannot say.

    Every other read in this router answers from stored rows. This one cannot:
    a new instrument names a ticker the platform has never held, so the set to
    choose from only exists at the venue.
    """

    def test_offers_the_tickers_the_venue_prints(self, client_and_cache):
        client, _cache = client_and_cache

        resp = client.get(f"/api/v1/inst/apps/{BYBIT}/venue-symbols")

        assert resp.status_code == 200
        assert resp.json() == [
            {
                "vendor_symbol": "BTCUSDT",
                "base": "BTC",
                "quote": "USDT",
                "market_types": ["spot", "swap"],
            },
        ]

    def test_asks_the_venue_behind_the_app_id(self, client_and_cache, price_bars):
        client, _cache = client_and_cache

        client.get(f"/api/v1/inst/apps/{BYBIT}/venue-symbols")

        price_bars.for_app.assert_called_once_with(BYBIT)

    def test_a_venue_with_no_market_list_is_empty_not_a_404(
        self, client_and_cache, price_bars
    ):
        """A broker reached some other way is a real venue that cannot answer.

        Matching `/apps/{app_id}/products`, which returns `[]` for a venue
        listing nothing rather than treating it as a bad request. The field is
        free text either way, so an empty list costs the caller nothing.
        """
        client, _cache = client_and_cache

        resp = client.get("/api/v1/inst/apps/999/venue-symbols")

        assert resp.status_code == 200
        assert resp.json() == []
        price_bars.for_app.assert_not_called()

    def test_an_unreachable_exchange_says_so_instead_of_a_bare_500(
        self, client_and_cache, price_bars
    ):
        """502, and a sentence — the form has to know to stop waiting for a list."""
        price_bars.for_app.return_value.venue_symbols.side_effect = BarFetchError(
            "could not list markets on bybit: timeout"
        )

        client, _cache = client_and_cache

        resp = client.get(f"/api/v1/inst/apps/{BYBIT}/venue-symbols")

        assert resp.status_code == 502
        assert "could not list markets on bybit" in resp.json()["detail"]


class TestDriverErrorsReachTheCallerToo:
    """A failure before the procedure's OUT row still has to say something.

    `ProcedureError` is the procedure reporting a SQLSTATE it caught. When the
    call never gets that far the driver raises instead, and unhandled that is a
    500 whose body is `Internal Server Error` — the dialog can only show
    "Request failed with status code 500", which names no cause and suggests no
    fix.
    """

    def test_a_procedure_this_database_does_not_have_names_itself(
        self, client_and_cache
    ):
        """42883 means the environment is behind, not that the form was wrong."""
        client, cache = client_and_cache
        cache.create_instrument.side_effect = psycopg.errors.UndefinedFunction(
            "procedure inst.sp_ins_product(integer, text, text, integer, text, "
            "text, text, text, text, text, text, integer, integer) does not exist"
        )

        resp = _post(client)

        assert resp.status_code == 502
        assert resp.json()["detail"]["sqlstate"] == "42883"
        assert "sp_ins_product" in resp.json()["detail"]["message"]

    def test_a_constraint_raised_by_the_driver_is_still_a_conflict(
        self, client_and_cache
    ):
        """Same mapping either way — where it was raised is not the caller's problem."""
        client, cache = client_and_cache
        cache.create_instrument.side_effect = psycopg.errors.UniqueViolation(
            'duplicate key value violates unique constraint "uq_product_cusip_current"'
        )

        assert _post(client).status_code == 409

    def test_a_dead_connection_carries_its_message_rather_than_a_bare_500(
        self, client_and_cache
    ):
        """No SQLSTATE to map, so 502 — but the text is what makes it actionable."""
        client, cache = client_and_cache
        cache.create_instrument.side_effect = psycopg.OperationalError(
            "connection failed: Connection refused"
        )

        resp = _post(client)

        assert resp.status_code == 502
        assert "Connection refused" in resp.json()["detail"]["message"]


class TestAuthGating:
    def test_creating_an_instrument_requires_being_signed_in(self):
        """Signed-in is the whole check — an instrument has no owner.

        Without `dependency_overrides` there is no cookie, so `require_user`
        401s. It is restated on the route rather than left to the router mount,
        so a remount cannot silently open a write path.
        """
        with patch("quant.shared.db.psycopg"):
            from quant.api.auth.service import AuthService
            from quant.api.main import app

            app.state.db_conninfo = "postgresql://stub"
            app.state.data_caches = MagicMock()
            with patch.object(AuthService, "__init__", return_value=None):
                app.state.auth_service = AuthService.__new__(AuthService)

            resp = TestClient(app).post(
                "/api/v1/inst/products", json=NEW_INSTRUMENT
            )

            assert resp.status_code == 401
