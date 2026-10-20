"""Scalar Sharpe objective for parameter search.

Returns one number per ``(window, signal)`` set. Indicators and
``pct_change`` are computed once; the search loop only looks up arrays and
does numpy arithmetic. The rules it applies — which series a factor reads,
how PnL nets fees, when a Sharpe is undefined — are ``Performance``'s
(``FactorFrames``, ``strategy_pnl``, ``sharpe_ratio``); this module adds
only the per-window cache. ``Performance`` remains the engine for metrics,
equity curves, and trade-time positions.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from quant.strategy.indicators import TechnicalAnalysis
from quant.strategy.performance import (
    FactorFrames,
    Performance,
    sharpe_ratio,
    strategy_pnl,
)
from quant.strategy.signals import combine_positions

logger = logging.getLogger(__name__)


class IndicatorCache:
    """``{window: ndarray}`` for one factor, computed eagerly."""

    def __init__(self, frame: pd.DataFrame, indicator_name: str, windows) -> None:
        ta = TechnicalAnalysis(frame)
        self._arrays = {
            int(w): ta.indicator(indicator_name, w).to_numpy()
            for w in windows
        }

    def __getitem__(self, window) -> np.ndarray:
        return self._arrays[int(window)]

    def __contains__(self, window) -> bool:
        return int(window) in self._arrays


class Objective(ABC):
    """Precomputed inputs plus Sharpe math shared by single- and multi-factor."""

    def __init__(self, data: dict, config, *, fee_bps=None) -> None:
        self._config = config
        self._frames = FactorFrames(data, config)
        fee = Performance.DEFAULT_FEE_BPS if fee_bps is None else fee_bps
        self.transaction_cost = fee / 10_000
        self.trading_period = config.trading_period
        # Same pandas call Performance uses — do not re-derive the series.
        self.chg = self._frames.main["price"].pct_change().to_numpy()

    @staticmethod
    def for_config(data, config, window_values, *, fee_bps=None) -> "Objective":
        """Pick the subclass ``Performance`` would take for this config."""
        if len(config.get_substrategies()) > 1:
            return MultiFactorObjective(
                data, config, window_values, fee_bps=fee_bps,
            )
        return SingleFactorObjective(
            data, config, window_values, fee_bps=fee_bps,
        )

    @abstractmethod
    def __call__(self, windows, signals) -> float:
        """Sharpe for one parameter set. Tuples even for a single factor."""

    def _sharpe(self, position, metric_window: int) -> float:
        """``Performance.get_sharpe_ratio`` on arrays, after indicator warmup."""
        _, _, pnl = strategy_pnl(position, self.chg, self.transaction_cost)
        return sharpe_ratio(
            pnl[int(metric_window):],
            self.trading_period,
            min_obs=Performance.MIN_METRIC_OBS,
        )


class SingleFactorObjective(Objective):
    """One indicator cache, one signal function."""

    def __init__(self, data, config, windows, *, fee_bps=None) -> None:
        super().__init__(data, config, fee_bps=fee_bps)
        self._cache = IndicatorCache(
            self._frames.single_factor_frame(), config.indicator_name, windows,
        )
        self._signal_func = config.signal_func

    def __call__(self, windows, signals) -> float:
        window = int(windows[0])
        signal = float(signals[0])
        position = self._signal_func(self._cache[window], signal)
        return self._sharpe(position, window)


class MultiFactorObjective(Objective):
    """One cache per ``SubStrategy``; ``combine_positions`` with strengths."""

    def __init__(self, data, config, window_ranges, *, fee_bps=None) -> None:
        super().__init__(data, config, fee_bps=fee_bps)
        self._conjunction = config.conjunction
        self._caches = []
        self._signal_funcs = []
        for sub, windows in zip(config.get_substrategies(), window_ranges):
            frame = pd.DataFrame({"factor": self._frames.factor(sub)})
            self._caches.append(IndicatorCache(frame, sub.indicator_name, windows))
            self._signal_funcs.append(sub.resolve_signal_func())

    def __call__(self, windows, signals) -> float:
        positions = []
        strengths = []
        for i, (cache, func) in enumerate(zip(self._caches, self._signal_funcs)):
            ind = cache[int(windows[i])]
            positions.append(func(ind, float(signals[i])))
            strengths.append(ind)
        combined = combine_positions(
            positions, self._conjunction, strengths=strengths,
        )
        return self._sharpe(combined, max(int(w) for w in windows))
