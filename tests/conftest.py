import pytest
import pandas as pd
import numpy as np

from quant.refdata.reader import RedisRefData

#: Shaped like the Redis snapshot: PERIOD_LENGTH arrives stringified, because
#: the publisher serialises Postgres intervals with ``json.dumps(default=str)``.
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
        assert table == "tm_interval"
        return self._rows


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
