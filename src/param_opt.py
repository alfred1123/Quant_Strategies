'''
N-dimensional parameter grid search for the backtest pipeline.

Sweeps over arbitrary combinations of window, signal, factor, indicator,
and strategy — yielding Sharpe ratios for each combination.
'''

import itertools
import logging

import pandas as pd
import numpy as np

from perf import Performance
from strat import StrategyConfig

logger = logging.getLogger(__name__)


class ParametersOptimization:

    def __init__(self, data, config, *, fee_bps=None):
        self.data = data
        self.config = config
        self.fee_bps = fee_bps

    def optimize_grid(self, param_grid: dict):
        """Sweep over an N-dimensional parameter grid.

        Args:
            param_grid: dict mapping parameter names to sequences of values.
                Required keys: ``window``, ``signal``.
                Optional keys:
                    ``factor``    — column name strings, overrides data['factor'].
                    ``indicator`` — TechnicalAnalysis method name strings.
                    ``strategy``  — callables (stored by ``__name__`` in output).

        Yields:
            dict with all parameter values plus ``sharpe``.
        """
        if 'window' not in param_grid or 'signal' not in param_grid:
            raise ValueError("param_grid must contain 'window' and 'signal' keys")

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
                                            self.config.indicator_name)
                strategy_func = params.get('strategy',
                                           self.config.strategy_func)

                if (indicator_name != self.config.indicator_name
                        or strategy_func != self.config.strategy_func):
                    config = StrategyConfig(
                        indicator_name=indicator_name,
                        strategy_func=strategy_func,
                        trading_period=self.config.trading_period,
                    )
                else:
                    config = self.config

                perf = Performance(data_copy, config,
                                   params['window'], params['signal'],
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
