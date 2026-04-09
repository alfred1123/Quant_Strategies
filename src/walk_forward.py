"""
Walk-forward overfitting test.

Splits historical data into in-sample (training) and out-of-sample (validation)
periods. Optimizes parameters on in-sample via grid search, then evaluates the
best parameters on out-of-sample to detect overfitting.

Usage:
    from strat import SignalDirection, StrategyConfig, SubStrategy
    # Single-factor
    config = StrategyConfig("BTC-USD", "get_bollinger_band",
                            SignalDirection.momentum_const_signal, 365)
    wf = WalkForward(data, 0.5, config)
    result = wf.run(window_tuple, signal_tuple)

    # Multi-factor — run() auto-detects from config
    sub1 = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0, "v")
    sub2 = SubStrategy("get_rsi", "reversion_const_signal", 14, 0.5, "volume")
    config = StrategyConfig("BTC-USD", "get_sma",
                            SignalDirection.momentum_const_signal, 365,
                            conjunction="AND", substrategies=(sub1, sub2))
    wf = WalkForward(data, 0.5, config)
    result = wf.run(window_ranges, signal_ranges)
"""

import logging

import numpy as np
import pandas as pd

from param_opt import ParametersOptimization
from perf import Performance

logger = logging.getLogger(__name__)


class WalkForwardResult:
    """Container for walk-forward test results."""

    def __init__(self, best_window, best_signal,
                 is_metrics, oos_metrics, overfitting_ratio,
                 full_equity_df=None):
        self.best_window = best_window
        self.best_signal = best_signal
        self.is_metrics = is_metrics    # pd.Series
        self.oos_metrics = oos_metrics  # pd.Series
        self.overfitting_ratio = overfitting_ratio
        self.full_equity_df = full_equity_df  # pd.DataFrame, full-period enriched data

    def summary(self):
        """Return a DataFrame comparing in-sample vs out-of-sample."""
        df = pd.DataFrame({
            'In-Sample': self.is_metrics,
            'Out-of-Sample': self.oos_metrics,
        })
        df.loc['Overfitting Ratio'] = [np.nan, self.overfitting_ratio]
        return df


