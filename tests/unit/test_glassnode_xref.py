"""Glassnode PRODUCT_XREF: venue base, asset-list gate, idempotent insert."""

import pytest

from quant.data.glassnode_xref import (
    ASSET_LIST_UNAVAILABLE,
    BASES_DISAGREE,
    GLASSNODE_APP_MISSING,
    MARKETS_UNAVAILABLE,
    NO_VENUE_BASE,
    NOT_ON_GLASSNODE,
    glassnode_xref_report,
    load_venue_markets,
    map_glassnode_xrefs,
    read_glassnode_asset_symbols,
    venue_market_base,
)
from quant.market_data.fetcher import VenueMarket
from quant.shared.db import ProcedureError

BYBIT = 34
BINANCE = 35
GLASSNODE = 2
YAHOO = 1

BTC_MARKET = VenueMarket("BTCUSDT", "BTC", "USDT", ("spot", "swap"))
USDC_MARKET = VenueMarket("BTCUSDC", "BTC", "USDC", ("spot",))
PEPE_MARKET = VenueMarket("1000PEPEUSDT", "1000PEPE", "USDT", ("swap",))
WETH_MARKET = VenueMarket("WETHUSDT", "WETH", "USDT", ("spot",))
ETH_MARKET = VenueMarket("ETHUSDT", "ETH", "USDT", ("spot",))


class FakeInstruments:
    """The slice of InstrumentCache this pass calls."""

    def __init__(self, products, xrefs, *, on_insert=None):
        self._products = list(products)
        self._xrefs = list(xrefs)
        self.inserted = []
        self.refreshed = 0
        self._on_insert = on_insert

    def get_products(self):
        return list(self._products)

    def get_xrefs(self, product_id=None, app_id=None):
        rows = self._xrefs
        if product_id is not None:
            rows = [row for row in rows if row["product_id"] == product_id]
        if app_id is not None:
            rows = [row for row in rows if row["app_id"] == app_id]
        return list(rows)

    def resolve_vendor_symbol(self, product_id, app_id):
        for row in self._xrefs:
            if row["product_id"] == product_id and row["app_id"] == app_id:
                return row["vendor_symbol"]
        return None

    def sp_ins_product_xref(self, *, product_id, app_id, vendor_symbol, product_xref_id=None):
        if self._on_insert is not None:
            self._on_insert(self)
        self.inserted.append(
            {
                "product_id": product_id,
                "app_id": app_id,
                "vendor_symbol": vendor_symbol,
                "product_xref_id": product_xref_id,
            }
        )
        self._xrefs.append(
            {"product_id": product_id, "app_id": app_id, "vendor_symbol": vendor_symbol}
        )
        return 99, 1

    def refresh(self):
        self.refreshed += 1


def _product(product_id, cusip):
    return {"product_id": product_id, "internal_cusip": cusip}


def _map(cache, markets, listed, *, product_id=None, failed=(), glassnode_app_id=GLASSNODE):
    return map_glassnode_xrefs(
        cache,
        glassnode_app_id=glassnode_app_id,
        exchange_app_ids=[BYBIT, BINANCE],
        markets_by_app=markets,
        failed_app_ids=failed,
        listed_symbols=listed,
        product_id=product_id,
    )


class TestVenueMarketBase:
    """The Glassnode symbol is the venue's base, not a rewrite of the cusip."""

    def test_btcusdt_base_is_btc(self):
        assert venue_market_base("BTCUSDT", [BTC_MARKET]) == "BTC"

    def test_btcusdc_base_is_btc_without_stripping_a_quote(self):
        # BTCUSDC does not end in USDT. Stripping USDT off the cusip cannot
        # see this pair, and stripping USDC would be a second special case.
        assert venue_market_base("BTCUSDC", [USDC_MARKET, BTC_MARKET]) == "BTC"

    def test_leveraged_base_is_kept_whole(self):
        assert venue_market_base("1000PEPEUSDT", [PEPE_MARKET]) == "1000PEPE"

    def test_unknown_ticker_has_no_base(self):
        assert venue_market_base("BTCUSDT", [ETH_MARKET]) is None

    def test_empty_and_blank_inputs_have_no_base(self):
        assert venue_market_base(None, [BTC_MARKET]) is None
        assert venue_market_base("", [BTC_MARKET]) is None
        assert venue_market_base("BTCUSDT", []) is None
        blank = VenueMarket("BTCUSDT", "  ", "USDT", ("spot",))
        missing = VenueMarket("BTCUSDT", None, "USDT", ("spot",))
        assert venue_market_base("BTCUSDT", [blank]) is None
        assert venue_market_base("BTCUSDT", [missing]) is None

    def test_one_market_matches_and_the_next_does_not(self):
        markets = [ETH_MARKET, BTC_MARKET]
        assert venue_market_base("BTCUSDT", markets[:1]) is None
        assert venue_market_base("BTCUSDT", markets) == "BTC"


