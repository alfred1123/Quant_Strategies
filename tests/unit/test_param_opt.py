import itertools
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from optuna.samplers import TPESampler

from quant.strategy.signals import Strategy, StrategyConfig, SubStrategy, SignalDirection
from quant.strategy.optimizer import (
    BayesianSearch,
    ExhaustiveSearch,
    OptimizeResult,
    OverBudgetGrid,
    ParametersOptimization,
    RANDOM_DISTINCT,
    RandomDistinctSearch,
    REJECT,
    SearchPolicy,
    SearchSpace,
    SearchStrategy,
    TPE_DISTINCT,
)
from tests.policy import WIDE


_BOLLINGER_CONFIG = StrategyConfig("test", "get_bollinger_band",
                                   Strategy.momentum_band_signal, 252)


class TestParametersOptimization:
    def _make_optimizer(self, df, search=WIDE):
        return ParametersOptimization(
            {_BOLLINGER_CONFIG.internal_cusip: df.copy()},
            _BOLLINGER_CONFIG,
            search=search,
        )

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

    def test_budget_below_the_grid_uses_tpe(self, sample_ohlc_df):
        """A budget smaller than the grid scores that many distinct cells."""
        opt = self._make_optimizer(
            sample_ohlc_df,
            SearchPolicy(3, 42, 3, TPE_DISTINCT),
        )
        result = opt.optimize((5, 10, 15, 20), (0.5, 1.0, 1.5))
        assert result.search == "TPE sample"
        assert result.distinct_cells == 3
        assert len(result.grid_df) == 3

    def test_starved_window_scores_nan(self, sample_ohlc_df):
        """A window that leaves too few PnL bars scores NaN via Performance."""
        opt = self._make_optimizer(sample_ohlc_df)
        # 100 bars, window 50 → 50 remaining < Performance.MIN_METRIC_OBS
        result = opt.optimize((5, 50), (0.5,))
        starved = result.grid_df[result.grid_df["window"] == 50]
        assert starved["sharpe"].isna().all()
        ok = result.grid_df[result.grid_df["window"] == 5]
        assert ok["sharpe"].notna().all()


