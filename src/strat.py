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
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubStrategy:
    """One indicator + signal direction pair with its parameters.

    Maps 1:1 to elements in the ``substrategies`` JSON array
    in the ``substrategies`` JSON array (design doc §1.1).
    """
    indicator_name: str        # TechnicalAnalysis method, e.g. "get_bollinger_band"
    signal_func_name: str      # SignalDirection method name, e.g. "momentum_band_signal"
    window: int                # indicator lookback period
    signal: float              # threshold
    data_column: str = "v"     # which raw column becomes 'factor'
    internal_cusip: str | None = None  # indicator underlying; None = use StrategyConfig.internal_cusip

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

    ``internal_cusip`` records the stable product identifier from
    ``INST.PRODUCT.INTERNAL_CUSIP`` (format ``symbol.exchange``,
    always lowercase, e.g. ``"btc-usd.crypto"``, ``"aapl.nyse"``).
    Vendor-specific symbols are resolved via ``INST.PRODUCT_XREF``.
    """
    internal_cusip: str        # INST.PRODUCT.INTERNAL_CUSIP, e.g. "btc-usd.crypto"
    indicator_name: str        # TechnicalAnalysis method name, e.g. "get_bollinger_band"
    signal_func: Callable      # e.g. SignalDirection.momentum_band_signal
    trading_period: int        # 365 (crypto) or 252 (equity)
    strategy_id: str = field(default_factory=lambda: str(uuid7()))
    name: str = ""             # human-readable; auto-generated if empty
    conjunction: str = "AND"   # "AND" | "OR" | "FILTER" — how substrategies combine
    substrategies: tuple = ()  # tuple[SubStrategy, ...]; empty = single-factor legacy

    @classmethod
    def single(cls, internal_cusip, indicator_name, signal_func, trading_period,
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
            internal_cusip=internal_cusip,
            indicator_name=indicator_name,
            signal_func=signal_func,
            trading_period=trading_period,
            substrategies=(sub,),
            **kwargs,
        )

    def get_internal_cusips(self) -> set:
        """Return all unique internal CUSIPs needed by this strategy."""
        cusips = {self.internal_cusip}
        for sub in self.substrategies:
            if sub.internal_cusip is not None:
                cusips.add(sub.internal_cusip)
        return cusips

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


def combine_positions(positions: list, conjunction: str = "AND",
                      strengths: list | None = None) -> np.ndarray:
    """Combine position arrays from multiple factors using AND/OR/FILTER logic.

    Args:
        positions: list of numpy arrays, each containing {-1, 0, 1, NaN}.
        conjunction: "AND"    — position only when ALL agree;
                     "OR"     — position when ANY factor signals;
                     "FILTER" — first factor gates on/off (non-zero = pass),
                                remaining factors provide direction (AND-combined).
        strengths: optional list of numpy arrays with raw indicator values.
            When provided, conflicts are resolved by signal strength
            (the factor with the most extreme reading wins) instead of
            going flat (AND) or defaulting to long (OR).

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
    if conj not in ("AND", "OR", "FILTER"):
        raise ValueError(f"conjunction must be 'AND', 'OR', or 'FILTER', got '{conjunction}'")

    stacked = np.column_stack(positions)  # shape (n, num_factors)
    nan_mask = np.isnan(stacked).any(axis=1)
    signs = np.sign(stacked)

    if conj == "FILTER":
        # First factor = gate (non-zero = active, direction ignored).
        # Remaining factors = signal (provide direction, AND-combined).
        gate = signs[:, 0] != 0  # True when gate is active

        if signs.shape[1] == 2:
            # Single signal factor — use its direction directly
            combined = np.where(gate, stacked[:, 1], 0.0)
        else:
            # Multiple signal factors — AND-combine them
            sig_signs = signs[:, 1:]
            all_pos = (sig_signs == 1).all(axis=1)
            all_neg = (sig_signs == -1).all(axis=1)
            direction = np.where(all_pos, 1.0, np.where(all_neg, -1.0, 0.0))

            # Disagreement among signals: resolve by strength if available
            if strengths is not None:
                sig_strengths = strengths[1:]
                sig_positions = positions[1:]
                has_signal = (sig_signs != 0).any(axis=1)
                disagree = ~all_pos & ~all_neg & has_signal & ~nan_mask
                if disagree.any():
                    raw = np.column_stack(sig_strengths).astype(float)
                    n_rows, n_cols = raw.shape
                    pctile = np.full_like(raw, 0.5)
                    for j in range(n_cols):
                        col = raw[:, j]
                        valid_mask = ~np.isnan(col)
                        valid_count = valid_mask.sum()
                        if valid_count <= 1:
                            continue
                        sorted_vals = np.sort(col[valid_mask])
                        ranks = np.searchsorted(sorted_vals, col[valid_mask], side='right')
                        pctile[valid_mask, j] = ranks / valid_count
                    conv = np.abs(pctile - 0.5)
                    masked = np.where(sig_signs[disagree] != 0, conv[disagree], -np.inf)
                    winner = np.argmax(masked, axis=1)
                    rows = np.arange(disagree.sum())
                    direction[disagree] = sig_signs[disagree][rows, winner]

            combined = np.where(gate, direction, 0.0)

        combined = combined.astype(float)
        combined[nan_mask] = np.nan
        return combined

    # Build per-factor conviction from raw indicator strengths.
    # Percentile-rank each factor column independently, then measure
    # distance from the median (0.5).  More extreme readings — whether
    # at the top or bottom of the historical distribution — yield
    # higher conviction.  Scale-invariant: RSI (0-100), Bollinger z
    # (-3 to +3), and SMA ($) all become directly comparable.
    conviction = None
    if strengths is not None:
        raw = np.column_stack(strengths).astype(float)
        n_rows, n_cols = raw.shape
        pctile = np.full_like(raw, 0.5)
        for j in range(n_cols):
            col = raw[:, j]
            valid_mask = ~np.isnan(col)
            valid_count = valid_mask.sum()
            if valid_count <= 1:
                continue  # single value → neutral conviction (0.5)
            sorted_vals = np.sort(col[valid_mask])
            ranks = np.searchsorted(sorted_vals, col[valid_mask], side='right')
            pctile[valid_mask, j] = ranks / valid_count
        conviction = np.abs(pctile - 0.5)

    if conj == "AND":
        all_positive = (signs == 1).all(axis=1)
        all_negative = (signs == -1).all(axis=1)
        combined = np.where(all_positive, 1.0, np.where(all_negative, -1.0, 0.0))

        # Disagreement: strongest non-zero factor wins when strengths available
        if conviction is not None:
            has_signal = (signs != 0).any(axis=1)
            disagree = ~all_positive & ~all_negative & has_signal & ~nan_mask
            if disagree.any():
                masked = np.where(signs[disagree] != 0, conviction[disagree], -np.inf)
                winner = np.argmax(masked, axis=1)
                rows = np.arange(disagree.sum())
                combined[disagree] = signs[disagree][rows, winner]
    else:  # OR
        any_positive = (signs == 1).any(axis=1)
        any_negative = (signs == -1).any(axis=1)
        conflict = any_positive & any_negative

        # No conflict: straightforward direction
        combined = np.where(any_positive & ~conflict, 1.0,
                            np.where(any_negative & ~conflict, -1.0, 0.0))

        if conviction is not None and conflict.any():
            # Conflict: strongest signal wins
            masked = np.where(signs[conflict] != 0, conviction[conflict], -np.inf)
            winner = np.argmax(masked, axis=1)
            rows = np.arange(conflict.sum())
            combined[conflict] = signs[conflict][rows, winner]
        else:
            # Legacy fallback: positive wins over negative
            combined[conflict] = 1.0

    combined[nan_mask] = np.nan
    return combined


