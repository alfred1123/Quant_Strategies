import numpy as np
import pytest

from strat import (Strategy, StrategyConfig, SubStrategy, SignalDirection,
                   strategy_to_json, backtest_results_to_json)


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
        cfg = StrategyConfig("TEST", "get_bollinger_band",
                             Strategy.momentum_const_signal, 365)
        with pytest.raises(AttributeError):
            cfg.trading_period = 252

    def test_fields(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.reversion_const_signal, 252)
        assert cfg.ticker == "TEST"
        assert cfg.indicator_name == "get_sma"
        assert cfg.signal_func is Strategy.reversion_const_signal
        assert cfg.trading_period == 252
        assert cfg.strategy_id  # auto-generated UUID is non-empty

    def test_equality(self):
        a = StrategyConfig("TEST", "get_ema", Strategy.momentum_const_signal, 365,
                           strategy_id="same-id")
        b = StrategyConfig("TEST", "get_ema", Strategy.momentum_const_signal, 365,
                           strategy_id="same-id")
        assert a == b

    def test_inequality(self):
        a = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365,
                           strategy_id="id-a")
        b = StrategyConfig("TEST", "get_ema", Strategy.momentum_const_signal, 365,
                           strategy_id="id-b")
        assert a != b


# -------------------------------------------------------------------------
# Phase 2: SubStrategy, StrategyConfig extensions, JSON serialization
# -------------------------------------------------------------------------

class TestSubStrategy:
    def test_frozen_dataclass(self):
        sub = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        with pytest.raises(AttributeError):
            sub.window = 30

    def test_default_data_column(self):
        sub = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        assert sub.data_column == "v"

    def test_custom_data_column(self):
        sub = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0,
                          data_column="volume")
        assert sub.data_column == "volume"

    def test_resolve_signal_func_momentum(self):
        sub = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        fn = sub.resolve_signal_func()
        assert fn is SignalDirection.momentum_const_signal

    def test_resolve_signal_func_reversion(self):
        sub = SubStrategy("get_sma", "reversion_const_signal", 20, 1.0)
        fn = sub.resolve_signal_func()
        assert fn is SignalDirection.reversion_const_signal

    def test_resolve_signal_func_invalid(self):
        sub = SubStrategy("get_sma", "nonexistent_signal", 20, 1.0)
        with pytest.raises(AttributeError):
            sub.resolve_signal_func()

    def test_equality(self):
        a = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        b = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        assert a == b

    def test_inequality(self):
        a = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        b = SubStrategy("get_sma", "reversion_const_signal", 20, 1.0)
        assert a != b


class TestStrategyConfigExtensions:
    """Tests for the new Phase 2 fields: name, conjunction, substrategies."""

    def test_default_name_empty(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365)
        assert cfg.name == ""

    def test_default_conjunction_and(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365)
        assert cfg.conjunction == "AND"

    def test_default_substrategies_empty(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365)
        assert cfg.substrategies == ()

    def test_custom_fields(self):
        sub = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365,
                             name="my_strat", conjunction="OR",
                             substrategies=(sub,))
        assert cfg.name == "my_strat"
        assert cfg.conjunction == "OR"
        assert len(cfg.substrategies) == 1
        assert cfg.substrategies[0] is sub

    def test_get_substrategies_from_populated(self):
        sub1 = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        sub2 = SubStrategy("get_rsi", "reversion_const_signal", 14, 0.5)
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365,
                             substrategies=(sub1, sub2))
        result = cfg.get_substrategies()
        assert len(result) == 2
        assert result[0] is sub1
        assert result[1] is sub2

    def test_get_substrategies_synthesizes_from_legacy(self):
        cfg = StrategyConfig("TEST", "get_bollinger_band",
                             Strategy.momentum_const_signal, 365)
        result = cfg.get_substrategies()
        assert len(result) == 1
        assert result[0].indicator_name == "get_bollinger_band"
        assert result[0].signal_func_name == "momentum_const_signal"

    def test_multi_substrategy_frozen(self):
        sub = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365,
                             substrategies=(sub,))
        with pytest.raises(TypeError):
            cfg.substrategies[0] = sub  # tuple is immutable