class TestAssetCheckAndInsert:
    def test_listed_base_is_inserted_once_in_catalog_spelling(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )
        mixed = VenueMarket("BTCUSDT", "btc", "USDT", ("spot",))

        outcomes = _map(cache, {BYBIT: [mixed]}, ["BTC"])

        assert cache.inserted == [
            {
                "product_id": 1,
                "app_id": GLASSNODE,
                "vendor_symbol": "BTC",
                "product_xref_id": None,
            }
        ]
        assert outcomes[0].wrote is True
        assert outcomes[0].skip_reason is None
        assert cache.refreshed == 1

    def test_unlisted_base_is_not_written(self):
        cache = FakeInstruments(
            [_product(1, "1000pepeusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "1000PEPEUSDT"}],
        )

        outcomes = _map(cache, {BYBIT: [PEPE_MARKET]}, ["PEPE", "BTC"])

        assert cache.inserted == []
        assert outcomes[0].wrote is False
        assert outcomes[0].skip_reason == f"1000PEPE is {NOT_ON_GLASSNODE}"
        assert "PEPE" not in {row["vendor_symbol"] for row in cache.inserted}
        assert cache.refreshed == 0

    def test_renamed_base_is_left_unmapped(self):
        # WETH is not ETH. A failed asset check does not rewrite the cusip
        # or store the lookalike.
        cache = FakeInstruments(
            [_product(1, "wethusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "WETHUSDT"}],
        )

        outcomes = _map(cache, {BYBIT: [WETH_MARKET]}, ["ETH"])

        assert cache.inserted == []
        assert outcomes[0].skip_reason == f"WETH is {NOT_ON_GLASSNODE}"

    def test_usdc_pair_uses_the_venue_base(self):
        cache = FakeInstruments(
            [_product(1, "btcusdc.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDC"}],
        )

        outcomes = _map(cache, {BYBIT: [USDC_MARKET]}, ["BTC"])

        assert outcomes[0].vendor_symbol == "BTC"
        assert cache.inserted[0]["vendor_symbol"] == "BTC"

    def test_missing_market_does_not_invent_a_base_from_the_cusip(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        outcomes = _map(cache, {BYBIT: []}, ["BTC"])

        assert cache.inserted == []
        assert outcomes[0].skip_reason == NO_VENUE_BASE

    def test_unread_asset_list_writes_nothing(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        outcomes = _map(cache, {BYBIT: [BTC_MARKET]}, None)

        assert cache.inserted == []
        assert outcomes[0].skip_reason == ASSET_LIST_UNAVAILABLE

    def test_empty_catalog_is_not_on_glassnode(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        outcomes = _map(cache, {BYBIT: [BTC_MARKET]}, [])

        assert outcomes[0].skip_reason == f"BTC is {NOT_ON_GLASSNODE}"
        assert cache.inserted == []

    def test_disagreeing_bases_are_not_written(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
                {"product_id": 1, "app_id": BINANCE, "vendor_symbol": "ETHUSDT"},
            ],
        )
        markets = {BYBIT: [BTC_MARKET], BINANCE: [ETH_MARKET]}

        outcomes = _map(cache, markets, ["BTC", "ETH"])

        assert cache.inserted == []
        assert outcomes[0].skip_reason == BASES_DISAGREE

    def test_the_same_base_on_two_venues_is_one_insert(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
                {"product_id": 1, "app_id": BINANCE, "vendor_symbol": "BTCUSDT"},
            ],
        )
        markets = {BYBIT: [BTC_MARKET], BINANCE: [BTC_MARKET]}

        _map(cache, markets, ["BTC"])

        assert len(cache.inserted) == 1

    def test_a_failed_venue_does_not_block_the_one_that_answered(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
                {"product_id": 1, "app_id": BINANCE, "vendor_symbol": "BTCUSDT"},
            ],
        )

        outcomes = _map(
            cache,
            {BINANCE: [BTC_MARKET]},
            ["BTC"],
            failed=[BYBIT],
        )

        assert outcomes[0].wrote is True
        assert cache.inserted[0]["vendor_symbol"] == "BTC"

    def test_every_venue_failing_is_markets_unavailable(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        outcomes = _map(cache, {}, ["BTC"], failed=[BYBIT])

        assert outcomes[0].skip_reason == MARKETS_UNAVAILABLE
        assert cache.inserted == []

    def test_no_glassnode_app_writes_nothing(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        outcomes = _map(cache, {BYBIT: [BTC_MARKET]}, ["BTC"], glassnode_app_id=None)

        assert outcomes[0].skip_reason == GLASSNODE_APP_MISSING
        assert cache.inserted == []


class TestIdempotentInsert:
    def test_a_current_row_is_left_alone(self):
        # Even when the venue base would now be a different asset. Versioning
        # the row would change the symbol the daily fill already uses.
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"},
                {"product_id": 1, "app_id": GLASSNODE, "vendor_symbol": "BTC"},
            ],
        )

        outcomes = _map(cache, {BYBIT: [ETH_MARKET]}, ["ETH", "BTC"])

        assert cache.inserted == []
        assert outcomes[0].wrote is False
        assert outcomes[0].vendor_symbol == "BTC"
        assert outcomes[0].skip_reason is None
        assert cache.refreshed == 0

    def test_a_unique_violation_keeps_the_row_that_won(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        def lose_the_race(fake):
            fake._xrefs.append(
                {"product_id": 1, "app_id": GLASSNODE, "vendor_symbol": "BTC"}
            )
            raise ProcedureError(
                proc="INST.SP_INS_PRODUCT_XREF",
                sqlstate="23505",
                message="duplicate key value violates unique constraint",
            )

        cache._on_insert = lose_the_race

        outcomes = _map(cache, {BYBIT: [BTC_MARKET]}, ["BTC"])

        assert cache.inserted == []
        assert outcomes[0].wrote is False
        assert outcomes[0].vendor_symbol == "BTC"
        assert outcomes[0].skip_reason is None

    def test_a_non_unique_procedure_error_propagates(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        def fail(fake):
            raise ProcedureError(
                proc="INST.SP_INS_PRODUCT_XREF",
                sqlstate="23502",
                message="null value in column",
            )

        cache._on_insert = fail

        with pytest.raises(ProcedureError, match="null value") as raised:
            _map(cache, {BYBIT: [BTC_MARKET]}, ["BTC"])
        assert raised.value.sqlstate == "23502"

    def test_a_unique_violation_with_no_row_afterwards_is_a_skip(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        def lose_and_vanish(_fake):
            raise ProcedureError(
                proc="INST.SP_INS_PRODUCT_XREF",
                sqlstate="23505",
                message="duplicate key value violates unique constraint",
            )

        cache._on_insert = lose_and_vanish

        outcomes = _map(cache, {BYBIT: [BTC_MARKET]}, ["BTC"])

        assert cache.inserted == []
        assert outcomes[0].wrote is False
        assert outcomes[0].vendor_symbol is None
        assert "duplicate key" in (outcomes[0].skip_reason or "")


class TestBackfill:
    def test_existing_btc_is_kept_and_a_listed_coin_is_added(self):
        products = [
            _product(1, "btcusdt.crypto"),
            _product(2, "ethusdt.crypto"),
            _product(3, "1000pepeusdt.crypto"),
            _product(4, "ibit.nasdaq"),
        ]
        xrefs = [
            {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
            {"product_id": 1, "app_id": GLASSNODE, "vendor_symbol": "BTC"},
            {"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"},
            {"product_id": 3, "app_id": BYBIT, "vendor_symbol": "1000PEPEUSDT"},
            {"product_id": 4, "app_id": YAHOO, "vendor_symbol": "IBIT"},
        ]
        cache = FakeInstruments(products, xrefs)
        markets = {
            BYBIT: [BTC_MARKET, ETH_MARKET, PEPE_MARKET],
        }

        outcomes = _map(cache, markets, ["BTC", "ETH"])
        report = glassnode_xref_report(outcomes)

        assert [row["internal_cusip"] for row in report["already_mapped"]] == [
            "btcusdt.crypto"
        ]
        assert report["mapped"] == [
            {
                "product_id": 2,
                "internal_cusip": "ethusdt.crypto",
                "vendor_symbol": "ETH",
            }
        ]
        assert report["skipped"] == [
            {
                "product_id": 3,
                "internal_cusip": "1000pepeusdt.crypto",
                "vendor_symbol": None,
                "reason": f"1000PEPE is {NOT_ON_GLASSNODE}",
            }
        ]
        assert cache.inserted == [
            {
                "product_id": 2,
                "app_id": GLASSNODE,
                "vendor_symbol": "ETH",
                "product_xref_id": None,
            }
        ]

    def test_one_product_limits_the_pass(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto"), _product(2, "ethusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
                {"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"},
            ],
        )
        markets = {BYBIT: [BTC_MARKET, ETH_MARKET]}

        outcomes = _map(cache, markets, ["BTC", "ETH"], product_id=2)

        assert [row.product_id for row in outcomes] == [2]
        assert cache.inserted[0]["vendor_symbol"] == "ETH"

    def test_no_products_is_an_empty_pass(self):
        cache = FakeInstruments([], [])

        assert _map(cache, {BYBIT: [BTC_MARKET]}, ["BTC"]) == []
        assert cache.inserted == []

    def test_two_writes_reload_the_cache_once(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto"), _product(2, "ethusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
                {"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"},
            ],
        )

        outcomes = _map(cache, {BYBIT: [BTC_MARKET, ETH_MARKET]}, ["BTC", "ETH"])

        assert [outcome.wrote for outcome in outcomes] == [True, True]
        assert cache.refreshed == 1

    def test_a_failed_cache_reload_does_not_skip_the_next_product(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto"), _product(2, "ethusdt.crypto")],
            [
                {"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"},
                {"product_id": 2, "app_id": BYBIT, "vendor_symbol": "ETHUSDT"},
            ],
        )

        def refresh():
            cache.refreshed += 1
            raise RuntimeError("cache reload failed")

        cache.refresh = refresh

        outcomes = _map(cache, {BYBIT: [BTC_MARKET, ETH_MARKET]}, ["BTC", "ETH"])

        assert cache.refreshed == 1
        assert [row["vendor_symbol"] for row in cache.inserted] == ["BTC", "ETH"]
        assert [outcome.wrote for outcome in outcomes] == [True, True]

    def test_a_product_id_the_cache_does_not_hold_is_an_empty_pass(self):
        cache = FakeInstruments(
            [_product(1, "btcusdt.crypto")],
            [{"product_id": 1, "app_id": BYBIT, "vendor_symbol": "BTCUSDT"}],
        )

        assert _map(cache, {BYBIT: [BTC_MARKET]}, ["BTC"], product_id=99) == []
        assert cache.inserted == []


class TestVenueMarketLoad:
    def test_one_venue_failing_leaves_the_other(self):
        def markets_for_app(app_id):
            if app_id == BYBIT:
                raise RuntimeError("bybit down")
            return [ETH_MARKET]

        loaded, failed = load_venue_markets([BYBIT, BINANCE], markets_for_app)

        assert failed == {BYBIT}
        assert loaded[BINANCE] == [ETH_MARKET]
        assert BYBIT not in loaded

    def test_zero_apps_loads_nothing(self):
        loaded, failed = load_venue_markets([], lambda app_id: [BTC_MARKET])

        assert loaded == {}
        assert failed == set()


class TestAssetListRead:
    def test_the_decision_module_does_not_construct_a_client(self):
        import inspect

        import quant.data.glassnode_xref as decision

        assert "Glassnode(" not in inspect.getsource(decision)

    def test_a_caller_can_pass_the_asset_catalog(self):
        def reader():
            raise AssertionError("reader must not be called")

        # Spelling is the caller's, after a strip. Casefold happens at lookup.
        assert read_glassnode_asset_symbols(["BTC", " eth "], reader=reader) == ["BTC", "eth"]

    def test_no_reader_and_no_catalog_is_unread(self):
        assert read_glassnode_asset_symbols() is None
        assert read_glassnode_asset_symbols(None) is None

    def test_an_empty_catalog_is_empty_not_unread(self):
        assert read_glassnode_asset_symbols([]) == []

    def test_one_symbol_is_kept(self):
        assert read_glassnode_asset_symbols(["BTC"]) == ["BTC"]

    def test_a_blank_and_a_non_string_are_dropped(self):
        assert read_glassnode_asset_symbols(["", "  ", 1, "BTC"]) == ["BTC"]

    def test_a_reader_failure_is_an_unread_catalog(self):
        def reader():
            raise ValueError("GLASSNODE_API_KEY is not set")

        assert read_glassnode_asset_symbols(reader=reader) is None

    def test_none_from_the_reader_is_unread(self):
        assert read_glassnode_asset_symbols(reader=lambda: None) is None

    def test_a_missing_key_is_an_unread_catalog(self, monkeypatch):
        monkeypatch.delenv("GLASSNODE_API_KEY", raising=False)

        def reader():
            from quant.data.sources import Glassnode

            return Glassnode().list_asset_symbols(timeout_s=2)

        assert read_glassnode_asset_symbols(reader=reader) is None
