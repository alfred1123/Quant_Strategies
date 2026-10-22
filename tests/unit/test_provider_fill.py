"""The scheduled fill calls fetch_df only for providers the checkbox cannot."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from quant.data.provider_fill import (
    ASSET_LIST_UNAVAILABLE,
    BASES_DISAGREE,
    MARKETS_UNAVAILABLE,
    NO_VENUE_BASE,
    ExchangeListing,
    fill_scheduled_providers,
    resolve_provider_symbol,
    scheduled_provider_apps,
)

APPS = [
    {"app_id": 1, "name": "yahoo", "is_exchange_ind": "N", "refresh_dataset_ind": "Y"},
    {"app_id": 2, "name": "glassnode", "is_exchange_ind": "N", "refresh_dataset_ind": "N"},
    {"app_id": 34, "name": "bybit", "is_exchange_ind": "Y", "refresh_dataset_ind": "N"},
]
METRICS = [
    {"app_id": 2, "metric_nm": "price", "metric_path": "market/price_usd_close"},
    {"app_id": 2, "metric_nm": "sopr", "metric_path": "indicators/sopr"},
    {"app_id": 2, "metric_nm": "unused", "metric_path": None},
    {"app_id": 1, "metric_nm": "price", "metric_path": None},
]


def test_scheduled_apps_are_non_exchange_and_refresh_off():
    names = [app["name"] for app in scheduled_provider_apps(APPS)]
    assert names == ["glassnode"]


def _fill(refdata, inst, **kwargs):
    kwargs.setdefault("exchange_app_ids", [])
    kwargs.setdefault("markets_for_app", lambda _app_id: [])
    bt_cache = MagicMock()
    bt_cache.default_tm_interval_id.return_value = 1
    return fill_scheduled_providers(
        refdata, inst, bt_cache, since=date(2010, 1, 1), today=date(2026, 10, 10), **kwargs,
    )


def test_fill_inserts_each_catalog_metric_for_each_xref():
    refdata = MagicMock()
    refdata.get.side_effect = lambda table: APPS if table == "app" else METRICS
    inst = MagicMock()
    inst.get_products.return_value = []
    inst.get_xrefs.return_value = [{"product_id": 9, "app_id": 2, "vendor_symbol": "BTC"}]
    inst.get_product_by_id.return_value = {"product_id": 9, "internal_cusip": "btcusdt.crypto"}
    frame = pd.DataFrame({"price": [1.0]})

    with patch("quant.strategy.backtest_service.fetch_df", return_value=frame) as fetch:
        report = _fill(refdata, inst)

    assert report.filled == 2
    assert report.failed == 0
    inst.get_xrefs.assert_called_once_with(app_id=2)
    calls = [c.kwargs for c in fetch.call_args_list]
    assert calls == [
        {
            "refresh": True,
            "tm_interval_id": 1,
            "metric_nm": "price",
        },
        {
            "refresh": True,
            "tm_interval_id": 1,
            "metric_nm": "sopr",
        },
    ]
    assert fetch.call_args_list[0].args[:4] == (
        "btcusdt.crypto", "2010-01-01", "2026-10-10", "glassnode",
    )


def test_one_failed_series_does_not_stop_the_next():
    refdata = MagicMock()
    refdata.get.side_effect = lambda table: APPS if table == "app" else METRICS
    inst = MagicMock()
    inst.get_products.return_value = []
    inst.get_xrefs.return_value = [{"product_id": 9}]
    inst.get_product_by_id.return_value = {"internal_cusip": "btcusdt.crypto"}

    with patch(
        "quant.strategy.backtest_service.fetch_df",
        side_effect=[RuntimeError("glassnode down"), pd.DataFrame({"price": [1.0]})],
    ):
        report = _fill(refdata, inst)

    assert report.filled == 1
    assert report.failed == 1
    assert "price" in report.errors[0]


def _listing(base: str | None, *, failed: bool = False) -> ExchangeListing:
    return ExchangeListing(
        vendor_symbol="BTCUSDT" if base != "ETH" else "ETHUSDT",
        base=base,
        markets_unavailable=failed,
    )


def test_the_same_base_on_two_quotes_is_one_symbol():
    decision = resolve_provider_symbol(
        [
            ExchangeListing("BTCUSDT", "BTC"),
            ExchangeListing("BTCUSDC", "BTC"),
        ],
        listed_symbols=["btc"],
        existing_symbol=None,
    )

    assert decision.write is True
    assert decision.vendor_symbol == "btc"
    assert decision.skip_reason is None


def test_a_base_the_provider_does_not_list_is_not_written():
    decision = resolve_provider_symbol(
        [ExchangeListing("1000PEPEUSDT", "1000PEPE")],
        listed_symbols=["PEPE"],
        existing_symbol=None,
    )

    assert decision.write is False
    assert decision.vendor_symbol is None
    assert decision.skip_reason == "1000PEPE is not a listed asset"


def test_disagreeing_bases_are_not_collapsed():
    decision = resolve_provider_symbol(
        [ExchangeListing("BTCUSDT", "BTC"), ExchangeListing("ETHUSDT", "ETH")],
        listed_symbols=["BTC", "ETH"],
        existing_symbol=None,
    )

    assert decision.write is False
    assert decision.skip_reason == BASES_DISAGREE


def test_an_existing_symbol_is_left_alone():
    decision = resolve_provider_symbol(
        [ExchangeListing("BTCUSDT", "ETH")],
        listed_symbols=["ETH"],
        existing_symbol="BTC",
    )

    assert decision.write is False
    assert decision.vendor_symbol == "BTC"
    assert decision.skip_reason is None


def test_an_unread_asset_list_is_not_an_empty_catalog():
    unread = resolve_provider_symbol(
        [_listing("BTC")],
        listed_symbols=None,
        existing_symbol=None,
    )
    empty = resolve_provider_symbol(
        [_listing("BTC")],
        listed_symbols=[],
        existing_symbol=None,
    )

    assert unread.skip_reason == ASSET_LIST_UNAVAILABLE
    assert empty.skip_reason == "BTC is not a listed asset"
    assert unread.write is False
    assert empty.write is False


def test_a_failed_market_table_does_not_invent_a_base():
    decision = resolve_provider_symbol(
        [ExchangeListing("BTCUSDT", None, markets_unavailable=True)],
        listed_symbols=["BTC"],
        existing_symbol=None,
    )

    assert decision.skip_reason == MARKETS_UNAVAILABLE
    assert decision.write is False


def test_a_ticker_with_no_base_is_not_the_cusip():
    decision = resolve_provider_symbol(
        [ExchangeListing("BTCUSDT", None)],
        listed_symbols=["BTC"],
        existing_symbol=None,
    )

    assert decision.skip_reason == NO_VENUE_BASE


def test_no_listing_has_no_symbol():
    decision = resolve_provider_symbol(
        [],
        listed_symbols=["BTC"],
        existing_symbol=None,
    )

    assert decision.skip_reason == NO_VENUE_BASE
    assert decision.write is False


def test_a_missing_symbol_is_written_then_fetched():
    refdata = MagicMock()
    refdata.get.side_effect = lambda table: APPS if table == "app" else METRICS
    product = {"product_id": 9, "internal_cusip": "btcusdt.crypto"}
    xrefs = [{"product_id": 9, "app_id": 34, "vendor_symbol": "BTCUSDT"}]
    inst = MagicMock()
    inst.get_products.return_value = [product]
    inst.get_product_by_id.return_value = product
    inst.resolve_vendor_symbol.return_value = None

    def get_xrefs(product_id=None, app_id=None):
        rows = xrefs
        if product_id is not None:
            rows = [row for row in rows if row["product_id"] == product_id]
        if app_id is not None:
            rows = [row for row in rows if row["app_id"] == app_id]
        return rows

    inst.get_xrefs.side_effect = get_xrefs

    def insert(*, product_id, app_id, vendor_symbol, product_xref_id=None):
        xrefs.append(
            {"product_id": product_id, "app_id": app_id, "vendor_symbol": vendor_symbol}
        )
        return 1, 1

    inst.sp_ins_product_xref.side_effect = insert
    frame = pd.DataFrame({"price": [1.0]})

    with patch("quant.data.provider_fill.listed_asset_symbols", return_value=["btc"]), \
            patch("quant.strategy.backtest_service.fetch_df", return_value=frame) as fetch:
        report = _fill(
            refdata,
            inst,
            exchange_app_ids=[34],
            markets_for_app=lambda _app_id: [("BTCUSDT", "BTC")],
        )

    inst.sp_ins_product_xref.assert_called_once_with(
        product_id=9, app_id=2, vendor_symbol="btc",
    )
    inst.refresh.assert_called_once()
    assert report.filled == 2
    assert report.failed == 0
    assert fetch.call_args_list[0].args[0] == "btcusdt.crypto"


def test_a_base_the_provider_does_not_list_is_not_fetched():
    refdata = MagicMock()
    refdata.get.side_effect = lambda table: APPS if table == "app" else METRICS
    product = {"product_id": 9, "internal_cusip": "1000pepeusdt.crypto"}
    inst = MagicMock()
    inst.get_products.return_value = [product]
    inst.resolve_vendor_symbol.return_value = None
    inst.get_xrefs.side_effect = lambda product_id=None, app_id=None: (
        [{"product_id": 9, "app_id": 34, "vendor_symbol": "1000PEPEUSDT"}]
        if app_id is None else []
    )

    with patch("quant.data.provider_fill.listed_asset_symbols", return_value=["PEPE"]), \
            patch("quant.strategy.backtest_service.fetch_df") as fetch:
        report = _fill(
            refdata,
            inst,
            exchange_app_ids=[34],
            markets_for_app=lambda _app_id: [("1000PEPEUSDT", "1000PEPE")],
        )

    inst.sp_ins_product_xref.assert_not_called()
    fetch.assert_not_called()
    assert report.filled == 0
