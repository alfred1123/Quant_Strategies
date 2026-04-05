'''
Strategy module — technical indicators, trading signals, and strategy configuration.

Consolidates ta.py (TechnicalAnalysis) and signal.py (Strategy signals) into a
single module for the backtest pipeline.

Pipeline: data.py → strat.py → perf.py → param_opt.py → walk_forward.py
'''

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable identity of a trading strategy — portable across backtest and live.

    Carries *what* to run (indicator + strategy + annualisation) but not
    platform-specific details like transaction fees or data.
    """
    indicator_name: str        # TechnicalAnalysis method name, e.g. "get_bollinger_band"
    signal_func: Callable      # e.g. SignalDirection.momentum_const_signal
    trading_period: int        # 365 (crypto) or 252 (equity)


class TechnicalAnalysis:
    """Technical analysis indicators operating on a 'factor' column."""

    def __init__(self, data) -> None:
        if 'factor' not in data.columns:
            logger.error("DataFrame missing required 'factor' column, got: %s",
                         list(data.columns))
            raise ValueError("DataFrame must contain a 'factor' column")
        self.data = data
        logger.debug("TechnicalAnalysis initialized with %d rows", len(data))

    def get_sma(self, period):
        """Simple moving average.

        Args:
            period (int): moving average period

        Returns:
            pd.Series: SMA values
        """
        sma = self.data['factor'].rolling(window=period).mean()
        return sma

    def get_ema(self, period):
        """Exponential moving average.

        Args:
            period (int): moving average period

        Returns:
            pd.Series: EMA values
        """
        ema = self.data['factor'].ewm(span=period, adjust=False).mean()
        return ema

    def get_rsi(self, period):
        """Relative Strength Index.

        Args:
            period (int): RSI period

        Returns:
            pd.Series: RSI values (0-100)
        """
        delta = self.data['factor'].diff(1)
        delta = delta.dropna()
        up = delta.copy()
        down = delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up1 = up.rolling(window=period).mean()
        roll_down1 = down.abs().rolling(window=period).mean()
        RS1 = roll_up1 / roll_down1
        rsi = 100.0 - (100.0 / (1.0 + RS1))
        return rsi

    # too many parameters, may tend to overfitting, disabled for now
    # def get_macd(self, period1, period2, period3):
    #     ema1 = self.data['factor'].ewm(span=period1, adjust=False).mean()
    #     ema2 = self.data['factor'].ewm(span=period2, adjust=False).mean()
    #     macd = ema1 - ema2
    #     signal = macd.ewm(span=period3, adjust=False).mean()
    #     return macd, signal

    def get_bollinger_band(self, period):
        """Bollinger Band z-score.

        Args:
            period (int): bollinger band period

        Returns:
            pd.Series: z-score values
        """
        sma = self.data['factor'].rolling(window=period).mean()
        rstd = self.data['factor'].rolling(window=period).std()
        z = (self.data['factor'] - sma) / rstd
        return z

    def get_stochastic_oscillator(self, period):
        """Stochastic oscillator (%D — smoothed).

        Requires 'High', 'Low', 'Close' columns in data.

        Args:
            period (int): stochastic oscillator period

        Returns:
            pd.Series: smoothed stochastic oscillator values
        """
        high = self.data['High'].rolling(window=period).max()
        low = self.data['Low'].rolling(window=period).min()
        k = 100 * (self.data['Close'] - low) / (high - low)
        d = k.rolling(window=period).mean()
        return d


class SignalDirection:
    """Trading signal generators — all static methods with signature (data_col, signal)."""


# Backward-compat alias
Strategy = SignalDirection

    @staticmethod
    def momentum_const_signal(data_col, signal):
        """Go long when indicator > signal, short when < -signal, flat otherwise.

        Args:
            data_col: indicator values (numpy array or pd.Series)
            signal: threshold parameter

        Returns:
            numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
        """
        position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def reversion_const_signal(data_col, signal):
        """Go long when indicator < -signal, short when > signal, flat otherwise.

        Args:
            data_col: indicator values (numpy array or pd.Series)
            signal: threshold parameter

        Returns:
            numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
        """
        position = np.where(data_col < -signal, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position
