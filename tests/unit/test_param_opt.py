import numpy as np
import pandas as pd
import pytest

from strat import Strategy, StrategyConfig, SubStrategy, SignalDirection
from param_opt import ParametersOptimization, OptimizeResult, OPTUNA_MAX_TRIALS


_BOLLINGER_CONFIG = StrategyConfig("TEST", "get_bollinger_band",
                                   Strategy.momentum_const_signal, 252)


class TestParametersOptimization:
    def _make_optimizer(self, df):
        return ParametersOptimization(df.copy(), _BOLLINGER_CONFIG)

    def test_optimize_returns_result(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        result = opt.optimize((5, 10), (0.5, 1.0))
        assert isinstance(result, OptimizeResult)
        assert len(result.grid_df) == 4  # 2 windows x 2 signals

    def test_optimize_result_columns(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        result = opt.optimize((5,), (0.5,))
        assert len(result.grid_df) == 1
        assert list(result.grid_df.columns) == ["window", "signal", "sharpe"]
        assert result.best["window"] == 5
        assert result.best["signal"] == 0.5
        assert isinstance(result.best["sharpe"], (int, float, np.floating))

    def test_optimize_covers_all_combinations(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        windows = (5, 10, 15)
        signals = (0.5, 1.0)
        result = opt.optimize(windows, signals)
        result_params = list(zip(result.grid_df["window"], result.grid_df["signal"]))
        assert (5, 0.5) in result_params
        assert (5, 1.0) in result_params
        assert (10, 0.5) in result_params
        assert (10, 1.0) in result_params
        assert (15, 0.5) in result_params
        assert (15, 1.0) in result_params

    def test_optimize_sharpe_varies_with_params(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        result = opt.optimize((5, 20), (0.5, 1.5))
        sharpes = result.grid_df["sharpe"].tolist()
        # Different params should generally produce different Sharpe ratios
        assert len(set(sharpes)) > 1

    def test_optimize_single_param(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        result = opt.optimize((10,), (1.0,))
        assert len(result.grid_df) == 1

    def test_optimize_with_n_trials(self, sample_ohlc_df):
        """When n_trials < total, TPE sampler is used and fewer trials run."""
        opt = self._make_optimizer(sample_ohlc_df)
        result = opt.optimize((5, 10, 15, 20), (0.5, 1.0, 1.5), n_trials=3)
        assert len(result.grid_df) == 3


class TestParametersOptimizationWithConfig:
    def test_config_stored(self, sample_ohlc_df):
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(sample_ohlc_df.copy(), config)
        assert opt.config is config

    def test_fee_propagates(self, sample_ohlc_df):
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(sample_ohlc_df.copy(), config, fee_bps=20.0)
        assert opt.fee_bps == 20.0


# -------------------------------------------------------------------------
# Phase 4: Multi-factor grid search
# -------------------------------------------------------------------------

def _multi_factor_config(**overrides):
    sub_a = SubStrategy("get_sma", "momentum_const_signal", 5, 0.5, "v")
    sub_b = SubStrategy("get_sma", "momentum_const_signal", 10, 0.5, "volume")
    defaults = dict(
        ticker="TEST",
        indicator_name="get_sma",
        signal_func=SignalDirection.momentum_const_signal,
        trading_period=252,
        conjunction="AND",
        substrategies=(sub_a, sub_b),
    )
    defaults.update(overrides)
    return StrategyConfig(**defaults)


class TestOptimizeMulti:
    def test_returns_result(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5, 10), (5, 10)],
            [(0.5,), (0.5,)],
        )
        assert isinstance(result, OptimizeResult)
        assert len(result.grid_df) == 4  # 2 × 1 × 2 × 1
        for col in ["window_0", "signal_0", "window_1", "signal_1", "sharpe"]:
            assert col in result.grid_df.columns

    def test_grid_size_correct(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5, 10, 15), (5, 10)],
            [(0.5, 1.0), (0.5,)],
        )
        # Factor 0: 3 windows × 2 signals = 6.  Factor 1: 2 × 1 = 2.  Total: 12.
        assert len(result.grid_df) == 12

    def test_covers_all_combinations(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5, 10), (5, 10)],
            [(0.5,), (0.5,)],
        )
        params = list(zip(result.grid_df["window_0"], result.grid_df["window_1"]))
        assert (5, 5) in params
        assert (5, 10) in params
        assert (10, 5) in params
        assert (10, 10) in params

    def test_sharpe_is_numeric(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5,), (10,)],
            [(0.5,), (0.5,)],
        )
        assert len(result.grid_df) == 1
        assert isinstance(result.grid_df.iloc[0]["sharpe"], (int, float, np.floating))

    def test_mismatched_ranges_raises(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        with pytest.raises(ValueError, match="window_ranges has 2.*signal_ranges has 1"):
            opt.optimize_multi([(5,), (10,)], [(0.5,)])

    def test_large_grid_uses_tpe(self, multi_factor_df, caplog):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        # Build ranges that exceed OPTUNA_MAX_TRIALS threshold
        big_range = tuple(range(1, 201))
        import logging
        with caplog.at_level(logging.INFO):
            # Run with small n_trials to avoid long execution
            result = opt.optimize_multi(
                [big_range, big_range], [big_range, big_range],
                n_trials=2,
            )
        assert any("TPE" in rec.message for rec in caplog.records)
        assert len(result.grid_df) == 2

    def test_or_conjunction(self, multi_factor_df):
        config = _multi_factor_config(conjunction="OR")
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5,), (10,)],
            [(0.5,), (0.5,)],
        )
        assert len(result.grid_df) == 1
        assert isinstance(result.grid_df.iloc[0]["sharpe"], (int, float, np.floating))

    def test_best_sharpe_selection(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5, 10, 20), (5, 10)],
            [(0.5, 1.0), (0.5,)],
        )
        assert result.best["sharpe"] == result.grid_df["sharpe"].max()

    def test_n_trials_limits_evaluations(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi(
            [(5, 10, 20), (5, 10)],
            [(0.5, 1.0), (0.5,)],
            n_trials=3,
        )
        assert len(result.grid_df) == 3


# -------------------------------------------------------------------------
# study exposure
# -------------------------------------------------------------------------

class TestStudy:
    def test_study_set_after_optimize(self, sample_ohlc_df):
        opt = ParametersOptimization(sample_ohlc_df.copy(), _BOLLINGER_CONFIG)
        result = opt.optimize((5, 10), (0.5, 1.0))
        assert result.study is not None
        assert len(result.study.trials) == 4

    def test_study_set_after_optimize_multi(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.optimize_multi([(5, 10), (5, 10)], [(0.5,), (0.5,)])
        assert result.study is not None
        assert len(result.study.trials) == 4

    def test_study_independent_per_call(self, sample_ohlc_df):
        opt = ParametersOptimization(sample_ohlc_df.copy(), _BOLLINGER_CONFIG)
        result1 = opt.optimize((5,), (0.5,))
        result2 = opt.optimize((5, 10), (0.5, 1.0))
        assert result1.study is not result2.study
        assert len(result2.study.trials) == 4


# -------------------------------------------------------------------------
# callbacks parameter
# -------------------------------------------------------------------------

class TestCallbacks:
    def test_optimize_callback_called_per_trial(self, sample_ohlc_df):
        opt = ParametersOptimization(sample_ohlc_df.copy(), _BOLLINGER_CONFIG)
        calls = []
        opt.optimize((5, 10), (0.5, 1.0),
                     callbacks=[lambda study, trial: calls.append(1)])
        assert len(calls) == 4  # 2 windows × 2 signals

    def test_optimize_multi_callback_called_per_trial(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        calls = []
        opt.optimize_multi(
            [(5, 10), (5, 10)], [(0.5,), (0.5,)],
            callbacks=[lambda study, trial: calls.append(1)],
        )
        assert len(calls) == 4  # 2×1 × 2×1


# -------------------------------------------------------------------------
# run() auto-dispatch
# -------------------------------------------------------------------------

class TestRun:
    def test_run_dispatches_single(self, sample_ohlc_df):
        opt = ParametersOptimization(sample_ohlc_df.copy(), _BOLLINGER_CONFIG)
        result = opt.run((5, 10), (0.5, 1.0))
        assert isinstance(result, OptimizeResult)
        assert list(result.grid_df.columns) == ["window", "signal", "sharpe"]
        assert len(result.grid_df) == 4

    def test_run_dispatches_multi(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(multi_factor_df.copy(), config)
        result = opt.run([(5, 10), (5, 10)], [(0.5,), (0.5,)])
        assert isinstance(result, OptimizeResult)
        assert "window_0" in result.grid_df.columns
        assert len(result.grid_df) == 4

    def test_optimize_no_callbacks_default(self, sample_ohlc_df):
        """Callbacks default to None — optimization still works."""
        opt = ParametersOptimization(sample_ohlc_df.copy(), _BOLLINGER_CONFIG)
        result = opt.optimize((5,), (0.5,))
        assert len(result.grid_df) == 1
