"""Numerical equivalence: Objective vs Performance, plus IndicatorCache."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from quant.strategy.indicators import TechnicalAnalysis
from quant.strategy.objective import (
    IndicatorCache,
    MultiFactorObjective,
    Objective,
    SingleFactorObjective,
)
from quant.strategy.optimizer import ParametersOptimization
from quant.strategy.performance import Performance
from quant.strategy.signals import SignalDirection, StrategyConfig, SubStrategy


_INDICATORS = (
    "get_sma",
    "get_ema",
    "get_rsi",
    "get_bollinger_band",
    "get_stochastic_oscillator",
)
_SIGNALS = (
    SignalDirection.momentum_band_signal,
    SignalDirection.reversion_band_signal,
    SignalDirection.momentum_bounded_signal,
    SignalDirection.reversion_bounded_signal,
)
_BOUNDED = {
    SignalDirection.momentum_bounded_signal,
    SignalDirection.reversion_bounded_signal,
}


def _assert_sharpe_equal(left, right):
    if np.isnan(left) and np.isnan(right):
        return
    assert left == pytest.approx(right, abs=1e-12)


def _perf_sharpe(data, config, window, signal, fee_bps=None):
    perf = Performance(data, config, window, signal, fee_bps=fee_bps)
    perf.enrich_performance()
    return perf.get_sharpe_ratio()


class TestIndicatorCache:
    def test_arrays_aligned_to_frame(self, sample_ohlc_df):
        cache = IndicatorCache(sample_ohlc_df, "get_rsi", (5, 10))
        assert cache[5].shape == (len(sample_ohlc_df),)
        assert cache[10].shape == (len(sample_ohlc_df),)
        assert 5 in cache and 10 in cache

    def test_window_computed_once(self, sample_ohlc_df):
        real = TechnicalAnalysis.get_sma
        calls = {"n": 0}

        def spy(self, period):
            calls["n"] += 1
            return real(self, period)

        with patch.object(TechnicalAnalysis, "get_sma", spy):
            cache = IndicatorCache(sample_ohlc_df, "get_sma", (5, 10))
            cache[5]
            cache[5]
            cache[10]
        assert calls["n"] == 2


class TestObjectiveEquivalence:
    def test_indicator_x_signal_random_pairs(self, sample_ohlc_df):
        rng = np.random.default_rng(0)
        data = {"test": sample_ohlc_df}
        windows = np.array([5, 8, 10, 12, 15])
        band = np.array([0.5, 1.0, 1.5, 2.0])
        bounded = np.array([60.0, 70.0, 80.0])
        for indicator in _INDICATORS:
            for signal_func in _SIGNALS:
                config = StrategyConfig(
                    "test", indicator, signal_func, 252,
                )
                sigs = bounded if signal_func in _BOUNDED else band
                pairs = [
                    (int(rng.choice(windows)), float(rng.choice(sigs)))
                    for _ in range(10)
                ]
                unique_w = sorted({w for w, _ in pairs})
                obj = SingleFactorObjective(data, config, unique_w)
                for window, signal in pairs:
                    expected = _perf_sharpe(data, config, window, signal)
                    got = obj((window,), (signal,))
                    _assert_sharpe_equal(got, expected)

    def test_multi_factor_conjunctions(self, multi_factor_df):
        data = {"test": multi_factor_df}
        ranges = [(5, 10), (8, 12)]
        for conjunction in ("AND", "OR", "FILTER"):
            sub_a = SubStrategy("get_sma", "momentum_band_signal", 5, 0.5, "v")
            sub_b = SubStrategy("get_rsi", "momentum_bounded_signal", 10, 70, "volume")
            config = StrategyConfig(
                "test", "get_sma", SignalDirection.momentum_band_signal, 252,
                conjunction=conjunction, substrategies=(sub_a, sub_b),
            )
            obj = MultiFactorObjective(data, config, ranges)
            for windows, signals in (
                ((5, 8), (0.5, 70.0)),
                ((10, 12), (1.0, 80.0)),
            ):
                expected = _perf_sharpe(data, config, windows, signals)
                got = obj(windows, signals)
                _assert_sharpe_equal(got, expected)

    def test_cross_product_factor(self):
        np.random.seed(42)
        n = 300
        idx = pd.date_range("2020-01-01", periods=n, freq="D", name="datetime")
        btc = 100 + np.cumsum(np.random.randn(n) * 0.5)
        eth = 50 + np.cumsum(np.random.randn(n) * 0.3)
        data = {
            "btc-usd": pd.DataFrame({
                "price": btc, "factor": btc, "v": btc,
                "Close": btc, "High": btc + 0.3, "Low": btc - 0.3,
            }, index=idx),
            "eth-usd": pd.DataFrame({
                "price": eth, "factor": eth, "v": eth,
                "Close": eth, "High": eth + 0.3, "Low": eth - 0.3,
            }, index=idx),
        }
        sub = SubStrategy(
            "get_sma", "momentum_band_signal", 10, 0.5, "v",
            internal_cusip="eth-usd",
        )
        config = StrategyConfig(
            "btc-usd", "get_sma", SignalDirection.momentum_band_signal, 365,
            substrategies=(sub,),
        )
        obj = SingleFactorObjective(data, config, (10, 20))
        for window, signal in ((10, 0.5), (20, 1.0)):
            expected = _perf_sharpe(data, config, window, signal)
            _assert_sharpe_equal(obj((window,), (signal,)), expected)

    def test_flat_series_is_nan(self):
        n = 120
        idx = pd.date_range("2020-01-01", periods=n, freq="D")
        prices = np.full(n, 100.0)
        df = pd.DataFrame({
            "price": prices, "factor": prices,
            "Close": prices, "High": prices, "Low": prices,
        }, index=idx)
        config = StrategyConfig(
            "test", "get_sma", SignalDirection.momentum_band_signal, 252,
        )
        data = {"test": df}
        obj = SingleFactorObjective(data, config, (5,))
        expected = _perf_sharpe(data, config, 5, 1.0)
        _assert_sharpe_equal(obj((5,), (1.0,)), expected)
        assert np.isnan(expected)

    def test_window_at_least_row_count_is_nan(self, sample_ohlc_df):
        config = StrategyConfig(
            "test", "get_sma", SignalDirection.momentum_band_signal, 252,
        )
        data = {"test": sample_ohlc_df}
        n = len(sample_ohlc_df)
        obj = SingleFactorObjective(data, config, (n,))
        expected = _perf_sharpe(data, config, n, 1.0)
        _assert_sharpe_equal(obj((n,), (1.0,)), expected)
        assert np.isnan(expected)

    def test_fee_bps_matches_performance(self, sample_ohlc_df):
        config = StrategyConfig(
            "test", "get_bollinger_band",
            SignalDirection.momentum_band_signal, 252,
        )
        data = {"test": sample_ohlc_df}
        obj = SingleFactorObjective(data, config, (5,), fee_bps=20.0)
        expected = _perf_sharpe(data, config, 5, 1.0, fee_bps=20.0)
        _assert_sharpe_equal(obj((5,), (1.0,)), expected)

    def test_for_config_picks_subclass(self, sample_ohlc_df, multi_factor_df):
        single = StrategyConfig(
            "test", "get_sma", SignalDirection.momentum_band_signal, 252,
        )
        assert isinstance(
            Objective.for_config({"test": sample_ohlc_df}, single, (5, 10)),
            SingleFactorObjective,
        )
        sub_a = SubStrategy("get_sma", "momentum_band_signal", 5, 0.5, "v")
        sub_b = SubStrategy("get_sma", "momentum_band_signal", 10, 0.5, "volume")
        multi = StrategyConfig(
            "test", "get_sma", SignalDirection.momentum_band_signal, 252,
            substrategies=(sub_a, sub_b),
        )
        assert isinstance(
            Objective.for_config(
                {"test": multi_factor_df}, multi, [(5,), (10,)],
            ),
            MultiFactorObjective,
        )


def _long_ohlc(n=400, seed=0):
    """Enough bars that a 50/50 walk-forward split still clears MIN_METRIC_OBS."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    idx = pd.date_range("2016-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({
        "price": close, "factor": close, "v": close,
        "volume": 1000 + np.cumsum(rng.normal(0, 20, n)),
        "Close": close,
        "High": close + np.abs(rng.normal(0, 0.3, n)),
        "Low": close - np.abs(rng.normal(0, 0.3, n)),
        "Open": close + rng.normal(0, 0.1, n),
    }, index=idx)


