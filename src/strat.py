# we will be storing all the strategies here before we move them to the main file
# we will need a unique name for each strategy wtih ID

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactorConfig:
    """Defines a single factor in a multi-factor strategy.

    Attributes:
        column: DataFrame column name to use as the indicator input (e.g. 'price', 'volume').
        indicator_name: TechnicalAnalysis method name (e.g. 'get_bollinger_band').
    """
    column: str
    indicator_name: str


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable identity of a trading strategy — portable across backtest and live.

    Carries *what* to run (factors + strategy + annualisation) but not
    platform-specific details like transaction fees or data.

    Single-factor usage (backward-compatible):
        StrategyConfig(
            factors=(FactorConfig('price', 'get_bollinger_band'),),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
        )

    Multi-factor conjunction:
        StrategyConfig(
            factors=(
                FactorConfig('price', 'get_bollinger_band'),
                FactorConfig('volume', 'get_bollinger_band'),
            ),
            strategy_func=Strategy.momentum_const_signal,
            trading_period=365,
            conjunction='AND',
        )
    """
    factors: tuple             # tuple[FactorConfig, ...]
    strategy_func: Callable    # e.g. Strategy.momentum_const_signal
    trading_period: int        # 365 (crypto) or 252 (equity)
    conjunction: str = 'AND'   # 'AND' | 'OR'


def combine_positions(factor_positions, conjunction):
    """Combine per-factor position arrays via AND/OR conjunction.

    Args:
        factor_positions: list of numpy arrays, each with values in {-1, 0, 1, NaN}.
        conjunction: 'AND' or 'OR'.

    Returns:
        numpy array — combined position.

    AND logic:
        LONG (+1) when ALL factors = +1.
        SHORT (-1) when ALL factors = -1.
        Otherwise 0.

    OR logic:
        LONG (+1) when ANY factor = +1.
        SHORT (-1) when ANY factor = -1.
        If both LONG and SHORT are present, result is 0 (conflict).

    NaN propagation: if ANY factor is NaN at a given index, the result is NaN.
    """
    if not factor_positions:
        raise ValueError("factor_positions must not be empty")

    stacked = np.column_stack(factor_positions)  # shape (n, num_factors)
    n = stacked.shape[0]

    # NaN mask: True where ANY factor is NaN
    nan_mask = np.any(np.isnan(stacked), axis=1)

    if conjunction == 'AND':
        # LONG when ALL factors are +1
        all_long = np.all(stacked == 1, axis=1)
        # SHORT when ALL factors are -1
        all_short = np.all(stacked == -1, axis=1)
        result = np.where(all_long, 1.0, np.where(all_short, -1.0, 0.0))
    elif conjunction == 'OR':
        any_long = np.any(stacked == 1, axis=1)
        any_short = np.any(stacked == -1, axis=1)
        # Conflict: both long and short signals → flat
        result = np.where(
            any_long & any_short, 0.0,
            np.where(any_long, 1.0, np.where(any_short, -1.0, 0.0))
        )
    else:
        raise ValueError(f"conjunction must be 'AND' or 'OR', got '{conjunction}'")

    result[nan_mask] = np.nan
    return result


class Strategy:
    
    def __init__(self):
        pass
    
    def momentum_const_signal(data_col, signal):
        position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position
    
    def reversion_const_signal(data_col, signal):
        position = np.where(data_col < -signal, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position