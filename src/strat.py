# we will be storing all the strategies here before we move them to the main file
# we will need a unique name for each strategy wtih ID

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable identity of a trading strategy — portable across backtest and live.

    Carries *what* to run (indicator + strategy + annualisation) but not
    platform-specific details like transaction fees or data.
    """
    indicator_name: str        # TechnicalAnalysis method name, e.g. "get_bollinger_band"
    strategy_func: Callable    # e.g. Strategy.momentum_const_signal
    trading_period: int        # 365 (crypto) or 252 (equity)


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