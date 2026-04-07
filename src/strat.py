'''
Strategy module — technical indicators, trading signals, and strategy configuration.

Consolidates ta.py (TechnicalAnalysis) and signal.py (Strategy signals) into a
single module for the backtest pipeline.

Pipeline: data.py → strat.py → perf.py → param_opt.py → walk_forward.py
'''

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from uuid_extensions import uuid7

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indicator defaults — sensible window/signal bounds per indicator
# ---------------------------------------------------------------------------

INDICATOR_DEFAULTS = {
    "get_sma": {
        "win_min": 5, "win_max": 200, "win_step": 5,
        "sig_min": 0.0, "sig_max": 0.10, "sig_step": 0.01,
    },
    "get_ema": {
        "win_min": 5, "win_max": 200, "win_step": 5,
        "sig_min": 0.0, "sig_max": 0.10, "sig_step": 0.01,
    },
    "get_rsi": {
        "win_min": 5, "win_max": 50, "win_step": 1,
        "sig_min": 10.0, "sig_max": 40.0, "sig_step": 5.0,
    },
    "get_bollinger_band": {
        "win_min": 10, "win_max": 100, "win_step": 5,
        "sig_min": 0.25, "sig_max": 2.50, "sig_step": 0.25,
    },
    "get_stochastic_oscillator": {
        "win_min": 5, "win_max": 50, "win_step": 5,
        "sig_min": 10.0, "sig_max": 40.0, "sig_step": 5.0,
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubStrategy:
    """One indicator + signal direction pair with its parameters.

    Maps 1:1 to elements in the ``substrategies`` JSON array
    in the ``substrategies`` JSON array (design doc §1.1).
    """
    indicator_name: str        # TechnicalAnalysis method, e.g. "get_bollinger_band"
    signal_func_name: str      # SignalDirection method name, e.g. "momentum_const_signal"
    window: int                # indicator lookback period
    signal: float              # threshold
    data_column: str = "v"     # which raw column becomes 'factor'

    def resolve_signal_func(self) -> Callable:
        """Resolve ``signal_func_name`` to an actual callable on ``SignalDirection``."""
        return getattr(SignalDirection, self.signal_func_name)


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable identity of a trading strategy — portable across backtest and live.

    Carries *what* to run (indicator + strategy + annualisation) but not
    platform-specific details like transaction fees or data.

    ``strategy_id`` links this config to DeploymentConfig and DB records
    (``BT.STRATEGY.STRATEGY_ID``).

    ``ticker`` records the data-source symbol the strategy was backtested on
    (e.g. ``"BTC-USD"`` for Yahoo Finance).  Broker-specific symbols
    (e.g. ``"US.AAPL"`` for Futu) live in DeploymentConfig; the mapping
    between them is stored in ``REFDATA.TICKER_MAPPING``.
    """
    ticker: str                # Data-source symbol, e.g. "BTC-USD", "AAPL"
    indicator_name: str        # TechnicalAnalysis method name, e.g. "get_bollinger_band"
    signal_func: Callable      # e.g. SignalDirection.momentum_const_signal
    trading_period: int        # 365 (crypto) or 252 (equity)
    strategy_id: str = field(default_factory=lambda: str(uuid7()))
    name: str = ""             # human-readable; auto-generated if empty
    conjunction: str = "AND"   # "AND" | "OR" — how substrategies combine
    substrategies: tuple = ()  # tuple[SubStrategy, ...]; empty = single-factor legacy

    @classmethod
    def single(cls, ticker, indicator_name, signal_func, trading_period,
               window=20, signal=1.0, data_column="v", **kwargs):
        """Convenience constructor for the common single-indicator case.

        Builds a ``SubStrategy`` internally so the config is fully
        self-describing for JSON serialization.
        """
        sub = SubStrategy(
            indicator_name=indicator_name,
            signal_func_name=signal_func.__name__,
            window=window,
            signal=signal,
            data_column=data_column,
        )
        return cls(
            ticker=ticker,
            indicator_name=indicator_name,
            signal_func=signal_func,
            trading_period=trading_period,
            substrategies=(sub,),
            **kwargs,
        )

    def get_substrategies(self):
        """Return substrategies, synthesizing one from top-level fields if empty."""
        if self.substrategies:
            return list(self.substrategies)
        # Legacy single-factor config — synthesize a SubStrategy for callers
        # that need the uniform interface.
        return [SubStrategy(
            indicator_name=self.indicator_name,
            signal_func_name=self.signal_func.__name__,
            window=0,      # caller must supply window separately
            signal=0.0,    # caller must supply signal separately
            data_column="factor",
        )]


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


def combine_positions(positions: list, conjunction: str = "AND") -> np.ndarray:
    """Combine position arrays from multiple factors using AND/OR logic.

    Args:
        positions: list of numpy arrays, each containing {-1, 0, 1, NaN}.
        conjunction: "AND" — position only when ALL agree;
                     "OR"  — position when ANY factor signals.

    Returns:
        numpy array of {-1.0, 0.0, 1.0}, NaN where any input is NaN.

    Raises:
        ValueError: if positions list is empty or conjunction is invalid.
    """
    if not positions:
        raise ValueError("positions list must not be empty")

    if len(positions) == 1:
        return positions[0].copy()

    conj = conjunction.upper()
    if conj not in ("AND", "OR"):
        raise ValueError(f"conjunction must be 'AND' or 'OR', got '{conjunction}'")

    stacked = np.column_stack(positions)  # shape (n, num_factors)
    nan_mask = np.isnan(stacked).any(axis=1)

    if conj == "AND":
        # All factors must agree on the same non-zero direction
        signs = np.sign(stacked)
        all_positive = (signs == 1).all(axis=1)
        all_negative = (signs == -1).all(axis=1)
        combined = np.where(all_positive, 1.0, np.where(all_negative, -1.0, 0.0))
    else:  # OR
        # Any factor with a non-zero signal wins; take the first non-zero direction
        signs = np.sign(stacked)
        any_positive = (signs == 1).any(axis=1)
        any_negative = (signs == -1).any(axis=1)
        # Positive wins over negative when both present (arbitrary but consistent)
        combined = np.where(any_positive, 1.0, np.where(any_negative, -1.0, 0.0))

    combined[nan_mask] = np.nan
    return combined


class SignalDirection:
    """Trading signal generators — all static methods with signature (data_col, signal)."""

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


# Backward-compat alias
Strategy = SignalDirection


# ---------------------------------------------------------------------------
# JSON serialization  (design doc §8)
# ---------------------------------------------------------------------------

def strategy_to_json(config: StrategyConfig, window=None, signal=None) -> dict:
    """Serialize a StrategyConfig to the Strategy JSON schema.

    If ``config.substrategies`` is populated, ``window`` and ``signal`` are
    ignored (they come from each SubStrategy).  For legacy single-factor
    configs, ``window`` and ``signal`` are required.
    """
    subs = config.get_substrategies()

    # Legacy path: inject window/signal into the synthesized sub
    if not config.substrategies:
        if window is None or signal is None:
            raise ValueError("window and signal required for legacy StrategyConfig "
                             "without substrategies")
        subs = [SubStrategy(
            indicator_name=config.indicator_name,
            signal_func_name=config.signal_func.__name__,
            window=window,
            signal=signal,
            data_column="v",
        )]

    name = config.name or _auto_name(config, subs)

    return {
        "strategy_id": config.strategy_id,
        "name": name,
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ticker": config.ticker,
        "conjunction": config.conjunction,
        "trading_period": config.trading_period,
        "substrategies": [
            {
                "id": i + 1,
                "indicator": s.indicator_name,
                "signal_func": s.signal_func_name,
                "window": s.window,
                "signal": s.signal,
                "data_column": s.data_column,
            }
            for i, s in enumerate(subs)
        ],
    }


def backtest_results_to_json(strategy_id, perf, ticker, start, end, fee_bps):
    """Serialize backtest Performance metrics to JSON."""
    return {
        "strategy_id": strategy_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "data_range": {"start": start, "end": end},
        "ticker_backtested": ticker,
        "fee_bps": fee_bps,
        "metrics": perf.get_strategy_performance().to_dict(),
        "buy_hold_metrics": perf.get_buy_hold_performance().to_dict(),
    }


def _auto_name(config, subs):
    """Generate a short name: ``{ticker}_strategy_{id_prefix}``."""
    short_id = config.strategy_id[:8]
    return f"{config.ticker}_strategy_{short_id}"
