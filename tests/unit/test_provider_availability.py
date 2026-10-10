"""The Data tab reads provider windows without the JSON body."""

from unittest.mock import MagicMock

from quant.data.backtest_cache import BacktestCache


def test_list_availability_calls_the_window_procedure():
    cache = BacktestCache.__new__(BacktestCache)
    cache._call_get = MagicMock(return_value=[{"internal_cusip": "btcusdt.crypto"}])

    rows = cache.list_availability()

    cache._call_get.assert_called_once_with(
        "CALL BT.SP_GET_API_REQUEST_AVAILABILITY(NULL, NULL, NULL, NULL)",
        (),
    )
    assert rows == [{"internal_cusip": "btcusdt.crypto"}]
