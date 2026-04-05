import numpy as np
import pandas as pd
import pytest

from strat import Strategy, StrategyConfig
from param_opt import ParametersOptimization


_BOLLINGER_CONFIG = StrategyConfig("TEST", "get_bollinger_band",
                                   Strategy.momentum_const_signal, 252)


class TestParametersOptimization:
    def _make_optimizer(self, df):
        return ParametersOptimization(df.copy(), _BOLLINGER_CONFIG)

    def test_optimize_yields_tuples(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        window_list = (5, 10)
        signal_list = (0.5, 1.0)
        results = list(opt.optimize(window_list, signal_list))
        assert len(results) == 4  # 2 windows x 2 signals

    def test_optimize_result_format(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((5,), (0.5,)))
        assert len(results) == 1
        window, signal, sharpe = results[0]
        assert window == 5
        assert signal == 0.5
        assert isinstance(sharpe, (int, float, np.floating))

    def test_optimize_covers_all_combinations(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        windows = (5, 10, 15)
        signals = (0.5, 1.0)
        results = list(opt.optimize(windows, signals))
        result_params = [(r[0], r[1]) for r in results]
        assert (5, 0.5) in result_params
        assert (5, 1.0) in result_params
        assert (10, 0.5) in result_params
        assert (10, 1.0) in result_params
        assert (15, 0.5) in result_params
        assert (15, 1.0) in result_params

    def test_optimize_sharpe_varies_with_params(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((5, 20), (0.5, 1.5)))
        sharpes = [r[2] for r in results]
        # Different params should generally produce different Sharpe ratios
        assert len(set(sharpes)) > 1

    def test_optimize_single_param(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((10,), (1.0,)))
        assert len(results) == 1

    def test_optimize_returns_generator(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        gen = opt.optimize((5,), (0.5,))
        # Should be a generator, not a list
        import types
        assert isinstance(gen, types.GeneratorType)


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
