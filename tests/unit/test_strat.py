import numpy as np
import pytest

from strat import (Strategy, StrategyConfig, SubStrategy, SignalDirection,
                   strategy_to_json, backtest_results_to_json, combine_positions,
                   INDICATOR_DEFAULTS, resolve_signal_func)


class TestMomentumBandSignal:
    def test_long_when_above_signal(self):
        data = np.array([2.0, 3.0, 5.0])
        result = Strategy.momentum_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_short_when_below_neg_signal(self):
        data = np.array([-2.0, -3.0, -5.0])
        result = Strategy.momentum_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_flat_when_between_signals(self):
        data = np.array([0.0, 0.5, -0.5])
        result = Strategy.momentum_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_mixed_signals(self):
        data = np.array([2.0, 0.0, -2.0, 0.5, 1.5])
        result = Strategy.momentum_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [1.0, 0.0, -1.0, 0.0, 1.0])

    def test_nan_propagation(self):
        data = np.array([np.nan, 2.0, -2.0])
        result = Strategy.momentum_band_signal(data, 1.0)
        assert np.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == -1.0

    def test_zero_signal_threshold(self):
        data = np.array([0.1, -0.1, 0.0])
        result = Strategy.momentum_band_signal(data, 0.0)
        assert result[0] == 1.0
        assert result[1] == -1.0
        # Exactly zero: not > 0 and not < 0 → flat
        assert result[2] == 0.0

    def test_output_dtype_float(self):
        data = np.array([2.0, -2.0, 0.0])
        result = Strategy.momentum_band_signal(data, 1.0)
        assert result.dtype == float


class TestReversionBandSignal:
    def test_long_when_below_neg_signal(self):
        data = np.array([-2.0, -3.0, -5.0])
        result = Strategy.reversion_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_short_when_above_signal(self):
        data = np.array([2.0, 3.0, 5.0])
        result = Strategy.reversion_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_flat_when_between_signals(self):
        data = np.array([0.0, 0.5, -0.5])
        result = Strategy.reversion_band_signal(data, 1.0)
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_opposite_of_momentum(self):
        data = np.array([2.0, 0.0, -2.0, 0.5, 1.5])
        signal = 1.0
        mom = Strategy.momentum_band_signal(data, signal)
        rev = Strategy.reversion_band_signal(data, signal)
        # Reversion should be the negative of momentum (where not flat)
        np.testing.assert_array_equal(rev, -mom)

    def test_nan_propagation(self):
        data = np.array([np.nan, -2.0, 2.0])
        result = Strategy.reversion_band_signal(data, 1.0)
        assert np.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == -1.0


class TestStrategyConfig:
    def test_frozen_dataclass(self):
        cfg = StrategyConfig("TEST", "get_bollinger_band",
                             Strategy.momentum_band_signal, 365)
        with pytest.raises(AttributeError):
            cfg.trading_period = 252

    def test_fields(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.reversion_band_signal, 252)
        assert cfg.ticker == "TEST"
        assert cfg.indicator_name == "get_sma"
        assert cfg.signal_func is Strategy.reversion_band_signal
        assert cfg.trading_period == 252
        assert cfg.strategy_id  # auto-generated UUID is non-empty

    def test_equality(self):
        a = StrategyConfig("TEST", "get_ema", Strategy.momentum_band_signal, 365,
                           strategy_id="same-id")
        b = StrategyConfig("TEST", "get_ema", Strategy.momentum_band_signal, 365,
                           strategy_id="same-id")
        assert a == b

    def test_inequality(self):
        a = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365,
                           strategy_id="id-a")
        b = StrategyConfig("TEST", "get_ema", Strategy.momentum_band_signal, 365,
                           strategy_id="id-b")
        assert a != b


# -------------------------------------------------------------------------
# Phase 2: SubStrategy, StrategyConfig extensions, JSON serialization
# -------------------------------------------------------------------------

