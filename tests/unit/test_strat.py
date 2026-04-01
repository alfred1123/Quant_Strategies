import numpy as np
import pytest

from strat import Strategy, StrategyConfig


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
        cfg = StrategyConfig("get_bollinger_band",
                             Strategy.momentum_const_signal, 365)
        with pytest.raises(AttributeError):
            cfg.trading_period = 252

    def test_fields(self):
        cfg = StrategyConfig("get_sma", Strategy.reversion_const_signal, 252)
        assert cfg.indicator_name == "get_sma"
        assert cfg.strategy_func is Strategy.reversion_const_signal
        assert cfg.trading_period == 252

    def test_equality(self):
        a = StrategyConfig("get_ema", Strategy.momentum_const_signal, 365)
        b = StrategyConfig("get_ema", Strategy.momentum_const_signal, 365)
        assert a == b

    def test_inequality(self):
        a = StrategyConfig("get_sma", Strategy.momentum_const_signal, 365)
        b = StrategyConfig("get_ema", Strategy.momentum_const_signal, 365)
        assert a != b