class WalkForward:
    """Walk-forward overfitting test for the backtest pipeline."""

    def __init__(self, data, split_ratio, config, *, fee_bps=None):
        """
        Args:
            data: DataFrame with 'price' and 'factor' columns.
            split_ratio: Fraction of data used for in-sample (0.0–1.0).
            config: StrategyConfig with indicator_name, signal_func, trading_period.
            fee_bps: Transaction fee in basis points.
        """
        if not 0.0 < split_ratio < 1.0:
            raise ValueError(f"split_ratio must be between 0 and 1, got {split_ratio}")

        self.data = data
        self.split_ratio = split_ratio
        self.config = config
        self.fee_bps = fee_bps

        self.split_idx = int(len(data) * split_ratio)
        if self.split_idx < 2 or self.split_idx >= len(data) - 1:
            raise ValueError(
                f"Split produces empty partition: split_idx={self.split_idx}, "
                f"data length={len(data)}"
            )

        logger.info("Walk-forward split: %d in-sample, %d out-of-sample (ratio=%.2f)",
                     self.split_idx, len(data) - self.split_idx, split_ratio)

    def run(self, window_values, signal_values):
        """Run walk-forward test — auto-detects single vs multi-factor from config.

        Args:
            window_values: Single-factor: tuple of window candidates.
                           Multi-factor: list of tuples, one per substrategy.
            signal_values: Single-factor: tuple of signal candidates.
                           Multi-factor: list of tuples, one per substrategy.

        Returns:
            WalkForwardResult with in-sample/out-of-sample metrics.
            Multi-factor: ``best_window`` and ``best_signal`` are tuples.
        """
        subs = self.config.get_substrategies()
        if len(subs) > 1:
            return self._run_multi(window_values, signal_values)
        return self._run_single(window_values, signal_values)

    def _run_single(self, window_tuple, signal_tuple):
        """Walk-forward for a single-factor config."""
        # ── Split data ──────────────────────────────────────────────
        is_data = self.data.iloc[:self.split_idx].copy().reset_index(drop=True)
        oos_data = self.data.iloc[self.split_idx:].copy().reset_index(drop=True)

        # ── In-sample: grid search ──────────────────────────────────
        is_opt = ParametersOptimization(
            is_data, self.config, fee_bps=self.fee_bps,
        )

        opt_result = is_opt.optimize(window_tuple, signal_tuple)
        best_window = int(opt_result.best['window'])
        best_signal = float(opt_result.best['signal'])

        logger.info("In-sample best: window=%d, signal=%.2f, Sharpe=%.4f",
                     best_window, best_signal, opt_result.best['sharpe'])

        # ── In-sample: full performance with best params ────────────
        is_data_perf = self.data.iloc[:self.split_idx].copy().reset_index(drop=True)
        is_perf = Performance(
            is_data_perf, self.config, best_window, best_signal,
            fee_bps=self.fee_bps,
        )
        is_perf.enrich_performance()
        is_metrics = is_perf.get_strategy_performance()

        # ── Out-of-sample: evaluate with same params ────────────────
        oos_perf = Performance(
            oos_data, self.config, best_window, best_signal,
            fee_bps=self.fee_bps,
        )
        oos_perf.enrich_performance()
        oos_metrics = oos_perf.get_strategy_performance()

        # ── Overfitting ratio ───────────────────────────────────────
        overfitting_ratio = self._overfitting_ratio(is_metrics, oos_metrics)

        logger.info("Out-of-sample Sharpe=%.4f, Overfitting ratio=%.4f",
                     oos_metrics['Sharpe Ratio'], overfitting_ratio)

        # ── Full-period equity curve ────────────────────────────────
        full_perf = Performance(
            self.data.copy(), self.config, best_window, best_signal,
            fee_bps=self.fee_bps,
        )
        full_perf.enrich_performance()

        return WalkForwardResult(
            best_window=best_window,
            best_signal=best_signal,
            is_metrics=is_metrics,
            oos_metrics=oos_metrics,
            overfitting_ratio=overfitting_ratio,
            full_equity_df=full_perf.data,
        )

    def _run_multi(self, window_ranges, signal_ranges):
        """Walk-forward for a multi-factor config."""
        is_data = self.data.iloc[:self.split_idx].copy().reset_index(drop=True)
        oos_data = self.data.iloc[self.split_idx:].copy().reset_index(drop=True)

        is_opt = ParametersOptimization(
            is_data, self.config, fee_bps=self.fee_bps,
        )

        opt_result = is_opt.optimize_multi(window_ranges, signal_ranges)

        n_factors = len(window_ranges)
        best_windows = tuple(int(opt_result.best[f'window_{i}']) for i in range(n_factors))
        best_signals = tuple(float(opt_result.best[f'signal_{i}']) for i in range(n_factors))

        logger.info("In-sample best: windows=%s, signals=%s, Sharpe=%.4f",
                     best_windows, best_signals, opt_result.best['sharpe'])

        is_data_perf = self.data.iloc[:self.split_idx].copy().reset_index(drop=True)
        is_perf = Performance(
            is_data_perf, self.config, best_windows, best_signals,
            fee_bps=self.fee_bps,
        )
        is_perf.enrich_performance()
        is_metrics = is_perf.get_strategy_performance()

        oos_perf = Performance(
            oos_data, self.config, best_windows, best_signals,
            fee_bps=self.fee_bps,
        )
        oos_perf.enrich_performance()
        oos_metrics = oos_perf.get_strategy_performance()

        overfitting_ratio = self._overfitting_ratio(is_metrics, oos_metrics)

        logger.info("Out-of-sample Sharpe=%.4f, Overfitting ratio=%.4f",
                     oos_metrics['Sharpe Ratio'], overfitting_ratio)

        # ── Full-period equity curve ────────────────────────────────
        full_perf = Performance(
            self.data.copy(), self.config, best_windows, best_signals,
            fee_bps=self.fee_bps,
        )
        full_perf.enrich_performance()

        return WalkForwardResult(
            best_window=best_windows,
            best_signal=best_signals,
            is_metrics=is_metrics,
            oos_metrics=oos_metrics,
            overfitting_ratio=overfitting_ratio,
            full_equity_df=full_perf.data,
        )

    @staticmethod
    def _overfitting_ratio(is_metrics, oos_metrics):
        is_sharpe = is_metrics['Sharpe Ratio']
        oos_sharpe = oos_metrics['Sharpe Ratio']
        if np.isnan(is_sharpe) or is_sharpe == 0:
            return np.nan
        return 1 - (oos_sharpe / is_sharpe)