class TestSubStrategy:
    def test_frozen_dataclass(self):
        sub = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        with pytest.raises(AttributeError):
            sub.window = 30

    def test_default_data_column(self):
        sub = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        assert sub.data_column == "v"

    def test_custom_data_column(self):
        sub = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0,
                          data_column="volume")
        assert sub.data_column == "volume"

    def test_resolve_signal_func_momentum(self):
        sub = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        fn = sub.resolve_signal_func()
        assert fn is SignalDirection.momentum_band_signal

    def test_resolve_signal_func_reversion(self):
        sub = SubStrategy("get_sma", "reversion_band_signal", 20, 1.0)
        fn = sub.resolve_signal_func()
        assert fn is SignalDirection.reversion_band_signal

    def test_resolve_signal_func_invalid(self):
        sub = SubStrategy("get_sma", "nonexistent_signal", 20, 1.0)
        with pytest.raises(AttributeError):
            sub.resolve_signal_func()

    def test_equality(self):
        a = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        b = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        assert a == b

    def test_inequality(self):
        a = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        b = SubStrategy("get_sma", "reversion_band_signal", 20, 1.0)
        assert a != b


class TestStrategyConfigExtensions:
    """Tests for the new Phase 2 fields: name, conjunction, substrategies."""

    def test_default_name_empty(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365)
        assert cfg.name == ""

    def test_default_conjunction_and(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365)
        assert cfg.conjunction == "AND"

    def test_default_substrategies_empty(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365)
        assert cfg.substrategies == ()

    def test_custom_fields(self):
        sub = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365,
                             name="my_strat", conjunction="OR",
                             substrategies=(sub,))
        assert cfg.name == "my_strat"
        assert cfg.conjunction == "OR"
        assert len(cfg.substrategies) == 1
        assert cfg.substrategies[0] is sub

    def test_get_substrategies_from_populated(self):
        sub1 = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        sub2 = SubStrategy("get_rsi", "reversion_band_signal", 14, 0.5)
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365,
                             substrategies=(sub1, sub2))
        result = cfg.get_substrategies()
        assert len(result) == 2
        assert result[0] is sub1
        assert result[1] is sub2

    def test_get_substrategies_synthesizes_from_legacy(self):
        cfg = StrategyConfig("TEST", "get_bollinger_band",
                             Strategy.momentum_band_signal, 365)
        result = cfg.get_substrategies()
        assert len(result) == 1
        assert result[0].indicator_name == "get_bollinger_band"
        assert result[0].signal_func_name == "momentum_band_signal"

    def test_multi_substrategy_frozen(self):
        sub = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365,
                             substrategies=(sub,))
        with pytest.raises(TypeError):
            cfg.substrategies[0] = sub  # tuple is immutable


class TestStrategyConfigSingle:
    """Tests for StrategyConfig.single() convenience constructor."""

    def test_single_creates_substrategy(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_band_signal, 365,
            window=20, signal=1.0
        )
        assert len(cfg.substrategies) == 1
        sub = cfg.substrategies[0]
        assert sub.indicator_name == "get_bollinger_band"
        assert sub.signal_func_name == "momentum_band_signal"
        assert sub.window == 20
        assert sub.signal == 1.0
        assert sub.data_column == "v"

    def test_single_preserves_top_level(self):
        cfg = StrategyConfig.single(
            "AAPL", "get_sma", Strategy.reversion_band_signal, 252,
            window=50, signal=0.5
        )
        assert cfg.ticker == "AAPL"
        assert cfg.indicator_name == "get_sma"
        assert cfg.signal_func is Strategy.reversion_band_signal
        assert cfg.trading_period == 252
        assert cfg.strategy_id  # auto-generated

    def test_single_custom_data_column(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_band_signal, 365,
            window=10, signal=1.0, data_column="volume"
        )
        assert cfg.substrategies[0].data_column == "volume"

    def test_single_custom_strategy_id(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_band_signal, 365,
            window=10, signal=1.0, strategy_id="custom-id"
        )
        assert cfg.strategy_id == "custom-id"

    def test_single_custom_name(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_band_signal, 365,
            window=10, signal=1.0, name="my_strat"
        )
        assert cfg.name == "my_strat"