class SignalDirection:
    """Trading signal generators — all static methods with signature (data_col, signal)."""

    @staticmethod
    def momentum_band_signal(data_col, signal):
        """Go long when indicator > +signal, short when < -signal, flat otherwise.

        Symmetric band around zero — for unbounded/zero-centered indicators
        (Bollinger z-score, SMA deviation, EMA deviation).

        Args:
            data_col: indicator values (numpy array or pd.Series)
            signal: half-width of the band

        Returns:
            numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
        """
        position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def reversion_band_signal(data_col, signal):
        """Go long when indicator < -signal, short when > +signal, flat otherwise.

        Inverse of ``momentum_band_signal``.

        Args:
            data_col: indicator values (numpy array or pd.Series)
            signal: half-width of the band

        Returns:
            numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
        """
        position = np.where(data_col < -signal, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def momentum_bounded_signal(data_col, signal):
        """Go long when indicator > signal, short when < (100 - signal), flat otherwise.

        Two-sided level threshold for 0–100 bounded indicators (RSI, stochastic).
        ``signal`` is the upper boundary; the lower is mirrored at ``100 - signal``.

        Example: signal=70 → long when > 70, short when < 30, flat 30–70.

        Args:
            data_col: indicator values (numpy array or pd.Series)
            signal: upper threshold (lower = 100 - signal)

        Returns:
            numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
        """
        lower = 100 - signal
        position = np.where(data_col > signal, 1, np.where(data_col < lower, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def reversion_bounded_signal(data_col, signal):
        """Go long when indicator < (100 - signal), short when > signal, flat otherwise.

        Inverse of ``momentum_bounded_signal`` — mean-reversion on 0–100
        bounded indicators. Overbought (> signal) → short, oversold
        (< 100 - signal) → long.

        Example: signal=70 → short when > 70, long when < 30, flat 30–70.

        Args:
            data_col: indicator values (numpy array or pd.Series)
            signal: upper threshold (lower = 100 - signal)

        Returns:
            numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
        """
        lower = 100 - signal
        position = np.where(data_col < lower, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position


# Backward-compat alias
Strategy = SignalDirection


def resolve_signal_func(signal_name: str, indicator_name: str,
                        indicator_rows: list[dict],
                        signal_type_rows: list[dict]) -> Callable:
    """Resolve user-facing signal direction + indicator → concrete signal function.

    Reads ``IS_BOUNDED_IND`` from ``REFDATA.INDICATOR`` and picks
    ``FUNC_NAME_BAND`` or ``FUNC_NAME_BOUNDED`` from ``REFDATA.SIGNAL_TYPE``.

    Args:
        signal_name: user-facing name, e.g. ``"momentum"`` or ``"reversion"``
        indicator_name: TechnicalAnalysis method, e.g. ``"get_rsi"``
        indicator_rows: cached rows from ``REFDATA.INDICATOR``
        signal_type_rows: cached rows from ``REFDATA.SIGNAL_TYPE``

    Returns:
        Callable on ``SignalDirection``

    Raises:
        ValueError: if signal_name or indicator_name not found in REFDATA
    """
    # 1. Look up indicator → is it bounded?
    ind = next((r for r in indicator_rows
                if r["method_name"] == indicator_name), None)
    if ind is None:
        raise ValueError(f"Unknown indicator: {indicator_name}")
    bounded = ind.get("is_bounded_ind") == "Y"

    # 2. Look up signal type → pick correct func column
    sig = next((r for r in signal_type_rows
                if r["name"] == signal_name), None)
    if sig is None:
        raise ValueError(f"Unknown signal type: {signal_name}")
    func_name = sig["func_name_bounded"] if bounded else sig["func_name_band"]

    # 3. Resolve to actual callable
    func = getattr(SignalDirection, func_name, None)
    if func is None:
        raise ValueError(f"SignalDirection has no method '{func_name}'")
    return func


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
        "internal_cusip": config.internal_cusip,
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
                **({"internal_cusip": s.internal_cusip} if s.internal_cusip else {}),
            }
            for i, s in enumerate(subs)
        ],
    }


def backtest_results_to_json(strategy_id, perf, internal_cusip, start, end, fee_bps):
    """Serialize backtest Performance metrics to JSON."""
    return {
        "strategy_id": strategy_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "data_range": {"start": start, "end": end},
        "internal_cusip": internal_cusip,
        "fee_bps": fee_bps,
        "metrics": perf.get_strategy_performance().to_dict(),
        "buy_hold_metrics": perf.get_buy_hold_performance().to_dict(),
    }


def _auto_name(config, subs):
    """Generate a short name: ``{internal_cusip}_strategy_{id_prefix}``."""
    short_id = config.strategy_id[:8]
    return f"{config.internal_cusip}_strategy_{short_id}"
