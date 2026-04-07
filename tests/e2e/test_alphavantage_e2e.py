"""
E2E tests: hit the real Alpha Vantage API → run data through the full
backtest pipeline (ta → strategy → performance).

These tests require:
  - A valid ALPHAVANTAGE_API_KEY in .env
  - Network access

Run explicitly:
  python -m pytest tests/e2e/ -v -m e2e

They are skipped by default in `python -m pytest tests/` unless
the -m e2e marker is specified.
"""

import os
import time

import numpy as np
import pandas as pd
import pytest
from dotenv import load_dotenv

from data import AlphaVantage
from strat import TechnicalAnalysis, Strategy
from perf import Performance

# Load .env so we can check for the key
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

_has_key = bool(os.getenv('ALPHAVANTAGE_API_KEY'))

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def av():
    """AlphaVantage client — skips entire module if no API key."""
    if not _has_key:
        pytest.skip("ALPHAVANTAGE_API_KEY not set — skipping E2E tests")
    client = AlphaVantage()
    client.get_historical_price.cache_clear()
    return client


@pytest.fixture(autouse=True)
def _throttle():
    """Pause between tests to respect the free-tier rate limit (1 req/sec)."""
    yield
    time.sleep(1.5)


# ── Contract tests: verify real API response shape ──────────────────


class TestAlphaVantageContract:
    """Validate that the real API returns the expected schema.

    Note: Free tier returns ~100 most recent trading days only (compact).
    Test dates must be within this window.
    """

    def test_equity_daily_returns_t_v_columns(self, av):
        # Use recent dates within the free-tier compact window
        df = av.get_historical_price("IBM", "2026-03-01", "2026-03-31")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["t", "v"]
        assert len(df) > 0
        # Dates should be strings in YYYY-MM-DD format
        assert df["t"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()
        # Prices should be positive floats
        assert (df["v"] > 0).all()
        assert df["v"].dtype == np.float64

    def test_equity_daily_filters_date_range(self, av):
        df = av.get_historical_price("IBM", "2026-03-01", "2026-03-07")

        assert len(df) > 0
        assert df["t"].min() >= "2026-03-01"
        assert df["t"].max() <= "2026-03-07"

    def test_equity_daily_sorted_ascending(self, av):
        df = av.get_historical_price("IBM", "2026-03-01", "2026-03-31")

        dates = df["t"].tolist()
        assert dates == sorted(dates)


# ── Full pipeline E2E: real data → indicators → strategy → perf ────


class TestFullPipelineE2E:
    """Fetch real equity data and run through the full backtest pipeline."""

    @pytest.fixture
    def ibm_data(self, av):
        """Fetch recent IBM data for pipeline tests (free tier returns ~100 days)."""
        price = av.get_historical_price("IBM", "2025-01-01", "2026-04-01")
        # Build DataFrame matching pipeline expectations
        df = pd.DataFrame({
            "datetime": price["t"],
            "price": price["v"],
            "factor": price["v"],
        })
        return df

    def test_sma_momentum_on_real_data(self, ibm_data):
        ta = TechnicalAnalysis(ibm_data)
        perf = Performance(
            ta.data, 252, ta.get_sma,
            Strategy.momentum_const_signal, 20, 0.5,
        )
        result = perf.get_strategy_performance()

        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])
        assert np.isfinite(result["Sharpe Ratio"])

    def test_bollinger_reversion_on_real_data(self, ibm_data):
        ta = TechnicalAnalysis(ibm_data)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band,
            Strategy.reversion_const_signal, 20, 1.0,
        )
        result = perf.get_strategy_performance()

        assert isinstance(result, pd.Series)
        assert perf.get_max_drawdown() >= 0

    def test_buy_hold_benchmark_on_real_data(self, ibm_data):
        ta = TechnicalAnalysis(ibm_data)
        perf = Performance(
            ta.data, 252, ta.get_sma,
            Strategy.momentum_const_signal, 20, 0.5,
        )
        bh = perf.get_buy_hold_performance()

        assert isinstance(bh, pd.Series)
        assert np.isfinite(bh["Total Return"])