class TestStrategyToJson:
    def test_single_substrategy(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_band_signal, 365,
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
        assert sub["signal_func"] == "momentum_band_signal"
        assert sub["window"] == 20
        assert sub["signal"] == 1.0
        assert sub["data_column"] == "v"

    def test_multi_substrategy(self):
        sub1 = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        sub2 = SubStrategy("get_rsi", "reversion_band_signal", 14, 0.5)
        cfg = StrategyConfig(
            "AAPL", "get_sma", Strategy.momentum_band_signal, 252,
            strategy_id="multi-id", substrategies=(sub1, sub2)
        )
        result = strategy_to_json(cfg)
        assert len(result["substrategies"]) == 2
        assert result["substrategies"][0]["id"] == 1
        assert result["substrategies"][1]["id"] == 2
        assert result["substrategies"][1]["indicator"] == "get_rsi"

    def test_legacy_config_requires_window_signal(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365)
        with pytest.raises(ValueError, match="window and signal required"):
            strategy_to_json(cfg)

    def test_legacy_config_with_window_signal(self):
        cfg = StrategyConfig("TEST", "get_sma", Strategy.momentum_band_signal, 365,
                             strategy_id="legacy-id")
        result = strategy_to_json(cfg, window=20, signal=1.0)
        assert result["strategy_id"] == "legacy-id"
        assert len(result["substrategies"]) == 1
        assert result["substrategies"][0]["window"] == 20
        assert result["substrategies"][0]["signal"] == 1.0

    def test_auto_name(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_band_signal, 365,
            window=20, signal=1.0, strategy_id="abcd1234-0000-0000-0000-000000000000"
        )
        result = strategy_to_json(cfg)
        assert result["name"] == "BTC-USD_strategy_abcd1234"

    def test_custom_name_preserved(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_band_signal, 365,
            window=20, signal=1.0, name="my_custom"
        )
        result = strategy_to_json(cfg)
        assert result["name"] == "my_custom"

    def test_created_at_present(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_band_signal, 365,
            window=20, signal=1.0
        )
        result = strategy_to_json(cfg)
        assert "created_at" in result
        assert "T" in result["created_at"]  # ISO format check

    def test_version_default_1(self):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_sma", Strategy.momentum_band_signal, 365,
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


# -------------------------------------------------------------------------
# Phase 3: combine_positions
# -------------------------------------------------------------------------

class TestCombinePositions:
    def test_and_unanimous_long(self):
        a = np.array([1.0, 1.0, 1.0])
        b = np.array([1.0, 1.0, 1.0])
        result = combine_positions([a, b], "AND")
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_and_unanimous_short(self):
        a = np.array([-1.0, -1.0, -1.0])
        b = np.array([-1.0, -1.0, -1.0])
        result = combine_positions([a, b], "AND")
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_and_disagree_gives_flat(self):
        a = np.array([1.0, -1.0, 1.0, 0.0])
        b = np.array([-1.0, 1.0, 0.0, 1.0])
        result = combine_positions([a, b], "AND")
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0, 0.0])

    def test_and_one_flat_gives_flat(self):
        a = np.array([1.0, -1.0, 0.0])
        b = np.array([0.0, -1.0, 0.0])
        result = combine_positions([a, b], "AND")
        np.testing.assert_array_equal(result, [0.0, -1.0, 0.0])

    def test_or_any_long(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        result = combine_positions([a, b], "OR")
        np.testing.assert_array_equal(result, [1.0, 1.0, 0.0])

    def test_or_any_short(self):
        a = np.array([0.0, -1.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        result = combine_positions([a, b], "OR")
        np.testing.assert_array_equal(result, [-1.0, -1.0, 0.0])

    def test_or_mixed_positive_wins(self):
        """When one factor is long and another short, positive wins in OR."""
        a = np.array([1.0, -1.0])
        b = np.array([-1.0, 1.0])
        result = combine_positions([a, b], "OR")
        np.testing.assert_array_equal(result, [1.0, 1.0])

    def test_single_factor_passthrough(self):
        a = np.array([1.0, 0.0, -1.0, 0.0])
        result = combine_positions([a], "AND")
        np.testing.assert_array_equal(result, a)

    def test_single_factor_returns_copy(self):
        a = np.array([1.0, 0.0, -1.0])
        result = combine_positions([a])
        assert result is not a

    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            combine_positions([])

    def test_nan_propagation(self):
        a = np.array([np.nan, 1.0, -1.0])
        b = np.array([1.0, np.nan, -1.0])
        result = combine_positions([a, b], "AND")
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == -1.0

    def test_three_factors_and(self):
        a = np.array([1.0, 1.0, -1.0])
        b = np.array([1.0, -1.0, -1.0])
        c = np.array([1.0, 1.0, -1.0])
        result = combine_positions([a, b, c], "AND")
        np.testing.assert_array_equal(result, [1.0, 0.0, -1.0])

    def test_three_factors_or(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([0.0, 0.0, -1.0])
        c = np.array([0.0, 1.0, 0.0])
        result = combine_positions([a, b, c], "OR")
        np.testing.assert_array_equal(result, [0.0, 1.0, -1.0])

    def test_case_insensitive_conjunction(self):
        a = np.array([1.0, -1.0])
        b = np.array([1.0, -1.0])
        result_lower = combine_positions([a, b], "and")
        result_upper = combine_positions([a, b], "AND")
        np.testing.assert_array_equal(result_lower, result_upper)

    # --- Signal-strength conflict resolution (percentile rank) ---
    # Tests use 10-element arrays so percentile rank has enough history
    # to distinguish extreme from moderate readings.

    def test_and_disagree_strength_wins(self):
        """AND + strengths: disagreement resolved by strongest factor."""
        # Rows 0-1 disagree; rows 2-9 are filler (both flat)
        a = np.array([1.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        b = np.array([-1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # sa: readings near the middle of distribution → low conviction
        sa = np.array([50, 50, 48, 52, 49, 51, 48, 52, 49, 51])
        # sb: extreme readings on rows 0/1 → high conviction → b wins
        sb = np.array([99, 1, 50, 50, 50, 50, 50, 50, 50, 50])
        result = combine_positions([a, b], "AND", strengths=[sa, sb])
        assert result[0] == -1.0  # b wins (99 = extreme high percentile)
        assert result[1] == 1.0   # b wins (1 = extreme low percentile)

    def test_or_conflict_strength_wins(self):
        """OR + strengths: conflict resolved by strongest factor."""
        a = np.array([1.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        b = np.array([-1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # a extreme on row 0, b extreme on row 1
        sa = np.array([99, 50, 50, 50, 50, 50, 50, 50, 50, 50])
        sb = np.array([50, 99, 50, 50, 50, 50, 50, 50, 50, 50])
        result = combine_positions([a, b], "OR", strengths=[sa, sb])
        assert result[0] == 1.0   # a wins row 0 (a more extreme)
        assert result[1] == 1.0   # b wins row 1 (b more extreme)

    def test_and_strength_ignores_flat_factors(self):
        """Flat (0) factors don't compete in strength tiebreak."""
        a = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        b = np.array([0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        sa = np.array([50, 50, 48, 52, 49, 51, 48, 52, 49, 51])
        sb = np.array([50, 50, 48, 52, 49, 51, 48, 52, 49, 51])
        result = combine_positions([a, b], "AND", strengths=[sa, sb])
        # Row 0: a=+1 b=0 → only a has signal → a wins (+1)
        # Row 1: a=0 b=-1 → only b has signal → b wins (-1)
        assert result[0] == 1.0
        assert result[1] == -1.0

    def test_three_factors_strength_tiebreak(self):
        """Three factors disagree, percentile rank picks the winner."""
        a = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        c = np.array([-1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # b has the most extreme reading on row 0 → b wins
        sa = np.array([50, 48, 52, 49, 51, 50, 48, 52, 49, 51])
        sb = np.array([99, 48, 52, 49, 51, 50, 48, 52, 49, 51])
        sc = np.array([50, 48, 52, 49, 51, 50, 48, 52, 49, 51])
        result = combine_positions([a, b, c], "AND", strengths=[sa, sb, sc])
        assert result[0] == -1.0  # b wins (most extreme)

    def test_strengths_none_preserves_legacy(self):
        """Without strengths, AND disagree stays flat, OR conflict positive wins."""
        a = np.array([1.0, 1.0])
        b = np.array([-1.0, -1.0])
        and_result = combine_positions([a, b], "AND", strengths=None)
        or_result = combine_positions([a, b], "OR", strengths=None)
        np.testing.assert_array_equal(and_result, [0.0, 0.0])
        np.testing.assert_array_equal(or_result, [1.0, 1.0])

    # --- FILTER conjunction mode ---

    def test_filter_gate_active_uses_signal_direction(self):
        """FILTER: gate active (+1) → use signal factor direction."""
        gate = np.array([1.0, 1.0, 1.0, 0.0])   # active except row 3
        signal = np.array([1.0, -1.0, 0.0, 1.0])  # direction
        result = combine_positions([gate, signal], "FILTER")
        np.testing.assert_array_equal(result, [1.0, -1.0, 0.0, 0.0])

    def test_filter_gate_inactive_gives_flat(self):
        """FILTER: gate inactive (0) → always flat regardless of signal."""
        gate = np.array([0.0, 0.0, 0.0])
        signal = np.array([1.0, -1.0, 0.0])
        result = combine_positions([gate, signal], "FILTER")
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_filter_gate_negative_counts_as_active(self):
        """FILTER: gate -1 is still active (non-zero), direction comes from signal."""
        gate = np.array([-1.0, -1.0])
        signal = np.array([1.0, -1.0])
        result = combine_positions([gate, signal], "FILTER")
        np.testing.assert_array_equal(result, [1.0, -1.0])

    def test_filter_three_factors_signals_agree(self):
        """FILTER with 3 factors: gate + 2 signals AND-combined."""
        gate = np.array([1.0, 1.0, 1.0, 0.0])
        sig_a = np.array([1.0, 1.0, -1.0, 1.0])
        sig_b = np.array([1.0, -1.0, -1.0, 1.0])
        result = combine_positions([gate, sig_a, sig_b], "FILTER")
        # Row 0: gate on, both +1 → +1
        # Row 1: gate on, disagree → 0 (AND of signals)
        # Row 2: gate on, both -1 → -1
        # Row 3: gate off → 0
        np.testing.assert_array_equal(result, [1.0, 0.0, -1.0, 0.0])

    def test_filter_nan_propagation(self):
        """FILTER: NaN in gate or signal → NaN in output."""
        gate = np.array([np.nan, 1.0, 1.0])
        signal = np.array([1.0, np.nan, -1.0])
        result = combine_positions([gate, signal], "FILTER")
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == -1.0

    def test_filter_case_insensitive(self):
        gate = np.array([1.0, 0.0])
        signal = np.array([1.0, -1.0])
        result = combine_positions([gate, signal], "filter")
        np.testing.assert_array_equal(result, [1.0, 0.0])

    def test_invalid_conjunction_raises(self):
        a = np.array([1.0])
        with pytest.raises(ValueError, match="conjunction must be"):
            combine_positions([a, a], "XOR")


class TestIndicatorDefaults:
    REQUIRED_KEYS = {"win_min", "win_max", "win_step",
                     "sig_min", "sig_max", "sig_step"}

    def test_all_indicators_have_defaults(self):
        expected = {"get_sma", "get_ema", "get_rsi",
                    "get_bollinger_band", "get_stochastic_oscillator"}
        assert set(INDICATOR_DEFAULTS.keys()) == expected

    def test_all_entries_have_required_keys(self):
        for name, bounds in INDICATOR_DEFAULTS.items():
            missing = self.REQUIRED_KEYS - set(bounds.keys())
            assert not missing, f"{name} missing keys: {missing}"

    def test_min_less_than_max(self):
        for name, b in INDICATOR_DEFAULTS.items():
            assert b["win_min"] < b["win_max"], f"{name}: win_min >= win_max"
            if b["sig_min"] is not None:
                assert b["sig_min"] < b["sig_max"], f"{name}: sig_min >= sig_max"

    def test_bounded_indicators_have_sig_range(self):
        for name in ("get_rsi", "get_stochastic_oscillator"):
            b = INDICATOR_DEFAULTS[name]
            assert b["sig_min"] == 0.0, f"{name}: sig_min should be 0.0"
            assert b["sig_max"] == 100.0, f"{name}: sig_max should be 100.0"
            assert b["sig_step"] == 5.0, f"{name}: sig_step should be 5.0"

    def test_window_min_at_least_two(self):
        for name, b in INDICATOR_DEFAULTS.items():
            assert b["win_min"] >= 2, f"{name}: win_min < 2"

    def test_bollinger_window_min_at_least_ten(self):
        assert INDICATOR_DEFAULTS["get_bollinger_band"]["win_min"] >= 10


# -------------------------------------------------------------------------
# Band signals (renamed from _const)
# -------------------------------------------------------------------------
# Bounded signals (new — for 0–100 indicators like RSI, stochastic)
# -------------------------------------------------------------------------

class TestMomentumBoundedSignal:
    def test_long_when_above_signal(self):
        data = np.array([75.0, 80.0, 90.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_short_when_below_lower(self):
        data = np.array([25.0, 20.0, 10.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_flat_in_middle(self):
        data = np.array([35.0, 50.0, 65.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_boundary_values(self):
        data = np.array([30.0, 70.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        # Exactly at threshold: not > 70 and not < 30 → flat
        np.testing.assert_array_equal(result, [0.0, 0.0])

    def test_mixed_signals(self):
        data = np.array([75.0, 50.0, 25.0, 30.0, 71.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [1.0, 0.0, -1.0, 0.0, 1.0])

    def test_nan_propagation(self):
        data = np.array([np.nan, 75.0, 25.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        assert np.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == -1.0

    def test_output_dtype_float(self):
        data = np.array([75.0, 25.0, 50.0])
        result = Strategy.momentum_bounded_signal(data, 70.0)
        assert result.dtype == float

    def test_symmetric_with_signal_50(self):
        """signal=50 → lower=50, so > 50 long, < 50 short, == 50 flat."""
        data = np.array([51.0, 49.0, 50.0])
        result = Strategy.momentum_bounded_signal(data, 50.0)
        np.testing.assert_array_equal(result, [1.0, -1.0, 0.0])


class TestReversionBoundedSignal:
    def test_long_when_below_lower(self):
        data = np.array([25.0, 20.0, 10.0])
        result = Strategy.reversion_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_short_when_above_signal(self):
        data = np.array([75.0, 80.0, 90.0])
        result = Strategy.reversion_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [-1.0, -1.0, -1.0])

    def test_flat_in_middle(self):
        data = np.array([35.0, 50.0, 65.0])
        result = Strategy.reversion_bounded_signal(data, 70.0)
        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])

    def test_opposite_of_momentum_bounded(self):
        data = np.array([75.0, 50.0, 25.0, 30.0, 71.0])
        signal = 70.0
        mom = Strategy.momentum_bounded_signal(data, signal)
        rev = Strategy.reversion_bounded_signal(data, signal)
        np.testing.assert_array_equal(rev, -mom)

    def test_nan_propagation(self):
        data = np.array([np.nan, 25.0, 75.0])
        result = Strategy.reversion_bounded_signal(data, 70.0)
        assert np.isnan(result[0])
        assert result[1] == 1.0
        assert result[2] == -1.0

    def test_output_dtype_float(self):
        data = np.array([75.0, 25.0, 50.0])
        result = Strategy.reversion_bounded_signal(data, 70.0)
        assert result.dtype == float


# -------------------------------------------------------------------------
# resolve_signal_func
# -------------------------------------------------------------------------

class TestResolveSignalFunc:
    """Tests for the DB-driven signal function resolver."""

    INDICATOR_ROWS = [
        {"method_name": "get_bollinger_band", "is_bounded_ind": "N"},
        {"method_name": "get_sma", "is_bounded_ind": "N"},
        {"method_name": "get_rsi", "is_bounded_ind": "Y"},
        {"method_name": "get_stochastic_oscillator", "is_bounded_ind": "Y"},
    ]
    SIGNAL_TYPE_ROWS = [
        {"name": "momentum", "func_name_band": "momentum_band_signal",
         "func_name_bounded": "momentum_bounded_signal"},
        {"name": "reversion", "func_name_band": "reversion_band_signal",
         "func_name_bounded": "reversion_bounded_signal"},
    ]

    def test_unbounded_momentum_returns_band(self):
        fn = resolve_signal_func("momentum", "get_bollinger_band",
                                 self.INDICATOR_ROWS, self.SIGNAL_TYPE_ROWS)
        assert fn is SignalDirection.momentum_band_signal

    def test_unbounded_reversion_returns_band(self):
        fn = resolve_signal_func("reversion", "get_sma",
                                 self.INDICATOR_ROWS, self.SIGNAL_TYPE_ROWS)
        assert fn is SignalDirection.reversion_band_signal

    def test_bounded_momentum_returns_bounded(self):
        fn = resolve_signal_func("momentum", "get_rsi",
                                 self.INDICATOR_ROWS, self.SIGNAL_TYPE_ROWS)
        assert fn is SignalDirection.momentum_bounded_signal

    def test_bounded_reversion_returns_bounded(self):
        fn = resolve_signal_func("reversion", "get_stochastic_oscillator",
                                 self.INDICATOR_ROWS, self.SIGNAL_TYPE_ROWS)
        assert fn is SignalDirection.reversion_bounded_signal

    def test_unknown_indicator_raises(self):
        with pytest.raises(ValueError, match="Unknown indicator"):
            resolve_signal_func("momentum", "get_nonexistent",
                                self.INDICATOR_ROWS, self.SIGNAL_TYPE_ROWS)

    def test_unknown_signal_type_raises(self):
        with pytest.raises(ValueError, match="Unknown signal type"):
            resolve_signal_func("unknown", "get_rsi",
                                self.INDICATOR_ROWS, self.SIGNAL_TYPE_ROWS)
