"""
E2E tests: hit the real Yahoo Finance API → run data through the full
backtest pipeline (ta → strategy → performance → param_opt → walk_forward).

Yahoo Finance requires no API key, so these tests only need network access.

Run explicitly:
  python -m pytest tests/e2e/ -v -m e2e

They are skipped by default in `python -m pytest tests/` unless
the -m e2e marker is specified.
"""

import numpy as np
import pandas as pd
import pytest

from data import YahooFinance
from strat import Strategy, StrategyConfig, FactorConfig
from perf import Performance
from param_opt import ParametersOptimization
from walk_forward import WalkForward

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def yf():
    """YahooFinance client — clear cache for fresh data."""
    client = YahooFinance()
    client.get_historical_price.cache_clear()
    return client


# ── Contract tests: verify real API response shape ──────────────────


class TestYahooFinanceContract:
    """Validate that the real Yahoo Finance API returns the expected schema."""

    def test_equity_returns_t_v_columns(self, yf):
        df = yf.get_historical_price("AAPL", "2025-01-01", "2025-03-31")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["t", "v"]
        assert len(df) > 0
        assert df["t"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()
        assert (df["v"] > 0).all()
        assert df["v"].dtype == np.float64

    def test_crypto_returns_t_v_columns(self, yf):
        df = yf.get_historical_price("BTC-USD", "2025-01-01", "2025-03-31")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["t", "v"]
        assert len(df) > 0
        assert (df["v"] > 0).all()

    def test_dates_sorted_ascending(self, yf):
        df = yf.get_historical_price("AAPL", "2025-01-01", "2025-03-31")
        dates = df["t"].tolist()
        assert dates == sorted(dates)

    def test_etf_supported(self, yf):
        df = yf.get_historical_price("SPY", "2025-01-01", "2025-03-31")
        assert len(df) > 0
        assert list(df.columns) == ["t", "v"]

    def test_invalid_symbol_raises(self, yf):
        with pytest.raises((ValueError, RuntimeError)):
            yf.get_historical_price("ZZZZZZNOTREAL123", "2025-01-01", "2025-03-31")

    def test_long_history_available(self, yf):
        """Yahoo Finance should provide multi-year data."""
        df = yf.get_historical_price("AAPL", "2020-01-01", "2025-12-31")
        assert len(df) > 1000  # ~5 years of trading days


# ── Full pipeline E2E: real data → indicators → strategy → perf ────


class TestFullPipelineE2E:
    """Fetch real equity data and run through the backtest pipeline."""

    @pytest.fixture(scope="class")
    def aapl_data(self, yf):
        """Fetch AAPL data for pipeline tests."""
        price = yf.get_historical_price("AAPL", "2023-01-01", "2025-12-31")
        df = pd.DataFrame({
            "price": price["v"].values,
            "factor": price["v"].values,
        })
        return df

    @pytest.fixture
    def equity_config(self):
        return StrategyConfig(
            factors=(FactorConfig("factor", "get_sma"),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=252,
        )

    def test_sma_momentum_produces_valid_metrics(self, aapl_data, equity_config):
        perf = Performance(aapl_data, equity_config, 20, 0.5)
        result = perf.get_strategy_performance()

        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])
        assert np.isfinite(result["Sharpe Ratio"])
        assert result["Max Drawdown"] >= 0

    def test_bollinger_reversion_produces_valid_metrics(self, aapl_data):
        config = StrategyConfig(
            factors=(FactorConfig("factor", "get_bollinger_band"),),
            strategy_func=Strategy.reversion_const_signal,
            trading_period=252,
        )
        perf = Performance(aapl_data, config, 20, 1.0)
        result = perf.get_strategy_performance()

        assert isinstance(result, pd.Series)
        assert perf.get_max_drawdown() >= 0

    def test_ema_momentum_produces_valid_metrics(self, aapl_data):
        config = StrategyConfig(
            factors=(FactorConfig("factor", "get_ema"),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=252,
        )
        perf = Performance(aapl_data, config, 20, 0.5)
        result = perf.get_strategy_performance()

        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_buy_hold_benchmark(self, aapl_data, equity_config):
        perf = Performance(aapl_data, equity_config, 20, 0.5)
        bh = perf.get_buy_hold_performance()

        assert isinstance(bh, pd.Series)
        assert np.isfinite(bh["Total Return"])

    def test_transaction_costs_reduce_returns(self, aapl_data, equity_config):
        """Higher fees should produce lower or equal total returns."""
        perf_low = Performance(aapl_data, equity_config, 20, 0.5, fee_bps=1)
        perf_high = Performance(aapl_data, equity_config, 20, 0.5, fee_bps=50)

        assert perf_low.get_total_return() >= perf_high.get_total_return()


# ── Param optimization E2E ──────────────────────────────────────────


class TestParamOptE2E:
    """Grid search on real data."""

    @pytest.fixture(scope="class")
    def spy_data(self, yf):
        price = yf.get_historical_price("SPY", "2023-01-01", "2025-12-31")
        return pd.DataFrame({
            "price": price["v"].values,
            "factor": price["v"].values,
        })

    def test_grid_search_returns_results(self, spy_data):
        config = StrategyConfig(
            factors=(FactorConfig("factor", "get_sma"),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=252,
        )
        opt = ParametersOptimization(spy_data, config)
        results = list(opt.optimize((10, 20), (0.5, 1.0)))

        assert len(results) == 4  # 2 windows × 2 signals
        for window, signal, sharpe in results:
            assert isinstance(window, int)
            assert isinstance(signal, float)
            assert isinstance(sharpe, float)


# ── Walk-forward E2E ────────────────────────────────────────────────


class TestWalkForwardE2E:
    """Walk-forward overfitting test on real data."""

    @pytest.fixture(scope="class")
    def spy_data(self, yf):
        price = yf.get_historical_price("SPY", "2020-01-01", "2025-12-31")
        return pd.DataFrame({
            "price": price["v"].values,
            "factor": price["v"].values,
        })

    def test_walk_forward_produces_result(self, spy_data):
        config = StrategyConfig(
            factors=(FactorConfig("factor", "get_sma"),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=252,
        )
        wf = WalkForward(spy_data, 0.5, config)
        result = wf.run((10, 20), (0.5, 1.0))

        assert result.best_window in (10, 20)
        assert result.best_signal in (0.5, 1.0)
        assert isinstance(result.is_metrics, pd.Series)
        assert isinstance(result.oos_metrics, pd.Series)
        assert isinstance(result.overfitting_ratio, float)

    def test_walk_forward_summary_dataframe(self, spy_data):
        config = StrategyConfig(
            factors=(FactorConfig("factor", "get_bollinger_band"),),
            strategy_func=Strategy.reversion_const_signal,
            trading_period=252,
        )
        wf = WalkForward(spy_data, 0.5, config)
        result = wf.run((15, 25), (0.5, 1.5))
        summary = result.summary()

        assert isinstance(summary, pd.DataFrame)
        assert "In-Sample" in summary.columns
        assert "Out-of-Sample" in summary.columns
