"""Backtests fitted on the series they will be traded on.

A crypto strategy executes against an exchange order book but could only ever
be *fitted* on a data provider's series, because ``fetch_df`` had one path and
it went through ``quant/data/sources.py``. Nothing reported the substitution:
the deployment dialog showed a provider symbol next to a Bybit account and the
numbers behind the two were never the same numbers.

These tests pin the exchange branch — what it reads, and the four ways it
refuses rather than quietly returning a series that is not the one requested.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quant.strategy.backtest_service import BacktestError, fetch_df

BYBIT = {
    "app_id": 34,
    "name": "bybit",
    "class_name": "Bybit",
    "is_exchange_ind": "Y",
}
YAHOO = {
    "app_id": 1,
    "name": "yahoo",
    "class_name": "YahooFinance",
    "is_exchange_ind": "N",
}


def _bars(start="2020-04-01", periods=5) -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq="D", tz="UTC", name="datetime")
    return pd.DataFrame(
        {
            "price": range(periods),
            "factor": range(periods),
            "Open": range(periods),
            "High": range(periods),
            "Low": range(periods),
            "Close": range(periods),
            "Volume": range(periods),
        },
        index=idx,
    )


@pytest.fixture
def refdata():
    cache = MagicMock()
    cache.get.return_value = [BYBIT, YAHOO]
    cache.resolve_interval_id.return_value = 1
    return cache


@pytest.fixture
def inst_cache():
    cache = MagicMock()
    cache.resolve_internal_cusip.return_value = "BTCUSDT"
    return cache


@pytest.fixture
def bar_services():
    factory = MagicMock()
    service = factory.for_app.return_value
    service.stored_bounds.return_value = (
        datetime(2020, 3, 25, tzinfo=UTC),
        datetime(2026, 8, 29, tzinfo=UTC),
    )
    service.read_bars.return_value = _bars()
    return factory


class TestExchangeSourceReadsCapturedBars:
    def test_bars_come_from_the_price_bar_table(self, refdata, inst_cache, bar_services):
        df = fetch_df(
            "btcusdt.crypto", "2020-04-01", "2020-04-05", "bybit",
            refdata, inst_cache, bt_cache=MagicMock(), bar_services=bar_services,
        )

        assert list(df.columns) == [
            "price", "factor", "Open", "High", "Low", "Close", "Volume",
        ]
        bar_services.for_app.assert_called_once_with(34)
        kwargs = bar_services.for_app.return_value.read_bars.call_args.kwargs
        assert kwargs["internal_cusip"] == "btcusdt.crypto"
        assert kwargs["source_app_id"] == 34
        assert kwargs["tm_interval_id"] == 1

    def test_the_daily_interval_is_resolved_not_hardcoded(
        self, refdata, inst_cache, bar_services
    ):
        fetch_df(
            "btcusdt.crypto", "2020-04-01", "2020-04-05", "bybit",
            refdata, inst_cache, bar_services=bar_services,
        )

        refdata.resolve_interval_id.assert_called_once_with(timedelta(days=1))

    def test_the_backtest_cache_is_bypassed(self, refdata, inst_cache, bar_services):
        """PRICE_BAR is already the store — copying it into BT.API_REQUEST
        would make a second, divergeable version of the same fact."""
        bt_cache = MagicMock()

        fetch_df(
            "btcusdt.crypto", "2020-04-01", "2020-04-05", "bybit",
            refdata, inst_cache, bt_cache, bar_services=bar_services,
        )

        bt_cache.read_payload.assert_not_called()
        bt_cache.refresh_payload.assert_not_called()

    def test_a_provider_source_still_takes_the_provider_path(
        self, refdata, inst_cache, bar_services
    ):
        bt_cache = MagicMock()
        bt_cache.refdata.resolve_app_metric_id.return_value = 7
        bt_cache.read_payload.return_value = _bars()

        fetch_df(
            "btcusdt.crypto", "2020-04-01", "2020-04-05", "yahoo",
            refdata, inst_cache, bt_cache, bar_services=bar_services,
        )

        bt_cache.read_payload.assert_called_once()
        bar_services.for_app.assert_not_called()


class TestItRefusesRatherThanSubstitute:
    """Every refusal here has the same shape: the store cannot serve the
    requested series, and a shorter or different one is not an answer."""

    def test_uncaptured_series_points_at_the_market_data_page(
        self, refdata, inst_cache, bar_services
    ):
        bar_services.for_app.return_value.stored_bounds.return_value = None

        with pytest.raises(BacktestError, match="Market data page"):
            fetch_df(
                "btcusdt.crypto", "2020-04-01", "2020-04-05", "bybit",
                refdata, inst_cache, bar_services=bar_services,
            )

    def test_a_range_older_than_the_listing_names_what_is_covered(
        self, refdata, inst_cache, bar_services
    ):
        """Bybit's BTCUSDT starts 2020-03-25 and no backfill reaches behind
        it, so a 2016 request is answered with the real bounds, not 2020 bars
        silently relabelled as the requested range."""
        with pytest.raises(BacktestError, match=r"cover 2020-03-25 to 2026-08-29"):
            fetch_df(
                "btcusdt.crypto", "2016-01-01", "2026-01-01", "bybit",
                refdata, inst_cache, bar_services=bar_services,
            )

    def test_an_unlisted_factor_is_told_to_pick_its_own_source(
        self, refdata, inst_cache, bar_services
    ):
        """A ^VIX filter inheriting the traded product's venue: only the
        product being traded has to follow the venue it executes on."""
        inst_cache.resolve_internal_cusip.return_value = None

        with pytest.raises(BacktestError, match="not listed on bybit"):
            fetch_df(
                "^vix", "2020-04-01", "2020-04-05", "bybit",
                refdata, inst_cache, bar_services=bar_services,
            )

    def test_no_bar_source_configured_is_an_error_not_a_provider_fallback(
        self, refdata, inst_cache
    ):
        with pytest.raises(BacktestError, match="no price bar source"):
            fetch_df(
                "btcusdt.crypto", "2020-04-01", "2020-04-05", "bybit",
                refdata, inst_cache, bar_services=None,
            )
