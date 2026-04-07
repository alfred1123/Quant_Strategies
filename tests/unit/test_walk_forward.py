import numpy as np
import pandas as pd
import pytest

from strat import Strategy, StrategyConfig, SubStrategy, SignalDirection
from walk_forward import WalkForward, WalkForwardResult


_BOLLINGER_CONFIG = StrategyConfig("TEST", "get_bollinger_band",
                                   Strategy.momentum_const_signal, 252)


def _make_synthetic_data(n=500, seed=42):
    """Generate synthetic price data for walk-forward tests."""
    np.random.seed(seed)
    trend = np.linspace(100, 150, n)
    noise = np.cumsum(np.random.randn(n) * 0.3)
    close = trend + noise
    return pd.DataFrame({
        "price": close,
        "factor": close,
        "Close": close,
        "High": close + np.abs(np.random.randn(n) * 0.5),
        "Low": close - np.abs(np.random.randn(n) * 0.5),
    })


class TestWalkForwardInit:
    def test_valid_split_ratio(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        assert wf.split_idx == 250

    def test_split_ratio_0_raises(self):
        df = _make_synthetic_data()
        with pytest.raises(ValueError, match="split_ratio must be between"):
            WalkForward(df, 0.0, _BOLLINGER_CONFIG)

    def test_split_ratio_1_raises(self):
        df = _make_synthetic_data()
        with pytest.raises(ValueError, match="split_ratio must be between"):
            WalkForward(df, 1.0, _BOLLINGER_CONFIG)

    def test_split_ratio_too_small_raises(self):
        df = _make_synthetic_data(n=10)
        with pytest.raises(ValueError, match="Split produces empty partition"):
            WalkForward(df, 0.1, _BOLLINGER_CONFIG)

    def test_split_idx_proportional(self):
        df = _make_synthetic_data(n=200)
        wf = WalkForward(df, 0.7, _BOLLINGER_CONFIG)
        assert wf.split_idx == 140

    def test_fee_bps_propagates(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG, fee_bps=10.0)
        assert wf.fee_bps == 10.0


class TestWalkForwardRun:
    def test_returns_walk_forward_result(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        result = wf.run((10, 20), (0.5, 1.0))
        assert isinstance(result, WalkForwardResult)

    def test_best_window_in_grid(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        result = wf.run((10, 20, 30), (0.5, 1.0))
        assert result.best_window in (10, 20, 30)

    def test_best_signal_in_grid(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        result = wf.run((20,), (0.5, 1.0, 1.5))
        assert result.best_signal in (0.5, 1.0, 1.5)

    def test_is_metrics_is_series(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        result = wf.run((20,), (1.0,))
        assert isinstance(result.is_metrics, pd.Series)
        assert len(result.is_metrics) == 5

    def test_oos_metrics_is_series(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        result = wf.run((20,), (1.0,))
        assert isinstance(result.oos_metrics, pd.Series)
        assert len(result.oos_metrics) == 5

    def test_overfitting_ratio_is_finite_or_nan(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        result = wf.run((20,), (1.0,))
        assert np.isfinite(result.overfitting_ratio) or np.isnan(result.overfitting_ratio)


class TestWalkForwardResult:
    def test_summary_returns_dataframe(self):
        is_metrics = pd.Series([0.5, 0.1, 1.2, 0.05, 2.0],
                               index=['Total Return', 'Annualized Return',
                                      'Sharpe Ratio', 'Max Drawdown',
                                      'Calmar Ratio'])
        oos_metrics = pd.Series([0.3, 0.06, 0.8, 0.08, 0.75],
                                index=['Total Return', 'Annualized Return',
                                       'Sharpe Ratio', 'Max Drawdown',
                                       'Calmar Ratio'])
        result = WalkForwardResult(20, 1.0, is_metrics, oos_metrics, 0.333)
        summary = result.summary()
        assert isinstance(summary, pd.DataFrame)
        assert 'In-Sample' in summary.columns
        assert 'Out-of-Sample' in summary.columns
        assert 'Overfitting Ratio' in summary.index

    def test_summary_overfitting_row(self):
        is_metrics = pd.Series([0.5, 0.1, 1.2, 0.05, 2.0],
                               index=['Total Return', 'Annualized Return',
                                      'Sharpe Ratio', 'Max Drawdown',
                                      'Calmar Ratio'])
        oos_metrics = pd.Series([0.3, 0.06, 0.8, 0.08, 0.75],
                                index=['Total Return', 'Annualized Return',
                                       'Sharpe Ratio', 'Max Drawdown',
                                       'Calmar Ratio'])
        result = WalkForwardResult(20, 1.0, is_metrics, oos_metrics, 0.333)
        summary = result.summary()
        assert summary.loc['Overfitting Ratio', 'Out-of-Sample'] == pytest.approx(0.333)
        assert np.isnan(summary.loc['Overfitting Ratio', 'In-Sample'])


class TestWalkForwardWithConfig:
    def test_config_stored(self):
        df = _make_synthetic_data()
        wf = WalkForward(df, 0.5, _BOLLINGER_CONFIG)
        assert wf.config is _BOLLINGER_CONFIG

    def test_run_produces_result(self):
        df = _make_synthetic_data()
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        wf = WalkForward(df.copy(), 0.5, config)
        result = wf.run((20,), (1.0,))
        assert isinstance(result, WalkForwardResult)
        assert result.best_window == 20

    def test_fee_propagates(self):
        df = _make_synthetic_data()
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        wf = WalkForward(df, 0.5, config, fee_bps=15.0)
        assert wf.fee_bps == 15.0


# -------------------------------------------------------------------------
# Phase 4: Multi-factor walk-forward
# -------------------------------------------------------------------------

def _make_multi_factor_data(n=500, seed=42):
    np.random.seed(seed)
    trend = np.linspace(100, 150, n)
    noise = np.cumsum(np.random.randn(n) * 0.3)
    close = trend + noise
    volume = 5000 + np.cumsum(np.random.randn(n) * 50)
    return pd.DataFrame({
        "price": close,
        "factor": close,
        "v": close,
        "volume": volume,
        "Close": close,
        "High": close + np.abs(np.random.randn(n) * 0.5),
        "Low": close - np.abs(np.random.randn(n) * 0.5),
    })


def _multi_factor_config():
    sub_a = SubStrategy("get_sma", "momentum_const_signal", 10, 0.5, "v")
    sub_b = SubStrategy("get_sma", "momentum_const_signal", 20, 0.5, "volume")
    return StrategyConfig(
        "TEST", "get_sma", SignalDirection.momentum_const_signal, 252,
        conjunction="AND", substrategies=(sub_a, sub_b),
    )


class TestWalkForwardMultiFactor:
    def test_run_multi_returns_result(self):
        df = _make_multi_factor_data()
        config = _multi_factor_config()
        wf = WalkForward(df, 0.5, config)
        result = wf.run_multi([(10, 20), (10, 20)], [(0.5,), (0.5,)])
        assert isinstance(result, WalkForwardResult)

    def test_best_params_are_tuples(self):
        df = _make_multi_factor_data()
        config = _multi_factor_config()
        wf = WalkForward(df, 0.5, config)
        result = wf.run_multi([(10, 20), (10, 20)], [(0.5, 1.0), (0.5,)])
        assert isinstance(result.best_window, tuple)
        assert isinstance(result.best_signal, tuple)
        assert len(result.best_window) == 2
        assert len(result.best_signal) == 2

    def test_best_window_in_grid(self):
        df = _make_multi_factor_data()
        config = _multi_factor_config()
        wf = WalkForward(df, 0.5, config)
        result = wf.run_multi([(10, 20), (10, 20)], [(0.5,), (0.5,)])
        assert result.best_window[0] in (10, 20)
        assert result.best_window[1] in (10, 20)

    def test_metrics_are_series(self):
        df = _make_multi_factor_data()
        config = _multi_factor_config()
        wf = WalkForward(df, 0.5, config)
        result = wf.run_multi([(10,), (20,)], [(0.5,), (0.5,)])
        assert isinstance(result.is_metrics, pd.Series)
        assert isinstance(result.oos_metrics, pd.Series)
        assert len(result.is_metrics) == 5
        assert len(result.oos_metrics) == 5

    def test_overfitting_ratio_finite_or_nan(self):
        df = _make_multi_factor_data()
        config = _multi_factor_config()
        wf = WalkForward(df, 0.5, config)
        result = wf.run_multi([(10,), (20,)], [(0.5,), (0.5,)])
        assert np.isfinite(result.overfitting_ratio) or np.isnan(result.overfitting_ratio)

    def test_summary_returns_dataframe(self):
        df = _make_multi_factor_data()
        config = _multi_factor_config()
        wf = WalkForward(df, 0.5, config)
        result = wf.run_multi([(10,), (20,)], [(0.5,), (0.5,)])
        summary = result.summary()
        assert isinstance(summary, pd.DataFrame)
        assert "In-Sample" in summary.columns
        assert "Overfitting Ratio" in summary.index
