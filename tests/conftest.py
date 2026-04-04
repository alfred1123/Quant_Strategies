import pytest
import pandas as pd
import numpy as np


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
    })


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
    })


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
    })