class TestStrategyConfigSingle:
    """Tests for StrategyConfig.single() convenience constructor."""

    def test_single_creates_substrategy(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_const_signal, 365,
            window=20, signal=1.0
        )
        assert len(cfg.substrategies) == 1
        sub = cfg.substrategies[0]
        assert sub.indicator_name == "get_bollinger_band"
        assert sub.signal_func_name == "momentum_const_signal"
        assert sub.window == 20
        assert sub.signal == 1.0
        assert sub.data_column == "v"

    def test_single_preserves_top_level(self):
        cfg = StrategyConfig.single(
            "AAPL", "get_sma", Strategy.reversion_const_signal, 252,
            window=50, signal=0.5
        )
        assert cfg.ticker == "AAPL"
        assert cfg.indicator_name == "get_sma"
        assert cfg.signal_func is Strategy.reversion_const_signal
        assert cfg.trading_period == 252
        assert cfg.strategy_id  # auto-generated

    def test_single_custom_data_column(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_const_signal, 365,
            window=10, signal=1.0, data_column="volume"
        )
        assert cfg.substrategies[0].data_column == "volume"

    def test_single_custom_strategy_id(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_const_signal, 365,
            window=10, signal=1.0, strategy_id="custom-id"
        )
        assert cfg.strategy_id == "custom-id"

    def test_single_custom_name(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_const_signal, 365,
            window=10, signal=1.0, name="my_strat"
        )
        assert cfg.name == "my_strat"


class TestStrategyToJson:
    def test_single_substrategy(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_const_signal, 365,
            window=20, signal=1.0, strategy_id="test-id"
        )
        result = strategy_to_json(cfg)
        assert result["strategy_id"] == "test-id"
        assert result["ticker"] == "BTC-USD"
        assert result["conjunction"] == "AND"
        assert result["trading_period"] == 365
        assert len(result["substrategies"]) == 1
        sub = result["substrategies"][0]
        assert sub["id"] == 1
        assert sub["indicator"] == "get_bollinger_band"
        assert sub["signal_func"] == "momentum_const_signal"
        assert sub["window"] == 20
        assert sub["signal"] == 1.0
        assert sub["data_column"] == "v"

    def test_multi_substrategy(self):
        sub1 = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        sub2 = SubStrategy("get_rsi", "reversion_const_signal", 14, 0.5)
        cfg = StrategyConfig(
            "AAPL", "get_sma", Strategy.momentum_const_signal, 252,
            strategy_id="multi-id", substrategies=(sub1, sub2)
        )
        result = strategy_to_json(cfg)
        assert len(result["substrategies"]) == 2
        assert result["substrategies"][0]["id"] == 1
        assert result["substrategies"][1]["id"] == 2
        assert result["substrategies"][1]["indicator"] == "get_rsi"

    def test_legacy_config_requires_window_signal(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365)
        with pytest.raises(ValueError, match="window and signal required"):
            strategy_to_json(cfg)

    def test_legacy_config_with_window_signal(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 365,
                             strategy_id="legacy-id")
        result = strategy_to_json(cfg, window=20, signal=1.0)
        assert result["strategy_id"] == "legacy-id"
        assert len(result["substrategies"]) == 1
        assert result["substrategies"][0]["window"] == 20
        assert result["substrategies"][0]["signal"] == 1.0

    def test_auto_name(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_const_signal, 365,
            window=20, signal=1.0, strategy_id="abcd1234-0000-0000-0000-000000000000"
        )
        result = strategy_to_json(cfg)
        assert result["name"] == "BTC-USD_strategy_abcd1234"

    def test_custom_name_preserved(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_const_signal, 365,
            window=20, signal=1.0, name="my_custom"
        )
        result = strategy_to_json(cfg)
        assert result["name"] == "my_custom"

    def test_created_at_present(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_const_signal, 365,
            window=20, signal=1.0
        )
        result = strategy_to_json(cfg)
        assert "created_at" in result
        assert "T" in result["created_at"]  # ISO format check

    def test_version_default_1(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_const_signal, 365,
            window=20, signal=1.0
        )
        result = strategy_to_json(cfg)
        assert result["version"] == 1


class TestBacktestResultsToJson:
    def test_structure(self):
        """Verify output structure with a mock Performance."""
        import pandas as pd
        from unittest.mock import MagicMock

        mock_perf = MagicMock()
        mock_perf.get_strategy_performance.return_value = pd.Series(
            {"sharpe": 1.5, "calmar": 2.0, "max_dd": 0.1})
        mock_perf.get_buy_hold_performance.return_value = pd.Series(
            {"sharpe": 0.8, "calmar": 1.0, "max_dd": 0.2})

        result = backtest_results_to_json(
            "strat-001", mock_perf, "BTC-USD",
            "2020-01-01", "2023-12-31", 5.0
        )
        assert result["strategy_id"] == "strat-001"
        assert result["ticker_backtested"] == "BTC-USD"
        assert result["fee_bps"] == 5.0
        assert result["data_range"]["start"] == "2020-01-01"
        assert result["data_range"]["end"] == "2023-12-31"
        assert result["metrics"]["sharpe"] == 1.5
        assert result["buy_hold_metrics"]["sharpe"] == 0.8
        assert "run_at" in result
