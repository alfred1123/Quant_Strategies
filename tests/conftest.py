import pytest
import pandas as pd
import numpy as np

from quant.refdata.reader import RedisRefData

#: Shaped like the Redis snapshot: PERIOD_LENGTH arrives stringified, because
#: the publisher serialises Postgres intervals with ``json.dumps(default=str)``.
MARKET_CALENDAR_ROWS = [
    {
        "listing_exchange": "",
        "bar_timezone": "UTC",
        "market_open_time": None,
        "market_close_time": None,
    }
]

APP_APPLY_TIMING_ROWS = [
    {"app_id": 10, "tm_interval_id": 1, "execute_offset": "0:05:00"},
    {"app_id": 10, "tm_interval_id": 2, "execute_offset": "0:05:00"},
]

#: ``CONFIG.SETTING`` as seeded in ``db/liquidbase/config/data/SETTING.sql``.
SETTING_ROWS = [
    {"setting_nm": "min_metric_obs", "setting_value": "60"},
    {"setting_nm": "max_queued_per_user", "setting_value": "30"},
    {"setting_nm": "default_tm_interval_id", "setting_value": "1"},
    {"setting_nm": "fallback_settlement_ccy", "setting_value": "USDT"},
    {"setting_nm": "order_max_attempts", "setting_value": "5"},
    {"setting_nm": "order_retry_backoff_s", "setting_value": "2.0"},
    {"setting_nm": "tick_max_attempts", "setting_value": "3"},
    {"setting_nm": "tick_retry_backoff_s", "setting_value": "5.0"},
    {"setting_nm": "fill_confirm_delays_s", "setting_value": "0.3,0.6,1.2,2.4,3.5"},
]

QUEUE_PRIORITY_ROWS = [
    {"name": "normal", "display_name": "Normal", "priority": 100},
    {"name": "high", "display_name": "High", "priority": 0},
]

SCHEDULE_STATUS_ROWS = [
    {"name": "PENDING", "display_name": "Pending"},
    {"name": "SUCCESS", "display_name": "Success"},
    {"name": "FAILED", "display_name": "Failed"},
]

#: ``REFDATA.INDICATOR`` / ``SIGNAL_TYPE`` / ``ASSET_TYPE`` as seeded in
#: ``db/liquidbase/refdata/data/`` — what the CLI and ``build_config`` read.
INDICATOR_ROWS = [
    {"name": "bollinger", "display_name": "Bollinger Band (z-score)", "method_name": "get_bollinger_band",
     "win_min": 10, "win_max": 100, "win_step": 5, "sig_min": 0.25, "sig_max": 2.50, "sig_step": 0.25,
     "is_bounded_ind": "N"},
    {"name": "sma", "display_name": "SMA", "method_name": "get_sma",
     "win_min": 5, "win_max": 200, "win_step": 5, "sig_min": 0.00, "sig_max": 0.10, "sig_step": 0.01,
     "is_bounded_ind": "N"},
    {"name": "ema", "display_name": "EMA", "method_name": "get_ema",
     "win_min": 5, "win_max": 200, "win_step": 5, "sig_min": 0.00, "sig_max": 0.10, "sig_step": 0.01,
     "is_bounded_ind": "N"},
    {"name": "rsi", "display_name": "RSI", "method_name": "get_rsi",
     "win_min": 5, "win_max": 50, "win_step": 1, "sig_min": None, "sig_max": None, "sig_step": 5.00,
     "is_bounded_ind": "Y"},
]

SIGNAL_TYPE_ROWS = [
    {"name": "momentum", "display_name": "Momentum",
     "func_name_band": "momentum_band_signal", "func_name_bounded": "momentum_bounded_signal"},
    {"name": "reversion", "display_name": "Reversion",
     "func_name_band": "reversion_band_signal", "func_name_bounded": "reversion_bounded_signal"},
]

ASSET_TYPE_ROWS = [
    {"name": "crypto", "display_name": "Crypto (365 days/year)", "trading_period": 365},
    {"name": "equity", "display_name": "Equity (252 trading days/year)", "trading_period": 252},
]

