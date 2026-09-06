"""Scalar Sharpe objective for parameter search.

A twin of ``Performance`` that returns one number per ``(window, signal)``
set. Indicators and ``pct_change`` are computed once; the search loop only
looks up arrays and does numpy arithmetic. ``Performance`` remains the
engine for metrics, equity curves, and trade-time positions.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from quant.strategy.indicators import TechnicalAnalysis
from quant.strategy.performance import Performance
from quant.strategy.signals import combine_positions

logger = logging.getLogger(__name__)


class IndicatorCache:
    """``{window: ndarray}`` for one factor, computed eagerly.

    Each array is ``reindex``-aligned to *frame* so a short indicator
    (``get_rsi`` drops the first row) cannot shift the position series.
    """

    def __init__(self, frame: pd.DataFrame, indicator_name: str, windows) -> None:
        ta = TechnicalAnalysis(frame)
        func = getattr(ta, indicator_name)
        self._arrays = {
            int(w): func(w).reindex(frame.index).to_numpy()
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
        self._all_data = data
        self._main = data[config.internal_cusip]
        fee = Performance.DEFAULT_FEE_BPS if fee_bps is None else fee_bps
        self.transaction_cost = fee / 10_000
        self.trading_period = config.trading_period
        # Same pandas call Performance uses — do not re-derive the series.
        self.chg = self._main["price"].pct_change().to_numpy()

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
        """Numpy form of ``Performance.get_sharpe_ratio`` (decision #63)."""
        pos = np.asarray(position, dtype=float)
        pos_x1 = np.empty_like(pos)
        pos_x1[0] = np.nan
        pos_x1[1:] = pos[:-1]
        trade = np.abs(pos - pos_x1)
        pnl = pos_x1 * self.chg - trade * self.transaction_cost
        sl = pnl[int(metric_window):]
        finite = sl[~np.isnan(sl)]
        if finite.size < Performance.MIN_METRIC_OBS:
            return np.nan
        std = finite.std(ddof=1)
        if std == 0 or np.isnan(std):
            return np.nan
        return float(finite.mean() / std * np.sqrt(self.trading_period))

    def _factor_series_for_sub(self, sub) -> pd.Series:
        """Factor column for *sub*, aligned to the traded product's index."""
        sub_cusip = sub.internal_cusip or self._config.internal_cusip
        sub_df = self._all_data[sub_cusip]
        if sub_cusip != self._config.internal_cusip:
            self._validate_factor_coverage(sub_df, sub_cusip)
        return sub_df[sub.data_column].reindex(self._main.index)

    def _validate_factor_coverage(self, factor_df, factor_cusip) -> None:
        """Same 80 % rule as ``Performance._validate_factor_coverage``."""
        main_dates = set(self._main.index)
        factor_dates = set(factor_df.index)
        missing = main_dates - factor_dates
        coverage = 1.0 - len(missing) / len(main_dates) if main_dates else 1.0
        if coverage < 0.80:
            raise ValueError(
                f"Factor '{factor_cusip}' covers only {coverage:.0%} of main product "
                f"'{self._config.internal_cusip}' dates "
                f"({len(factor_dates)} vs {len(main_dates)} trading days). "
                f"Cannot use a product with fewer trading days as a factor "
                f"for a product with more trading days."
            )


class SingleFactorObjective(Objective):
    """One indicator cache, one signal function."""

    def __init__(self, data, config, windows, *, fee_bps=None) -> None:
        super().__init__(data, config, fee_bps=fee_bps)
        sub = config.get_substrategies()[0]
        sub_cusip = sub.internal_cusip or config.internal_cusip
        if sub_cusip != config.internal_cusip:
            frame = self._main.copy()
            frame["factor"] = self._factor_series_for_sub(sub)
        else:
            # data_column is ignored on the same-cusip path — Performance does too.
            frame = self._main
        self._cache = IndicatorCache(frame, config.indicator_name, windows)
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
            factor_vals = self._factor_series_for_sub(sub)
            frame = pd.DataFrame({"factor": factor_vals})
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
