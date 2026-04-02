import numpy as np
import pandas as pd
import pytest

from strat import Strategy, StrategyConfig
from param_opt import ParametersOptimization


_BOLLINGER_CONFIG = StrategyConfig("get_bollinger_band",
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
        config = StrategyConfig("get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(sample_ohlc_df.copy(), config)
        assert opt.config is config

    def test_fee_propagates(self, sample_ohlc_df):
        config = StrategyConfig("get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(sample_ohlc_df.copy(), config, fee_bps=20.0)
        assert opt.fee_bps == 20.0


class TestFactorColumnsOptimization:
    def _make_optimizer(self, df):
        return ParametersOptimization(df.copy(), _BOLLINGER_CONFIG)

    def test_factor_columns_yields_4_tuples(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((10,), (0.5,),
                                    factor_columns=["price", "volume"]))
        assert len(results) == 2
        for row in results:
            assert len(row) == 4  # window, signal, factor, sharpe

    def test_factor_columns_covers_all_factors(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((10,), (0.5,),
                                    factor_columns=["price", "volume"]))
        factors = [r[2] for r in results]
        assert "price" in factors
        assert "volume" in factors

    def test_factor_columns_full_grid(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((5, 10), (0.5, 1.0),
                                    factor_columns=["price", "volume"]))
        # 2 windows × 2 signals × 2 factors = 8
        assert len(results) == 8

    def test_factor_columns_none_yields_3_tuples(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((10,), (0.5,), factor_columns=None))
        assert len(results) == 1
        assert len(results[0]) == 3  # window, signal, sharpe

    def test_different_factors_produce_different_sharpe(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize((10,), (0.5,),
                                    factor_columns=["price", "volume"]))
        sharpe_price = results[0][3]
        sharpe_volume = results[1][3]
        # Price and volume produce different indicator values → different Sharpe
        assert sharpe_price != sharpe_volume


class TestOptimizeGrid:
    """Tests for the N-dimensional optimize_grid method."""

    def _make_optimizer(self, df):
        return ParametersOptimization(df.copy(), _BOLLINGER_CONFIG)

    def test_basic_2d_grid_yields_dicts(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (5, 10), 'signal': (0.5, 1.0),
        }))
        assert len(results) == 4
        for row in results:
            assert isinstance(row, dict)
            assert 'window' in row
            assert 'signal' in row
            assert 'sharpe' in row

    def test_grid_returns_generator(self, sample_ohlc_df):
        import types
        opt = self._make_optimizer(sample_ohlc_df)
        gen = opt.optimize_grid({'window': (5,), 'signal': (0.5,)})
        assert isinstance(gen, types.GeneratorType)

    def test_3d_grid_with_factor(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (0.5,),
            'factor': ['price', 'volume'],
        }))
        assert len(results) == 2
        factors = [r['factor'] for r in results]
        assert 'price' in factors
        assert 'volume' in factors

    def test_4d_grid_with_indicator(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (0.5,),
            'indicator': ['get_bollinger_band', 'get_sma'],
        }))
        assert len(results) == 2
        indicators = [r['indicator'] for r in results]
        assert 'get_bollinger_band' in indicators
        assert 'get_sma' in indicators

    def test_5d_grid_with_strategy(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (0.5,),
            'strategy': [Strategy.momentum_const_signal,
                         Strategy.reversion_const_signal],
        }))
        assert len(results) == 2
        strategies = [r['strategy'] for r in results]
        assert 'momentum_const_signal' in strategies
        assert 'reversion_const_signal' in strategies

    def test_full_5d_grid(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (5, 10),
            'signal': (0.5,),
            'indicator': ['get_bollinger_band', 'get_sma'],
            'strategy': [Strategy.momentum_const_signal,
                         Strategy.reversion_const_signal],
            'factor': ['price', 'volume'],
        }))
        # 2 windows × 1 signal × 2 indicators × 2 strategies × 2 factors = 16
        assert len(results) == 16

    def test_missing_window_raises(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        with pytest.raises(ValueError, match="window"):
            list(opt.optimize_grid({'signal': (0.5,)}))

    def test_missing_signal_raises(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        with pytest.raises(ValueError, match="signal"):
            list(opt.optimize_grid({'window': (10,)}))

    def test_grid_results_buildable_as_dataframe(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = pd.DataFrame(opt.optimize_grid({
            'window': (5, 10), 'signal': (0.5, 1.0),
            'factor': ['price', 'volume'],
        }))
        assert list(results.columns) == ['window', 'signal', 'factor', 'sharpe']
        assert len(results) == 8

    def test_grid_pivot_works(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = pd.DataFrame(opt.optimize_grid({
            'window': (5, 10), 'signal': (0.5, 1.0),
        }))
        pivot = results.pivot(index='window', columns='signal', values='sharpe')
        assert pivot.shape == (2, 2)

    def test_backward_compat_matches_optimize(self, sample_ohlc_df):
        """optimize() wrapper yields same values as optimize_grid()."""
        opt = self._make_optimizer(sample_ohlc_df)
        old_results = list(opt.optimize((5, 10), (0.5, 1.0)))
        new_results = list(opt.optimize_grid({
            'window': (5, 10), 'signal': (0.5, 1.0),
        }))
        for old_tuple, new_dict in zip(old_results, new_results):
            assert old_tuple[0] == new_dict['window']
            assert old_tuple[1] == new_dict['signal']
            if np.isnan(old_tuple[2]):
                assert np.isnan(new_dict['sharpe'])
            else:
                assert old_tuple[2] == pytest.approx(new_dict['sharpe'])

    def test_grid_with_stochastic(self, sample_ohlc_df):
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (20.0,),
            'indicator': ['get_stochastic_oscillator'],
        }))
        assert len(results) == 1
        assert results[0]['indicator'] == 'get_stochastic_oscillator'
        assert isinstance(results[0]['sharpe'], (int, float, np.floating))

    def test_grid_all_indicators(self, sample_ohlc_df):
        """Sweep all 5 indicators in a single grid."""
        opt = self._make_optimizer(sample_ohlc_df)
        all_indicators = [
            'get_bollinger_band', 'get_sma', 'get_ema', 'get_rsi',
            'get_stochastic_oscillator',
        ]
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (0.5,),
            'indicator': all_indicators,
        }))
        assert len(results) == 5
        returned_indicators = {r['indicator'] for r in results}
        assert returned_indicators == set(all_indicators)

    def test_grid_all_strategies_x_all_indicators(self, sample_ohlc_df):
        """Full cross-product: 5 indicators × 2 strategies."""
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (0.5,),
            'indicator': [
                'get_bollinger_band', 'get_sma', 'get_ema', 'get_rsi',
                'get_stochastic_oscillator',
            ],
            'strategy': [Strategy.momentum_const_signal,
                         Strategy.reversion_const_signal],
        }))
        # 1 × 1 × 5 × 2 = 10
        assert len(results) == 10

    def test_grid_all_dims_single_values(self, sample_ohlc_df):
        """Single value per dimension — should still work."""
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,),
            'signal': (0.5,),
            'indicator': ['get_ema'],
            'strategy': [Strategy.reversion_const_signal],
            'factor': ['price'],
        }))
        assert len(results) == 1
        assert results[0]['indicator'] == 'get_ema'
        assert results[0]['strategy'] == 'reversion_const_signal'
        assert results[0]['factor'] == 'price'

    def test_grid_factor_switches_data(self, sample_ohlc_df):
        """Verify factor dimension actually changes the factor column."""
        opt = self._make_optimizer(sample_ohlc_df)
        results = list(opt.optimize_grid({
            'window': (10,), 'signal': (0.5,),
            'factor': ['price', 'volume'],
        }))
        sharpe_price = results[0]['sharpe']
        sharpe_volume = results[1]['sharpe']
        # Different factor columns produce different Sharpe ratios
        assert sharpe_price != sharpe_volume
