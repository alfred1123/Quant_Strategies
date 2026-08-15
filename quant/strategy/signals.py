"""Trading signal generators, multi-factor combiner, and strategy config.

Includes the data-model dataclasses (``StrategyConfig``, ``SubStrategy``)
that link to ``BT.STRATEGY``, the four ``SignalDirection`` static methods
(momentum/reversion × band/bounded), the ``combine_positions`` helper,
and JSON serialisation entry points.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from uuid_extensions import uuid7

from quant.shared.util import utc_now_iso

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubStrategy:
    """One indicator + signal direction pair with its parameters."""

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
    """Immutable identity of a trading strategy — portable across backtest and live."""

    internal_cusip: str        # INST.PRODUCT.INTERNAL_CUSIP, e.g. "btcusdt.crypto"
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
        """Convenience constructor for the common single-indicator case."""
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
        return [SubStrategy(
            indicator_name=self.indicator_name,
            signal_func_name=self.signal_func.__name__,
            window=0,
            signal=0.0,
            data_column="factor",
        )]


# ---------------------------------------------------------------------------
# Signal combination
# ---------------------------------------------------------------------------

def _conviction(strengths: list) -> np.ndarray:
    """Per-factor conviction from raw indicator strengths.

    Percentile-ranks each factor's raw values, then measures distance from
    the median (0.5) — the more extreme the reading, the higher the conviction.
    """
    raw = np.column_stack(strengths).astype(float)
    pctile = np.full_like(raw, 0.5)
    for j in range(raw.shape[1]):
        col = raw[:, j]
        valid_mask = ~np.isnan(col)
        valid_count = valid_mask.sum()
        if valid_count <= 1:
            continue
        sorted_vals = np.sort(col[valid_mask])
        ranks = np.searchsorted(sorted_vals, col[valid_mask], side='right')
        pctile[valid_mask, j] = ranks / valid_count
    return np.abs(pctile - 0.5)


def _strongest_sign(signs: np.ndarray, conviction: np.ndarray,
                    rows: np.ndarray) -> np.ndarray:
    """For each selected row, the sign of the most convicted non-flat factor."""
    masked = np.where(signs[rows] != 0, conviction[rows], -np.inf)
    winner = np.argmax(masked, axis=1)
    idx = np.arange(rows.sum())
    return signs[rows][idx, winner]


def _combine_filter(stacked: np.ndarray, signs: np.ndarray,
                    nan_mask: np.ndarray, strengths: list | None) -> np.ndarray:
    """FILTER: first factor gates on/off; remaining factors give direction."""
    gate = signs[:, 0] != 0  # True when gate is active

    if signs.shape[1] == 2:
        return np.where(gate, stacked[:, 1], 0.0)

    sig_signs = signs[:, 1:]
    all_pos = (sig_signs == 1).all(axis=1)
    all_neg = (sig_signs == -1).all(axis=1)
    direction = np.where(all_pos, 1.0, np.where(all_neg, -1.0, 0.0))

    if strengths is not None:
        has_signal = (sig_signs != 0).any(axis=1)
        disagree = ~all_pos & ~all_neg & has_signal & ~nan_mask
        if disagree.any():
            direction[disagree] = _strongest_sign(
                sig_signs, _conviction(strengths[1:]), disagree)

    return np.where(gate, direction, 0.0)


def _combine_and(signs: np.ndarray, nan_mask: np.ndarray,
                 conviction: np.ndarray | None) -> np.ndarray:
    """AND: position only when all factors agree; conviction breaks conflicts."""
    all_positive = (signs == 1).all(axis=1)
    all_negative = (signs == -1).all(axis=1)
    combined = np.where(all_positive, 1.0, np.where(all_negative, -1.0, 0.0))

    if conviction is not None:
        has_signal = (signs != 0).any(axis=1)
        disagree = ~all_positive & ~all_negative & has_signal & ~nan_mask
        if disagree.any():
            combined[disagree] = _strongest_sign(signs, conviction, disagree)
    return combined


def _combine_or(signs: np.ndarray, conviction: np.ndarray | None) -> np.ndarray:
    """OR: position when any factor signals; conviction (or long) breaks conflicts."""
    any_positive = (signs == 1).any(axis=1)
    any_negative = (signs == -1).any(axis=1)
    conflict = any_positive & any_negative

    combined = np.where(any_positive & ~conflict, 1.0,
                        np.where(any_negative & ~conflict, -1.0, 0.0))

    if conviction is not None and conflict.any():
        combined[conflict] = _strongest_sign(signs, conviction, conflict)
    else:
        combined[conflict] = 1.0
    return combined


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
        combined = _combine_filter(stacked, signs, nan_mask, strengths)
    else:
        conviction = _conviction(strengths) if strengths is not None else None
        if conj == "AND":
            combined = _combine_and(signs, nan_mask, conviction)
        else:  # OR
            combined = _combine_or(signs, conviction)

    combined = combined.astype(float)
    combined[nan_mask] = np.nan
    return combined


# ---------------------------------------------------------------------------
# Signal direction functions
# ---------------------------------------------------------------------------

class SignalDirection:
    """Trading signal generators — all static methods with signature (data_col, signal)."""

    @staticmethod
    def momentum_band_signal(data_col, signal):
        """Go long when indicator > +signal, short when < -signal, flat otherwise."""
        position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def reversion_band_signal(data_col, signal):
        """Go long when indicator < -signal, short when > +signal, flat otherwise."""
        position = np.where(data_col < -signal, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def momentum_bounded_signal(data_col, signal):
        """Go long when indicator > signal, short when < (100 - signal), flat otherwise."""
        lower = 100 - signal
        position = np.where(data_col > signal, 1, np.where(data_col < lower, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position

    @staticmethod
    def reversion_bounded_signal(data_col, signal):
        """Go long when indicator < (100 - signal), short when > signal, flat otherwise."""
        lower = 100 - signal
        position = np.where(data_col < lower, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position


# Pre-existing alias kept for callers that import the symbol ``Strategy``.
Strategy = SignalDirection


def resolve_signal_func(signal_name: str, indicator_name: str,
                        indicator_rows: list[dict],
                        signal_type_rows: list[dict]) -> Callable:
    """Resolve user-facing signal direction + indicator → concrete signal function.

    Reads ``IS_BOUNDED_IND`` from ``REFDATA.INDICATOR`` and picks
    ``FUNC_NAME_BAND`` or ``FUNC_NAME_BOUNDED`` from ``REFDATA.SIGNAL_TYPE``.
    """
    ind = next((r for r in indicator_rows
                if r["method_name"] == indicator_name), None)
    if ind is None:
        raise ValueError(f"Unknown indicator: {indicator_name}")
    bounded = ind.get("is_bounded_ind") == "Y"

    sig = next((r for r in signal_type_rows
                if r["name"] == signal_name), None)
    if sig is None:
        raise ValueError(f"Unknown signal type: {signal_name}")
    func_name = sig["func_name_bounded"] if bounded else sig["func_name_band"]

    func = getattr(SignalDirection, func_name, None)
    if func is None:
        raise ValueError(f"SignalDirection has no method '{func_name}'")
    return func


# ---------------------------------------------------------------------------
# JSON serialization  (design doc §8)
# ---------------------------------------------------------------------------

def strategy_to_json(config: StrategyConfig, window=None, signal=None) -> dict:
    """Serialize a StrategyConfig to the Strategy JSON schema."""
    subs = config.get_substrategies()

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
        "created_at": utc_now_iso(),
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


def config_from_json(doc: dict) -> StrategyConfig:
    """Build a ``StrategyConfig`` from ``strategy_to_json`` output."""
    internal = doc.get("internal_cusip") or doc.get("ticker")
    if not internal:
        raise ValueError("CONFIG_JSON missing internal_cusip")

    subs_raw = doc.get("substrategies") or []
    if not subs_raw:
        raise ValueError("CONFIG_JSON has no substrategies")

    subs = tuple(
        SubStrategy(
            indicator_name=s["indicator"],
            signal_func_name=s["signal_func"],
            window=int(s["window"]),
            signal=float(s["signal"]),
            data_column=s.get("data_column", "v"),
            internal_cusip=s.get("internal_cusip"),
        )
        for s in subs_raw
    )
    first = subs[0]
    signal_func = getattr(SignalDirection, first.signal_func_name)
    return StrategyConfig(
        internal_cusip=internal,
        indicator_name=first.indicator_name,
        signal_func=signal_func,
        trading_period=int(doc.get("trading_period", 365)),
        strategy_id=str(doc.get("strategy_id", "")),
        name=doc.get("name", ""),
        conjunction=doc.get("conjunction", "AND"),
        substrategies=subs,
    )


def params_from_strategy_json(doc: dict) -> tuple:
    """Return ``(window, signal)`` from serialized strategy JSON."""
    subs = doc["substrategies"]
    if len(subs) == 1:
        return int(subs[0]["window"]), float(subs[0]["signal"])
    return (
        tuple(int(s["window"]) for s in subs),
        tuple(float(s["signal"]) for s in subs),
    )


def backtest_results_to_json(strategy_id, perf, internal_cusip, start, end, fee_bps):
    """Serialize backtest Performance metrics to JSON."""
    return {
        "strategy_id": strategy_id,
        "run_at": utc_now_iso(),
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
