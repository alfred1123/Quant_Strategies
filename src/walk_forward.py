"""
Walk-forward overfitting test.

Splits historical data into in-sample (training) and out-of-sample (validation)
periods. Optimizes parameters on in-sample via grid search, then evaluates the
best parameters on out-of-sample to detect overfitting.

Usage (single-factor):
    from strat import StrategyConfig, FactorConfig, Strategy
    config = StrategyConfig(
        factors=(FactorConfig('price', 'get_bollinger_band'),),
        strategy_func=Strategy.momentum_const_signal,
        trading_period=365,
    )
    wf = WalkForward(data, 0.5, config)
    result = wf.run(window_tuple, signal_tuple)

Usage (multi-factor):
    config = StrategyConfig(
        factors=(
            FactorConfig('price', 'get_bollinger_band'),
            FactorConfig('volume', 'get_bollinger_band'),
        ),
        strategy_func=Strategy.momentum_const_signal,
        trading_period=365,
        conjunction='AND',
    )
    wf = WalkForward(data, 0.5, config)
    result = wf.run(
        param_grid={'window_0': (10, 20), 'signal_0': (0.5, 1.0),
                    'window_1': (15, 30), 'signal_1': (0.25, 0.75)}
    )
"""

import logging

import numpy as np
import pandas as pd

from param_opt import ParametersOptimization
from perf import Performance

logger = logging.getLogger(__name__)


class WalkForwardResult:
    """Container for walk-forward test results."""

    def __init__(self, best_windows, best_signals,
                 is_metrics, oos_metrics, overfitting_ratio):
        self.best_windows = best_windows    # tuple
        self.best_signals = best_signals    # tuple
        # Backward compat: single-factor exposes scalars
        self.best_window = best_windows[0] if len(best_windows) == 1 else best_windows
        self.best_signal = best_signals[0] if len(best_signals) == 1 else best_signals
        self.is_metrics = is_metrics    # pd.Series
        self.oos_metrics = oos_metrics  # pd.Series
        self.overfitting_ratio = overfitting_ratio

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

    def run(self, window_tuple=None, signal_tuple=None, *, param_grid=None):
        """Run walk-forward test.

        Args:
            window_tuple: Tuple of window values (single-factor legacy API).
            signal_tuple: Tuple of signal values (single-factor legacy API).
            param_grid: Dict with indexed keys for multi-factor
                        (e.g. {'window_0': (...), 'signal_0': (...), ...}).
                        If provided, window_tuple/signal_tuple are ignored.

        Returns:
            WalkForwardResult with in-sample/out-of-sample metrics.
        """
        num_factors = len(self.config.factors)

        # Build param_grid from legacy args if not provided
        if param_grid is None:
            if window_tuple is None or signal_tuple is None:
                raise ValueError(
                    "Either param_grid or (window_tuple, signal_tuple) must be provided"
                )
            param_grid = {
                'window': window_tuple,
                'signal': signal_tuple,
            }

        # ── Split data ──────────────────────────────────────────────
        is_data = self.data.iloc[:self.split_idx].copy().reset_index(drop=True)
        oos_data = self.data.iloc[self.split_idx:].copy().reset_index(drop=True)

        # ── In-sample: grid search ──────────────────────────────────
        is_opt = ParametersOptimization(
            is_data, self.config, fee_bps=self.fee_bps,
        )

        grid_results = pd.DataFrame(is_opt.optimize_grid(param_grid))

        best = grid_results.loc[grid_results['sharpe'].idxmax()]

        # Extract best windows/signals
        if 'window' in best and 'signal' in best:
            best_windows = (int(best['window']),)
            best_signals = (float(best['signal']),)
        else:
            best_windows = tuple(int(best[f'window_{i}']) for i in range(num_factors))
            best_signals = tuple(float(best[f'signal_{i}']) for i in range(num_factors))

        logger.info("In-sample best: windows=%s, signals=%s, Sharpe=%.4f",
                     best_windows, best_signals, best['sharpe'])

        # ── In-sample: full performance with best params ────────────
        is_data_perf = self.data.iloc[:self.split_idx].copy().reset_index(drop=True)
        is_perf = Performance(
            is_data_perf, self.config, best_windows, best_signals,
            fee_bps=self.fee_bps,
        )
        is_metrics = is_perf.get_strategy_performance()

        # ── Out-of-sample: evaluate with same params ────────────────
        oos_perf = Performance(
            oos_data, self.config, best_windows, best_signals,
            fee_bps=self.fee_bps,
        )
        oos_metrics = oos_perf.get_strategy_performance()

        # ── Overfitting ratio ───────────────────────────────────────
        is_sharpe = is_metrics['Sharpe Ratio']
        oos_sharpe = oos_metrics['Sharpe Ratio']

        if np.isnan(is_sharpe) or is_sharpe == 0:
            overfitting_ratio = np.nan
        else:
            overfitting_ratio = 1 - (oos_sharpe / is_sharpe)

        logger.info("Out-of-sample Sharpe=%.4f, Overfitting ratio=%.4f",
                     oos_sharpe, overfitting_ratio)

        return WalkForwardResult(
            best_windows=best_windows,
            best_signals=best_signals,
            is_metrics=is_metrics,
            oos_metrics=oos_metrics,
            overfitting_ratio=overfitting_ratio,
        )