def _signals_for(func):
    return (70.0, 80.0) if func in _BOUNDED else (0.5, 1.5)


class TestOptimizeGridMatchesPerformance:
    """Every user-facing search path must report Performance's Sharpe."""

    @pytest.mark.parametrize("indicator", _INDICATORS)
    @pytest.mark.parametrize("signal_func", _SIGNALS)
    @pytest.mark.parametrize("trading_period", (252, 365))
    def test_exhaustive_optimize_grid(self, indicator, signal_func, trading_period):
        df = _long_ohlc()
        data = {"test": df}
        config = StrategyConfig("test", indicator, signal_func, trading_period)
        windows = (5, 10, 20)
        signals = _signals_for(signal_func)
        result = ParametersOptimization(data, config, fee_bps=5.0).optimize(
            windows, signals,
        )
        assert len(result.grid_df) == len(windows) * len(signals)
        for row in result.grid_df.itertuples(index=False):
            expected = _perf_sharpe(
                data, config, int(row.window), float(row.signal), fee_bps=5.0,
            )
            _assert_sharpe_equal(row.sharpe, expected)

    def test_bayesian_sampled_cells(self):
        df = _long_ohlc()
        data = {"test": df}
        config = StrategyConfig(
            "test", "get_bollinger_band",
            SignalDirection.momentum_band_signal, 365,
        )
        windows = (5, 8, 10, 12, 15)
        signals = (0.5, 1.0, 1.5)
        result = ParametersOptimization(data, config).optimize(
            windows, signals, n_trials=4,
        )
        assert len(result.grid_df) == 4
        for row in result.grid_df.itertuples(index=False):
            expected = _perf_sharpe(
                data, config, int(row.window), float(row.signal),
            )
            _assert_sharpe_equal(row.sharpe, expected)

    @pytest.mark.parametrize("conjunction", ("AND", "OR", "FILTER"))
    def test_exhaustive_optimize_multi(self, conjunction):
        df = _long_ohlc()
        data = {"test": df}
        sub_a = SubStrategy("get_sma", "momentum_band_signal", 5, 0.5, "v")
        sub_b = SubStrategy("get_rsi", "momentum_bounded_signal", 10, 70, "volume")
        config = StrategyConfig(
            "test", "get_sma", SignalDirection.momentum_band_signal, 365,
            conjunction=conjunction, substrategies=(sub_a, sub_b),
        )
        window_ranges = [(5, 10), (8, 14)]
        signal_ranges = [(0.5, 1.5), (70.0, 80.0)]
        result = ParametersOptimization(data, config).optimize_multi(
            window_ranges, signal_ranges,
        )
        assert len(result.grid_df) == 16
        for row in result.grid_df.itertuples(index=False):
            windows = (int(row.window_0), int(row.window_1))
            signals = (float(row.signal_0), float(row.signal_1))
            expected = _perf_sharpe(data, config, windows, signals)
            _assert_sharpe_equal(row.sharpe, expected)

    def test_run_dispatches_match_performance(self):
        df = _long_ohlc()
        data = {"test": df}
        single = StrategyConfig(
            "test", "get_ema", SignalDirection.reversion_band_signal, 252,
        )
        single_res = ParametersOptimization(data, single).run((5, 15), (0.5, 1.5))
        for row in single_res.grid_df.itertuples(index=False):
            _assert_sharpe_equal(
                row.sharpe,
                _perf_sharpe(data, single, int(row.window), float(row.signal)),
            )

        sub_a = SubStrategy("get_bollinger_band", "momentum_band_signal", 5, 0.5, "v")
        sub_b = SubStrategy("get_sma", "momentum_band_signal", 10, 0.5, "volume")
        multi = StrategyConfig(
            "test", "get_bollinger_band",
            SignalDirection.momentum_band_signal, 365,
            conjunction="AND", substrategies=(sub_a, sub_b),
        )
        multi_res = ParametersOptimization(data, multi).run([(5,), (10,)], [(1.0,), (0.5,)])
        row = multi_res.grid_df.iloc[0]
        _assert_sharpe_equal(
            row["sharpe"],
            _perf_sharpe(data, multi, (5, 10), (1.0, 0.5)),
        )


