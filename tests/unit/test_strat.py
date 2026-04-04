import numpy as np
import pytest

from strat import Strategy, StrategyConfig, FactorConfig, combine_positions


class TestMomentumConstSignal:
    def test_long_when_above_signal(self):
        data = np.array([2.0, 3.0, 5.0])
        result = Strategy.momentum_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_short_when_below_neg_signal(self):
        data = np.array([-2.0, -3.0, -5.0])
        result = Strategy.momentum_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_flat_when_between_signals(self):
        data = np.array([0.0, 0.5, -0.5])
        result = Strategy.momentum_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_mixed_signals(self):
        data = np.array([2.0, 0.0, -2.0, 0.5, 1.5])
        result = Strategy.momentum_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [1.0, 0.0, -1.0, 0.0, 1.0])

    def test_nan_propagation(self):
        data = np.array([np.nan, 2.0, -2.0])
        result = Strategy.momentum_const_signal(data, 1.0)
        assert np.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == -1.0

    def test_zero_signal_threshold(self):
        data = np.array([0.1, -0.1, 0.0])
        result = Strategy.momentum_const_signal(data, 0.0)
        assert result[0] == 1.0
        assert result[1] == -1.0
        # Exactly zero: not > 0 and not < 0 → flat
        assert result[2] == 0.0

    def test_output_dtype_float(self):
        data = np.array([2.0, -2.0, 0.0])
        result = Strategy.momentum_const_signal(data, 1.0)
        assert result.dtype == float


class TestReversionConstSignal:
    def test_long_when_below_neg_signal(self):
        data = np.array([-2.0, -3.0, -5.0])
        result = Strategy.reversion_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_short_when_above_signal(self):
        data = np.array([2.0, 3.0, 5.0])
        result = Strategy.reversion_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_flat_when_between_signals(self):
        data = np.array([0.0, 0.5, -0.5])
        result = Strategy.reversion_const_signal(data, 1.0)
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_opposite_of_momentum(self):
        data = np.array([2.0, 0.0, -2.0, 0.5, 1.5])
        signal = 1.0
        mom = Strategy.momentum_const_signal(data, signal)
        rev = Strategy.reversion_const_signal(data, signal)
        # Reversion should be the negative of momentum (where not flat)
        np.testing.assert_array_equal(rev, -mom)

    def test_nan_propagation(self):
        data = np.array([np.nan, -2.0, 2.0])
        result = Strategy.reversion_const_signal(data, 1.0)
        assert np.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == -1.0


class TestStrategyConfig:
    def test_frozen_dataclass(self):
        cfg = StrategyConfig(
            factors=(FactorConfig('price', 'get_bollinger_band'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )
        with pytest.raises(AttributeError):
            cfg.trading_period = 252

    def test_fields(self):
        cfg = StrategyConfig(
            factors=(FactorConfig('price', 'get_sma'),),
            strategy_func=Strategy.reversion_const_signal,
            trading_period=252,
        )
        assert cfg.factors[0].indicator_name == "get_sma"
        assert cfg.factors[0].column == "price"
        assert cfg.strategy_func is Strategy.reversion_const_signal
        assert cfg.trading_period == 252
        assert cfg.conjunction == 'AND'

    def test_equality(self):
        a = StrategyConfig(
            factors=(FactorConfig('price', 'get_ema'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )
        b = StrategyConfig(
            factors=(FactorConfig('price', 'get_ema'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )
        assert a == b

    def test_inequality(self):
        a = StrategyConfig(
            factors=(FactorConfig('price', 'get_sma'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )
        b = StrategyConfig(
            factors=(FactorConfig('price', 'get_ema'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )
        assert a != b

    def test_conjunction_default(self):
        cfg = StrategyConfig(
            factors=(FactorConfig('price', 'get_bollinger_band'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )
        assert cfg.conjunction == 'AND'

    def test_conjunction_or(self):
        cfg = StrategyConfig(
            factors=(FactorConfig('price', 'get_bollinger_band'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
            conjunction='OR',
        )
        assert cfg.conjunction == 'OR'


class TestFactorConfig:
    def test_frozen(self):
        fc = FactorConfig('price', 'get_bollinger_band')
        with pytest.raises(AttributeError):
            fc.column = 'volume'

    def test_fields(self):
        fc = FactorConfig('volume', 'get_sma')
        assert fc.column == 'volume'
        assert fc.indicator_name == 'get_sma'


class TestCombinePositions:
    def test_and_all_long(self):
        a = np.array([1.0, 1.0, 1.0])
        b = np.array([1.0, 1.0, 1.0])
        result = combine_positions([a, b], 'AND')
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_and_all_short(self):
        a = np.array([-1.0, -1.0, -1.0])
        b = np.array([-1.0, -1.0, -1.0])
        result = combine_positions([a, b], 'AND')
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_and_mixed_signals(self):
        a = np.array([1.0, -1.0, 0.0, 1.0])
        b = np.array([1.0, -1.0, 1.0, -1.0])
        result = combine_positions([a, b], 'AND')
        np.testing.assert_array_equal(result, [1.0, -1.0, 0.0, 0.0])

    def test_or_any_long(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        result = combine_positions([a, b], 'OR')
        np.testing.assert_array_equal(result, [1.0, 1.0, 0.0])

    def test_or_any_short(self):
        a = np.array([-1.0, 0.0, 0.0])
        b = np.array([0.0, -1.0, 0.0])
        result = combine_positions([a, b], 'OR')
        np.testing.assert_array_equal(result, [-1.0, -1.0, 0.0])

    def test_or_conflict_is_flat(self):
        a = np.array([1.0, -1.0])
        b = np.array([-1.0, 1.0])
        result = combine_positions([a, b], 'OR')
        np.testing.assert_array_equal(result, [0.0, 0.0])

    def test_nan_propagation(self):
        a = np.array([1.0, np.nan, -1.0])
        b = np.array([1.0, 1.0, -1.0])
        result = combine_positions([a, b], 'AND')
        assert result[0] == 1.0
        assert np.isnan(result[1])
        assert result[2] == -1.0

    def test_single_factor_passthrough(self):
        a = np.array([1.0, -1.0, 0.0])
        result = combine_positions([a], 'AND')
        np.testing.assert_array_equal(result, [1.0, -1.0, 0.0])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            combine_positions([], 'AND')

    def test_invalid_conjunction_raises(self):
        a = np.array([1.0])
        with pytest.raises(ValueError, match="conjunction"):
            combine_positions([a], 'XOR')
