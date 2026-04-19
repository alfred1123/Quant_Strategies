"""
Walk-forward overfitting test.

Splits historical data into in-sample (training) and out-of-sample (validation)
periods. Optimizes parameters on in-sample via grid search, then evaluates the
best parameters on out-of-sample to detect overfitting.

Usage:
    from strat import SignalDirection, StrategyConfig, SubStrategy
    # Single-factor
    config = StrategyConfig("BTC-USD", "get_bollinger_band",
                            SignalDirection.momentum_band_signal, 365)
    wf = WalkForward(data, 0.5, config)
    result = wf.run(window_tuple, signal_tuple)

    # Multi-factor — run() auto-detects from config
    sub1 = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0, "v")
    sub2 = SubStrategy("get_rsi", "reversion_band_signal", 14, 0.5, "volume")
    config = StrategyConfig("BTC-USD", "get_sma",
                            SignalDirection.momentum_band_signal, 365,
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
            data: dict[str, DataFrame] keyed by internal_cusip.
            split_ratio: Fraction of data used for in-sample (0.0–1.0).
            config: StrategyConfig with indicator_name, signal_func, trading_period.
            fee_bps: Transaction fee in basis points.
        """
        if not 0.0 < split_ratio < 1.0:
            raise ValueError(f"split_ratio must be between 0 and 1, got {split_ratio}")

        self.all_data = data
        self.data = data[config.internal_cusip]

        self.split_ratio = split_ratio
        self.config = config
        self.fee_bps = fee_bps

        self.split_idx = int(len(self.data) * split_ratio)
        if self.split_idx < 2 or self.split_idx >= len(self.data) - 1:
            raise ValueError(
                f"Split produces empty partition: split_idx={self.split_idx}, "
                f"data length={len(self.data)}"
            )

        logger.info("Walk-forward split: %d in-sample, %d out-of-sample (ratio=%.2f)",
                     self.split_idx, len(self.data) - self.split_idx, split_ratio)

    def run(self, window_values, signal_values):
        """Run walk-forward test.

        Auto-dispatches to single vs multi-factor via ParametersOptimization.run().

        Args:
            window_values: Single-factor: tuple of window candidates.
                           Multi-factor: list of tuples, one per substrategy.
            signal_values: Single-factor: tuple of signal candidates.
                           Multi-factor: list of tuples, one per substrategy.

        Returns:
            WalkForwardResult with in-sample/out-of-sample metrics.
            Multi-factor: ``best_window`` and ``best_signal`` are tuples.
        """
        is_data_dict = {
            t: df.iloc[:self.split_idx].copy()
            for t, df in self.all_data.items()
        }
        oos_data_dict = {
            t: df.iloc[self.split_idx:].copy()
            for t, df in self.all_data.items()
        }

        # ── In-sample: optimize on training split ───────────────────
        opt_result = ParametersOptimization(
            is_data_dict, self.config, fee_bps=self.fee_bps,
        ).run(window_values, signal_values)

        best_window, best_signal = self._extract_best(opt_result.best)

        logger.info("In-sample best: window=%s, signal=%s, Sharpe=%.4f",
                    best_window, best_signal, opt_result.best['sharpe'])

        # ── Evaluate IS and OOS with best params ────────────────────
        is_metrics = self._evaluate(is_data_dict, best_window, best_signal)
        oos_metrics = self._evaluate(oos_data_dict, best_window, best_signal)
        overfitting_ratio = self._overfitting_ratio(is_metrics, oos_metrics)

        logger.info("Out-of-sample Sharpe=%.4f, Overfitting ratio=%.4f",
                    oos_metrics['Sharpe Ratio'], overfitting_ratio)

        # ── Full-period equity curve ─────────────────────────────────
        full_perf = Performance(
            self.all_data, self.config, best_window, best_signal,
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

    def _evaluate(self, data, best_window, best_signal):
        """Run Performance on a data slice with fixed params and return metrics."""
        perf = Performance(
            data, self.config, best_window, best_signal, fee_bps=self.fee_bps,
        )
        perf.enrich_performance()
        return perf.get_strategy_performance()

    @staticmethod
    def _extract_best(best: dict):
        """Extract (best_window, best_signal) from an OptimizeResult.best dict.

        Single-factor dicts have keys 'window'/'signal'.
        Multi-factor dicts have keys 'window_0', 'signal_0', 'window_1', ...
        """
        if 'window' in best:
            return int(best['window']), float(best['signal'])
        n = sum(1 for k in best if k.startswith('window_'))
        return (
            tuple(int(best[f'window_{i}']) for i in range(n)),
            tuple(float(best[f'signal_{i}']) for i in range(n)),
        )

    def _run_single(self, window_tuple, signal_tuple):
        return self.run(window_tuple, signal_tuple)

    def _run_multi(self, window_ranges, signal_ranges):
        return self.run(window_ranges, signal_ranges)

    @staticmethod
    def _overfitting_ratio(is_metrics, oos_metrics):
        is_sharpe = is_metrics['Sharpe Ratio']
        oos_sharpe = oos_metrics['Sharpe Ratio']
        if np.isnan(is_sharpe) or is_sharpe == 0:
            return np.nan
        return 1 - (oos_sharpe / is_sharpe)