class TestParametersOptimizationWithConfig:
    def test_config_stored(self, sample_ohlc_df):
        config = StrategyConfig("test", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        opt = ParametersOptimization({config.internal_cusip: sample_ohlc_df.copy()}, config, search=WIDE)
        assert opt.config is config

    def test_fee_propagates(self, sample_ohlc_df):
        config = StrategyConfig("test", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        opt = ParametersOptimization({config.internal_cusip: sample_ohlc_df.copy()}, config, fee_bps=20.0, search=WIDE)
        assert opt.fee_bps == 20.0


# -------------------------------------------------------------------------
# Phase 4: Multi-factor grid search
# -------------------------------------------------------------------------

def _multi_factor_config(**overrides):
    sub_a = SubStrategy("get_sma", "momentum_band_signal", 5, 0.5, "v")
    sub_b = SubStrategy("get_sma", "momentum_band_signal", 10, 0.5, "volume")
    defaults = dict(
        internal_cusip="test",
        indicator_name="get_sma",
        signal_func=SignalDirection.momentum_band_signal,
        trading_period=252,
        conjunction="AND",
        substrategies=(sub_a, sub_b),
    )
    defaults.update(overrides)
    return StrategyConfig(**defaults)


class TestOptimizeMulti:
    def test_returns_result(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
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
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        result = opt.optimize_multi(
            [(5, 10, 15), (5, 10)],
            [(0.5, 1.0), (0.5,)],
        )
        # Factor 0: 3 windows × 2 signals = 6.  Factor 1: 2 × 1 = 2.  Total: 12.
        assert len(result.grid_df) == 12

    def test_covers_all_combinations(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
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
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        result = opt.optimize_multi(
            [(5,), (10,)],
            [(0.5,), (0.5,)],
        )
        assert len(result.grid_df) == 1
        assert isinstance(result.grid_df.iloc[0]["sharpe"], (int, float, np.floating))

    def test_mismatched_ranges_raises(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        with pytest.raises(ValueError, match="window_ranges has 2.*signal_ranges has 1"):
            opt.optimize_multi([(5,), (10,)], [(0.5,)])

    def test_large_grid_uses_tpe(self, multi_factor_df, caplog):
        config = _multi_factor_config()
        opt = ParametersOptimization(
            {config.internal_cusip: multi_factor_df.copy()},
            config,
            search=SearchPolicy(2, 42, 3, TPE_DISTINCT),
        )
        big_range = tuple(range(1, 201))
        import logging
        with caplog.at_level(logging.INFO):
            result = opt.optimize_multi(
                [big_range, big_range], [big_range, big_range],
            )
        assert any("TPE" in rec.message for rec in caplog.records)
        assert result.distinct_cells == 2
        assert len(result.grid_df) == 2

    def test_or_conjunction(self, multi_factor_df):
        config = _multi_factor_config(conjunction="OR")
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        result = opt.optimize_multi(
            [(5,), (10,)],
            [(0.5,), (0.5,)],
        )
        assert len(result.grid_df) == 1
        assert isinstance(result.grid_df.iloc[0]["sharpe"], (int, float, np.floating))

    def test_best_sharpe_selection(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        result = opt.optimize_multi(
            [(5, 10, 20), (5, 10)],
            [(0.5, 1.0), (0.5,)],
        )
        assert result.best["sharpe"] == result.grid_df["sharpe"].max()

    def test_budget_limits_evaluations(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization(
            {config.internal_cusip: multi_factor_df.copy()},
            config,
            search=SearchPolicy(3, 42, 3, TPE_DISTINCT),
        )
        result = opt.optimize_multi(
            [(5, 10, 20), (5, 10)],
            [(0.5, 1.0), (0.5,)],
        )
        assert result.distinct_cells == 3
        assert len(result.grid_df) == 3


# -------------------------------------------------------------------------
# study exposure
# -------------------------------------------------------------------------

class TestStudy:
    def test_study_set_after_optimize(self, sample_ohlc_df):
        opt = ParametersOptimization({_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()}, _BOLLINGER_CONFIG, search=WIDE)
        result = opt.optimize((5, 10), (0.5, 1.0))
        assert result.study is not None
        assert len(result.study.trials) == 4

    def test_study_set_after_optimize_multi(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        result = opt.optimize_multi([(5, 10), (5, 10)], [(0.5,), (0.5,)])
        assert result.study is not None
        assert len(result.study.trials) == 4

    def test_study_independent_per_call(self, sample_ohlc_df):
        opt = ParametersOptimization({_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()}, _BOLLINGER_CONFIG, search=WIDE)
        result1 = opt.optimize((5,), (0.5,))
        result2 = opt.optimize((5, 10), (0.5, 1.0))
        assert result1.study is not result2.study
        assert len(result2.study.trials) == 4


# -------------------------------------------------------------------------
# callbacks parameter
# -------------------------------------------------------------------------

class TestCallbacks:
    def test_optimize_callback_called_per_trial(self, sample_ohlc_df):
        opt = ParametersOptimization({_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()}, _BOLLINGER_CONFIG, search=WIDE)
        calls = []
        opt.optimize((5, 10), (0.5, 1.0),
                     callbacks=[lambda study, trial: calls.append(1)])
        assert len(calls) == 4  # 2 windows × 2 signals

    def test_optimize_multi_callback_called_per_trial(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
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
        opt = ParametersOptimization({_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()}, _BOLLINGER_CONFIG, search=WIDE)
        result = opt.run((5, 10), (0.5, 1.0))
        assert isinstance(result, OptimizeResult)
        assert list(result.grid_df.columns) == ["window", "signal", "sharpe"]
        assert len(result.grid_df) == 4

    def test_run_dispatches_multi(self, multi_factor_df):
        config = _multi_factor_config()
        opt = ParametersOptimization({config.internal_cusip: multi_factor_df.copy()}, config, search=WIDE)
        result = opt.run([(5, 10), (5, 10)], [(0.5,), (0.5,)])
        assert isinstance(result, OptimizeResult)
        assert "window_0" in result.grid_df.columns
        assert len(result.grid_df) == 4

    def test_optimize_no_callbacks_default(self, sample_ohlc_df):
        """Callbacks default to None — optimization still works."""
        opt = ParametersOptimization({_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()}, _BOLLINGER_CONFIG, search=WIDE)
        result = opt.optimize((5,), (0.5,))
        assert len(result.grid_df) == 1


def _policy(budget, mode=TPE_DISTINCT, factor=3, seed=42) -> SearchPolicy:
    return SearchPolicy(budget, seed, factor, mode)


def _opt_for(policy: SearchPolicy) -> ParametersOptimization:
    return ParametersOptimization({"test": None}, _BOLLINGER_CONFIG, search=policy)


class TestSearchSelection:
    def test_budget_covers_the_grid(self):
        search = _opt_for(_policy(12))._select_search(12)
        assert isinstance(search, ExhaustiveSearch)

    def test_budget_above_the_grid_is_exhaustive(self):
        search = _opt_for(_policy(100))._select_search(12)
        assert isinstance(search, ExhaustiveSearch)

    def test_over_budget_tpe(self):
        search = _opt_for(_policy(3, TPE_DISTINCT))._select_search(12)
        assert isinstance(search, BayesianSearch)

    def test_over_budget_random(self):
        search = _opt_for(_policy(3, RANDOM_DISTINCT))._select_search(12)
        assert isinstance(search, RandomDistinctSearch)

    def test_reject_mode_refuses_the_grid(self):
        opt = _opt_for(_policy(3, REJECT))
        with pytest.raises(OverBudgetGrid, match="exceeds the trial budget"):
            opt._select_search(12)

    def test_unknown_mode_is_refused(self):
        opt = _opt_for(_policy(3, "GRID_SAMPLER"))
        with pytest.raises(ValueError, match="OVER_BUDGET_MODE"):
            opt._select_search(12)


class TestExhaustiveSearch:
    def test_visits_every_combination(self, sample_ohlc_df):
        opt = ParametersOptimization(
            {_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()},
            _BOLLINGER_CONFIG, search=WIDE)
        result = opt.optimize((5, 10, 15), (0.5, 1.0))
        assert len(result.grid_df) == 6
        assert all(
            t.state.name == "COMPLETE" for t in result.study.get_trials(deepcopy=False)
        )

    def test_callback_numbers_and_running_best(self, sample_ohlc_df):
        opt = ParametersOptimization(
            {_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()},
            _BOLLINGER_CONFIG, search=WIDE)
        numbers = []
        bests = []

        def on_trial(study, trial):
            numbers.append(trial.number)
            bests.append(study.best_value)

        opt.optimize((5, 10), (0.5, 1.0), callbacks=[on_trial])
        assert numbers == [0, 1, 2, 3]
        assert bests == list(np.maximum.accumulate(bests))

    def test_extract_plots_available(self, sample_ohlc_df):
        opt = ParametersOptimization(
            {_BOLLINGER_CONFIG.internal_cusip: sample_ohlc_df.copy()},
            _BOLLINGER_CONFIG, search=WIDE)
        result = opt.optimize((5, 10), (0.5, 1.0))
        assert result.extract_plots() is not None


def _price_frame(n=500, seed=42):
    """The series the distinct-cell repro was measured on (seed 42, 500 bars)."""
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "Open": close,
        "High": close + 0.3,
        "Low": close - 0.3,
        "Close": close,
        "price": close,
        "factor": close,
        "v": close,
        "volume": np.abs(close) * 10,
    }, index=pd.date_range("2020-01-01", periods=n, freq="D", name="datetime"))


def _scored(opt, method, *args, **kwargs):
    calls = []
    real = SearchStrategy.evaluate

    def wrapped(self, objective, windows, signals):
        calls.append((windows, signals))
        return real(self, objective, windows, signals)

    with patch.object(SearchStrategy, "evaluate", wrapped):
        result = getattr(opt, method)(*args, **kwargs)
    return result, calls


class _FirstCell(TPESampler):
    """Every categorical axis returns its first choice, so every proposal repeats."""

    def infer_relative_search_space(self, study, trial):
        return {}

    def sample_relative(self, study, trial, search_space):
        return {}

    def sample_independent(self, study, trial, param_name, param_distribution):
        return param_distribution.choices[0]


class TestDistinctBudget:
    """An over-budget grid spends the budget on distinct cells.

    On main, TPE with ``n_trials=20`` on this 25-cell grid (seed 42, 500 bars)
    scores the objective 20 times and records 15 distinct cells.
    """

    WINDOWS = (5, 10, 15, 20, 25)
    SIGNALS = (0.5, 1.0, 1.5, 2.0, 2.5)

    def _opt(self, frame, policy):
        return ParametersOptimization(
            {_BOLLINGER_CONFIG.internal_cusip: frame},
            _BOLLINGER_CONFIG,
            search=policy,
        )

    def test_budget_buys_distinct_cells(self):
        frame = _price_frame()
        opt = self._opt(frame, _policy(20))
        result, calls = _scored(opt, "optimize", self.WINDOWS, self.SIGNALS)
        keys = list(zip(result.grid_df["window"], result.grid_df["signal"]))
        assert result.grid_size == 25
        assert result.search == "TPE sample"
        assert result.distinct_cells == 20
        assert len(keys) == 20
        assert len(set(keys)) == 20
        assert len(calls) == 20
        assert len(result.grid) == 20
        assert result.n_valid == int(result.grid_df["sharpe"].notna().sum())
        top = [(row["window"], row["signal"]) for row in result.top10]
        assert len(top) == len(set(top))

    def test_attempt_cap_stops_before_the_budget(self):
        frame = _price_frame()
        opt = self._opt(frame, _policy(5, factor=1))
        with patch("quant.strategy.optimizer.TPESampler", _FirstCell):
            result, calls = _scored(opt, "optimize", self.WINDOWS, self.SIGNALS)
        assert result.attempts == 5
        assert result.distinct_cells == 1
        assert result.distinct_cells < 5
        assert len(calls) == 1
        assert len(result.grid_df) == 1

    def test_grid_smaller_than_the_budget_is_exhaustive(self):
        frame = _price_frame(n=120)
        opt = self._opt(frame, _policy(100))
        result, calls = _scored(opt, "optimize", (5, 10), (0.5, 1.0))
        assert result.search == "exhaustive"
        assert result.grid_size == 4
        assert result.distinct_cells == 4
        assert result.attempts == 4
        assert len(calls) == 4

    def test_budget_one_below_the_grid_stops_at_the_budget(self):
        frame = _price_frame(n=120)
        opt = self._opt(frame, _policy(5))
        result, calls = _scored(opt, "optimize", (5, 10, 15), (0.5, 1.0))
        assert result.grid_size == 6
        assert result.distinct_cells == 5
        assert result.search == "TPE sample"
        assert len(calls) == 5
        assert len(set(zip(result.grid_df["window"], result.grid_df["signal"]))) == 5

    def test_same_seed_same_cells(self):
        frame = _price_frame()
        policy = _policy(8)

        def once():
            result, _ = _scored(
                self._opt(frame.copy(), policy), "optimize", self.WINDOWS, self.SIGNALS,
            )
            return result

        def keys(result):
            return sorted(zip(result.grid_df["window"], result.grid_df["signal"]))

        first, second = once(), once()
        assert keys(first) == keys(second)
        assert first.best == second.best

    def test_multi_factor_keys_are_the_full_cell(self, multi_factor_df):
        config = _multi_factor_config()
        space = SearchSpace.multi(
            [(5, 10, 15, 20, 25), (5, 10, 15, 20, 25)],
            [(0.5, 1.0, 1.5), (0.5, 1.0, 1.5)],
        )
        left = space.cell_key({
            "window_0": 5, "signal_0": 0.5, "window_1": 10, "signal_1": 1.0,
        })
        right = space.cell_key({
            "window_0": 10, "signal_0": 0.5, "window_1": 5, "signal_1": 1.0,
        })
        assert left != right
        opt = ParametersOptimization(
            {config.internal_cusip: multi_factor_df.copy()},
            config,
            search=_policy(12, factor=5),
        )
        result, calls = _scored(
            opt, "optimize_multi",
            [(5, 10, 15, 20, 25), (5, 10, 15, 20, 25)],
            [(0.5, 1.0, 1.5), (0.5, 1.0, 1.5)],
        )
        keys = list(zip(
            result.grid_df["window_0"], result.grid_df["signal_0"],
            result.grid_df["window_1"], result.grid_df["signal_1"],
        ))
        assert result.grid_size == 225
        assert result.distinct_cells == 12
        assert len(set(keys)) == 12
        assert len(calls) == 12

    def test_random_sample_is_distinct_and_repeatable(self):
        frame = _price_frame(n=120)
        policy = _policy(5, RANDOM_DISTINCT, seed=7)
        result, calls = _scored(self._opt(frame, policy), "optimize", self.WINDOWS, self.SIGNALS)
        again, _ = _scored(self._opt(frame.copy(), policy), "optimize", self.WINDOWS, self.SIGNALS)
        keys = sorted(zip(result.grid_df["window"], result.grid_df["signal"]))
        assert result.search == "random sample"
        assert result.distinct_cells == 5
        assert len(set(keys)) == 5
        assert len(calls) == 5
        assert keys == sorted(zip(again.grid_df["window"], again.grid_df["signal"]))

    def test_reject_mode_does_not_score(self):
        frame = _price_frame(n=120)
        opt = self._opt(frame, _policy(5, REJECT))
        with (
            patch.object(SearchStrategy, "evaluate", side_effect=AssertionError("scored")),
            pytest.raises(OverBudgetGrid, match="25 cells exceeds the trial budget of 5"),
        ):
            opt.optimize(self.WINDOWS, self.SIGNALS)

    def test_reject_mode_under_budget_is_exhaustive(self):
        frame = _price_frame(n=120)
        opt = self._opt(frame, _policy(100, REJECT))
        result, calls = _scored(opt, "optimize", (5, 10), (0.5,))
        assert result.search == "exhaustive"
        assert result.distinct_cells == 2
        assert len(calls) == 2

    def test_flat_index_matches_the_product(self):
        space = SearchSpace.single((5, 10, 15), (0.5, 1.0))
        expected = list(itertools.product((5, 10, 15), (0.5, 1.0)))
        assert [space.combo_at(i) for i in range(space.total)] == expected

    def test_walk_forward_in_sample_uses_the_same_loop(self):
        from quant.strategy.walk_forward import WalkForward

        frame = _price_frame(n=200)
        wf = WalkForward(
            {_BOLLINGER_CONFIG.internal_cusip: frame},
            0.5,
            _BOLLINGER_CONFIG,
            search=_policy(4),
        )
        calls = []
        real = SearchStrategy.evaluate

        def wrapped(self, objective, windows, signals):
            calls.append(1)
            return real(self, objective, windows, signals)

        with patch.object(SearchStrategy, "evaluate", wrapped):
            wf.run((5, 10, 15), (0.5, 1.0, 1.5))
        assert len(calls) == 4

    def test_reject_is_a_422_at_the_service_boundary(self):
        from quant.strategy.backtest_service import BacktestError, _run_search

        opt = MagicMock()
        opt.run.side_effect = OverBudgetGrid(25, 20)
        with pytest.raises(BacktestError, match="25 cells exceeds the trial budget of 20") as caught:
            _run_search(opt, (), ())
        assert caught.value.status_code == 422