class TestWalkForwardOptimizeMatchesPerformance:
    """Walk-forward IS search uses Objective; its best Sharpe must match Performance."""

    def test_single_factor_is_best(self):
        from quant.strategy.walk_forward import WalkForward

        df = _long_ohlc(500)
        data = {"test": df}
        config = StrategyConfig(
            "test", "get_bollinger_band",
            SignalDirection.momentum_band_signal, 365,
        )
        windows, signals = (5, 10, 20), (0.5, 1.5)
        wf = WalkForward(data, 0.5, config, fee_bps=5.0)
        result = wf.run(windows, signals)

        is_data = {t: frame.iloc[:wf.split_idx].copy() for t, frame in data.items()}
        expected_best = _perf_sharpe(
            is_data, config, result.best_window, result.best_signal, fee_bps=5.0,
        )
        _assert_sharpe_equal(result.is_metrics["Sharpe Ratio"], expected_best)

        oos_data = {t: frame.iloc[wf.split_idx:].copy() for t, frame in data.items()}
        _assert_sharpe_equal(
            result.oos_metrics["Sharpe Ratio"],
            _perf_sharpe(
                oos_data, config, result.best_window, result.best_signal, fee_bps=5.0,
            ),
        )

    @pytest.mark.parametrize("conjunction", ("AND", "OR", "FILTER"))
    def test_multi_factor_is_best(self, conjunction):
        from quant.strategy.walk_forward import WalkForward

        df = _long_ohlc(500)
        data = {"test": df}
        sub_a = SubStrategy("get_sma", "momentum_band_signal", 5, 0.5, "v")
        sub_b = SubStrategy("get_rsi", "reversion_bounded_signal", 10, 70, "volume")
        config = StrategyConfig(
            "test", "get_sma", SignalDirection.momentum_band_signal, 365,
            conjunction=conjunction, substrategies=(sub_a, sub_b),
        )
        wf = WalkForward(data, 0.5, config)
        result = wf.run([(5, 12), (8, 14)], [(0.5, 1.5), (70.0, 80.0)])
        is_data = {t: frame.iloc[:wf.split_idx].copy() for t, frame in data.items()}
        _assert_sharpe_equal(
            result.is_metrics["Sharpe Ratio"],
            _perf_sharpe(is_data, config, result.best_window, result.best_signal),
        )


class TestCoverageFailFast:
    def test_sparse_factor_raises_from_optimize(self):
        n = 100
        idx = pd.date_range("2020-01-01", periods=n, freq="D")
        prices = 100 + np.arange(n, dtype=float)
        main = pd.DataFrame({
            "price": prices, "factor": prices, "v": prices,
            "Close": prices, "High": prices + 1, "Low": prices - 1,
        }, index=idx)
        factor = main.iloc[:50].copy()
        sub = SubStrategy(
            "get_sma", "momentum_band_signal", 5, 0.5, "v",
            internal_cusip="factor",
        )
        config = StrategyConfig(
            "main", "get_sma", SignalDirection.momentum_band_signal, 252,
            substrategies=(sub,),
        )
        data = {"main": main, "factor": factor}
        with pytest.raises(ValueError, match="covers only"):
            ParametersOptimization(data, config).optimize((5,), (0.5,))