TM_INTERVAL_ROWS = [
    {
        "tm_interval_id": 1,
        "name": "DAILY",
        "display_name": "Daily",
        "period_length": "1 day, 0:00:00",
    },
    {
        "tm_interval_id": 2,
        "name": "1H",
        "display_name": "Hourly",
        "period_length": "1:00:00",
    },
]


class StubRefData(RedisRefData):
    """A real reader over a fixed snapshot — no Redis, no stubbed lookups.

    Subclassed rather than mocked so tests exercise the shipped interval
    resolution, including the string parsing of ``PERIOD_LENGTH``. A
    ``MagicMock`` would answer every lookup with agreement, which is the
    opposite of what a guard built on those lookups needs to be tested against.
    """

    def __init__(self, rows=None) -> None:
        self._rows = TM_INTERVAL_ROWS if rows is None else rows

    def get(self, table: str) -> list[dict]:
        if table == "tm_interval":
            return self._rows
        if table == "market_calendar":
            return MARKET_CALENDAR_ROWS
        if table == "app":
            return []
        if table == "indicator":
            return INDICATOR_ROWS
        if table == "signal_type":
            return SIGNAL_TYPE_ROWS
        if table == "asset_type":
            return ASSET_TYPE_ROWS
        if table == "queue_priority":
            return QUEUE_PRIORITY_ROWS
        if table == "schedule_status":
            return SCHEDULE_STATUS_ROWS
        raise AssertionError(f"unexpected REFDATA table {table!r}")

    def get_config(self, table: str) -> list[dict]:
        if table == "app_apply_timing":
            return APP_APPLY_TIMING_ROWS
        if table == "setting":
            return SETTING_ROWS
        raise AssertionError(f"unexpected CONFIG table {table!r}")


@pytest.fixture
def refdata_stub():
    return StubRefData()


def _daily_index(n, start="2020-01-01"):
    """Generate a daily DatetimeIndex for n rows."""
    return pd.date_range(start, periods=n, freq="D", name="datetime")


@pytest.fixture
def sample_price_series():
    """Simple monotonically increasing price series for basic tests."""
    np.random.seed(42)
    n = 100
    prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.Series(prices, name="price")


@pytest.fixture
def sample_ohlc_df():
    """DataFrame with Open, High, Low, Close, factor, and price columns."""
    np.random.seed(42)
    n = 100
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1

    return pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "price": close,
        "factor": close,
    }, index=_daily_index(n))


@pytest.fixture
def simple_factor_df():
    """Minimal DataFrame with a known 'factor' column for deterministic indicator tests."""
    return pd.DataFrame({
        "factor": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
    })


@pytest.fixture
def trending_up_df():
    """Steadily rising price series — should produce positive returns."""
    n = 200
    prices = np.linspace(100, 200, n)
    return pd.DataFrame({
        "price": prices,
        "factor": prices,
        "Close": prices,
        "High": prices + 1,
        "Low": prices - 1,
    }, index=_daily_index(n))


@pytest.fixture
def trending_down_df():
    """Steadily falling price series — should produce negative buy-and-hold."""
    n = 200
    prices = np.linspace(200, 100, n)
    return pd.DataFrame({
        "price": prices,
        "factor": prices,
        "Close": prices,
        "High": prices + 1,
        "Low": prices - 1,
    }, index=_daily_index(n))


@pytest.fixture
def multi_factor_df():
    """DataFrame with two distinct factor columns for multi-factor tests."""
    np.random.seed(42)
    n = 100
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    volume = 1000 + np.cumsum(np.random.randn(n) * 50)
    return pd.DataFrame({
        "price": close,
        "factor": close,
        "v": close,
        "volume": volume,
        "Close": close,
        "High": close + np.abs(np.random.randn(n) * 0.3),
        "Low": close - np.abs(np.random.randn(n) * 0.3),
    }, index=_daily_index(n))
