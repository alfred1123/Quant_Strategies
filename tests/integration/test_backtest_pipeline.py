"""
Integration test: runs the full backtest pipeline with synthetic data.
data → TechnicalAnalysis → Strategy → Performance → ParametersOptimization
No external API calls are made.
"""

import numpy as np
import pandas as pd
import pytest

from ta import TechnicalAnalysis
from strat import Strategy
from perf import Performance
from param_opt import ParametersOptimization


@pytest.fixture
def synthetic_market_data():
    """Generate realistic synthetic OHLCV data with a trend + noise."""
    np.random.seed(123)
    n = 500
    trend = np.linspace(100, 150, n)
    noise = np.cumsum(np.random.randn(n) * 0.3)
    close = trend + noise
    high = close + np.abs(np.random.randn(n) * 0.5)
    low = close - np.abs(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "price": close,
        "factor": close,
        "Close": close,
        "High": high,
        "Low": low,
    })


class TestFullBacktestPipeline:
    """End-to-end test: data → indicators → strategy → performance."""

    def test_sma_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_sma, Strategy.momentum_const_signal, 20, 0.5
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])
        assert perf.get_max_drawdown() >= 0

    def test_ema_reversion_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_ema, Strategy.reversion_const_signal, 15, 1.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Sharpe Ratio"])

    def test_bollinger_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        strat_perf = perf.get_strategy_performance()
        bh_perf = perf.get_buy_hold_performance()
        assert isinstance(strat_perf, pd.Series)
        assert isinstance(bh_perf, pd.Series)
        # Both should return finite values for total return
        assert np.isfinite(strat_perf["Total Return"])
        assert np.isfinite(bh_perf["Total Return"])

    def test_rsi_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_rsi, Strategy.momentum_const_signal, 14, 30.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)


class TestParameterOptimizationPipeline:
    """End-to-end test: data → indicators → grid search → Sharpe results."""

    def test_grid_search_produces_results(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        opt = ParametersOptimization(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal
        )
        windows = (10, 20, 30)
        signals = (0.5, 1.0, 1.5)
        results = pd.DataFrame(
            opt.optimize(windows, signals), columns=["window", "signal", "sharpe"]
        )
        assert len(results) == 9
        assert results["window"].nunique() == 3
        assert results["signal"].nunique() == 3
        assert results["sharpe"].notna().all()

    def test_grid_search_can_pivot_to_heatmap(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        opt = ParametersOptimization(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal
        )
        results = pd.DataFrame(
            opt.optimize((10, 20), (0.5, 1.0)), columns=["window", "signal", "sharpe"]
        )
        pivot = results.pivot(index="window", columns="signal", values="sharpe")
        assert pivot.shape == (2, 2)
        assert not pivot.isna().any().any()


class TestStrategyVsBuyHoldConsistency:
    """Verify that strategy and buy-and-hold metrics are internally consistent."""

    def test_buy_hold_cumulative_matches_total_return(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        total = perf.get_buy_hold_total_return()
        cumu_last = perf.data["buy_hold_cumu"].iloc[-1]
        assert total == pytest.approx(cumu_last)

    def test_strategy_cumulative_matches_total_return(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        total = perf.get_total_return()
        cumu_last = perf.data["cumu"].iloc[-1]
        assert total == pytest.approx(cumu_last)

    def test_max_drawdown_within_cumulative_range(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        max_dd = perf.get_max_drawdown()
        cumu_range = perf.data["cumu"].max() - perf.data["cumu"].min()
        assert max_dd <= cumu_range + 1e-10
