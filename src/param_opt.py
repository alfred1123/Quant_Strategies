'''
N-dimensional parameter grid search for the backtest pipeline.

Sweeps over arbitrary combinations of window, signal, factor, indicator,
and strategy — yielding Sharpe ratios for each combination.

Multi-factor support:
    For a 2-factor config, use indexed keys in param_grid:
        {'window_0': (10, 20), 'signal_0': (0.5, 1.0),
         'window_1': (15, 30), 'signal_1': (0.25, 0.75)}
    These are packed into tuples for Performance:
        windows=(w0, w1), signals=(s0, s1)

    Single-factor (backward-compatible):
        {'window': (10, 20), 'signal': (0.5, 1.0)}
    Treated as: {'window_0': ..., 'signal_0': ...}
'''

import itertools
import logging
import re

import pandas as pd
import numpy as np

from perf import Performance
from strat import StrategyConfig

logger = logging.getLogger(__name__)


def _parse_indexed_params(params, num_factors):
    """Extract (windows_tuple, signals_tuple) from a flat params dict.

    Recognizes two formats:
    1. Legacy: 'window' + 'signal' → single-factor
    2. Indexed: 'window_0', 'signal_0', 'window_1', 'signal_1', ...

    Returns:
        (windows, signals) — tuples of length num_factors.
    """
    if 'window' in params and 'signal' in params:
        # Legacy single-factor format
        return (params['window'],), (params['signal'],)

    windows = []
    signals = []
    for i in range(num_factors):
        w_key = f'window_{i}'
        s_key = f'signal_{i}'
        if w_key not in params or s_key not in params:
            raise ValueError(
                f"Missing '{w_key}' or '{s_key}' in params for "
                f"{num_factors}-factor config"
            )
        windows.append(params[w_key])
        signals.append(params[s_key])
    return tuple(windows), tuple(signals)


class ParametersOptimization:

    def __init__(self, data, config, *, fee_bps=None):
        self.data = data
        self.config = config
        self.fee_bps = fee_bps

    def optimize_grid(self, param_grid: dict):
        """Sweep over an N-dimensional parameter grid.

        Args:
            param_grid: dict mapping parameter names to sequences of values.
                Single-factor: ``window``, ``signal`` (legacy).
                Multi-factor: ``window_0``, ``signal_0``, ``window_1``, ``signal_1``, ...
                Optional: ``factor``, ``indicator``, ``strategy``.

        Yields:
            dict with all parameter values plus ``sharpe``.
        """
        num_factors = len(self.config.factors)

        # Validate required keys
        has_legacy = 'window' in param_grid and 'signal' in param_grid
        has_indexed = f'window_0' in param_grid and f'signal_0' in param_grid
        if not has_legacy and not has_indexed:
            raise ValueError(
                "param_grid must contain 'window'+'signal' (single-factor) "
                "or 'window_0'+'signal_0' (indexed) keys"
            )

        keys = list(param_grid.keys())
        value_lists = [list(param_grid[k]) for k in keys]
        total = 1
        for v in value_lists:
            total *= len(v)

        dim_desc = " × ".join(
            f"{len(v)} {k}s" for k, v in zip(keys, value_lists)
        )
        logger.info("Starting grid search: %s = %d combinations",
                     dim_desc, total)

        for combo in itertools.product(*value_lists):
            params = dict(zip(keys, combo))
            try:
                data_copy = self.data.copy()
                if 'factor' in params:
                    data_copy['factor'] = data_copy[params['factor']]

                indicator_name = params.get('indicator',
                                            self.config.factors[0].indicator_name)
                strategy_func = params.get('strategy',
                                           self.config.strategy_func)

                if (indicator_name != self.config.factors[0].indicator_name
                        or strategy_func != self.config.strategy_func):
                    from strat import FactorConfig
                    config = StrategyConfig(
                        factors=tuple(
                            FactorConfig(f.column, indicator_name)
                            for f in self.config.factors
                        ),
                        strategy_func=strategy_func,
                        trading_period=self.config.trading_period,
                        conjunction=self.config.conjunction,
                    )
                else:
                    config = self.config

                windows, signals = _parse_indexed_params(params, len(config.factors))

                perf = Performance(data_copy, config,
                                   windows, signals,
                                   fee_bps=self.fee_bps)
                sharpe = perf.get_sharpe_ratio()
            except Exception:
                logger.warning("Grid search failed for %s", params,
                               exc_info=True)
                sharpe = np.nan

            result = {}
            for k, v in params.items():
                result[k] = v.__name__ if callable(v) else v
            result['sharpe'] = sharpe
            yield result

        logger.info("Grid search complete: %d combinations evaluated", total)

    def optimize(self, indicator_tuple: tuple, strategy_tuple: tuple,
                 factor_columns=None):
        """Backward-compatible 2D/3D grid search.

        Wraps :meth:`optimize_grid` and yields tuples instead of dicts.
        """
        param_grid = {
            'window': indicator_tuple,
            'signal': strategy_tuple,
        }
        if factor_columns is not None:
            param_grid['factor'] = factor_columns

        for result in self.optimize_grid(param_grid):
            if factor_columns is not None:
                yield (result['window'], result['signal'],
                       result['factor'], result['sharpe'])
            else:
                yield (result['window'], result['signal'], result['sharpe'])
