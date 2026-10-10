"""The scheduled fill calls fetch_df only for providers the checkbox cannot."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from quant.data.provider_fill import fill_scheduled_providers, scheduled_provider_apps

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


def test_fill_inserts_each_catalog_metric_for_each_xref():
    refdata = MagicMock()
    refdata.get.side_effect = lambda table: APPS if table == "app" else METRICS
    inst = MagicMock()
    inst.get_xrefs.return_value = [{"product_id": 9, "app_id": 2, "vendor_symbol": "BTC"}]
    inst.get_product_by_id.return_value = {"product_id": 9, "internal_cusip": "btcusdt.crypto"}
    frame = pd.DataFrame({"price": [1.0]})

    with patch("quant.strategy.backtest_service.fetch_df", return_value=frame) as fetch:
        report = fill_scheduled_providers(
            refdata, inst, MagicMock(), since=date(2010, 1, 1), today=date(2026, 10, 10),
        )

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
    inst.get_xrefs.return_value = [{"product_id": 9}]
    inst.get_product_by_id.return_value = {"internal_cusip": "btcusdt.crypto"}

    with patch(
        "quant.strategy.backtest_service.fetch_df",
        side_effect=[RuntimeError("glassnode down"), pd.DataFrame({"price": [1.0]})],
    ):
        report = fill_scheduled_providers(
            refdata, inst, MagicMock(), since=date(2010, 1, 1), today=date(2026, 10, 10),
        )

    assert report.filled == 1
    assert report.failed == 1
    assert "price" in report.errors[0]
