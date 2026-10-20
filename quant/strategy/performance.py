'''
This file aims to give performance by different metrics of the trading strategy based on the technical analysis indicators
for different factors of stocks.
The metrics include:
1. Total Return
2. Annualized Return
3. Sharpe Ratio
4. Max Drawdown
5. Calmar Ratio
'''

import logging

import pandas as pd
import numpy as np

from quant.strategy.indicators import TechnicalAnalysis
from quant.strategy.signals import StrategyConfig, combine_positions

logger = logging.getLogger(__name__)


def _max_window(window) -> int:
    """Largest indicator window in a scalar or per-substrategy collection."""
    if isinstance(window, (tuple, list)):
        return max(int(w) for w in window)
    return int(window)


def live_lookback_days(max_window: int, trading_period: int) -> int:
    """Calendar days of history to fetch so indicators are valid on the latest bar."""
    return max(max_window * 3 + 60, min(trading_period, 400))


def live_lookback_bars(window) -> int:
    """Bars of history to fetch so indicators are valid on the latest bar.

    The bar-indexed twin of :func:`live_lookback_days`, for sources addressed
    by interval rather than by date. It drops that function's
    ``min(trading_period, 400)`` floor: the floor buys roughly a year of daily
    history to survive weekends and holidays, which is meaningless when every
    element of the window is one bar of the interval being traded.
    """
    return _max_window(window) * 3 + 60


def live_date_range(window, trading_period: int) -> tuple[str, str]:
    """ISO ``(start, end)`` for live position evaluation ending today."""
    from datetime import date, timedelta

    days = live_lookback_days(_max_window(window), trading_period)
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _compound(pnl: pd.Series) -> tuple[pd.Series, pd.Series]:
    """``(cumulative_return, drawdown)`` from a per-bar **simple** return series.

    Simple returns compound multiplicatively — ``cumsum`` is additive and is
    only valid for log returns. Drawdown is read off the equity curve, which
    bounds it to ``[0, 1]`` instead of the unbounded ``cummax - cumu``.

    The lower clip floors a ruined position at zero equity, so a short that
    loses more than 100% on one bar stays wiped out rather than flipping the
    sign of every later bar. The peak is anchored at the starting capital of
    ``1.0`` because ``cummax`` alone omits it, which would report no drawdown
    for a strategy that is underwater from the first bar.
    """
    equity = (1.0 + pnl).clip(lower=0.0).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    return equity - 1.0, 1.0 - equity / peak


def _cagr(pnl: pd.Series, trading_period: int) -> float:
    """Geometric annualised return from a per-bar **simple** return series.

    The constant per-bar rate that reproduces realised growth over the series.
    An arithmetic ``mean * trading_period`` annualises an average the capital
    never actually earned, and overstates whenever returns vary.
    """
    n = int(pnl.notna().sum())
    if n == 0:
        return np.nan
    equity = float((1.0 + pnl).clip(lower=0.0).prod())
    return equity ** (trading_period / n) - 1.0


def _latest_final_position(final_position: pd.Series) -> tuple[float, str]:
    """Return ``(position, data_as_of)`` from a ``FinalPosition`` series."""
    if not isinstance(final_position, pd.Series):
        final_position = pd.Series(final_position)
    series = final_position.dropna()
    if series.empty:
        raise ValueError("insufficient data to compute signal")
    return float(series.iloc[-1]), str(series.index[-1])


def strategy_pnl(
    position: np.ndarray, chg: np.ndarray, transaction_cost: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(prior_position, turnover, pnl)`` per bar, from a position series.

    The bar's return accrues to the position held *entering* it. A fee is
    charged only on a change between two **known** positions: a missing prior
    is not a trade — the series is still warming up, or a gap just ended —
    and a missing current position has no PnL at all. ``Performance`` writes
    these as columns and ``Objective`` reduces them to one Sharpe; both must
    read the same rule, which is why it lives here once.
    """
    pos = np.asarray(position, dtype=float)
    prior = np.empty_like(pos)
    prior[0] = np.nan
    prior[1:] = pos[:-1]
    both_known = ~np.isnan(pos) & ~np.isnan(prior)
    turnover = np.where(both_known, np.abs(pos - prior), 0.0)
    turnover = np.where(np.isnan(pos), np.nan, turnover)
    pnl = prior * np.asarray(chg, dtype=float) - turnover * transaction_cost
    return prior, turnover, pnl


def sharpe_ratio(pnl, trading_period: int, *, min_obs: int) -> float:
    """Annualised Sharpe of a per-bar return series, or ``nan`` when undefined.

    Undefined below ``min_obs`` finite bars — ``mean * period`` over a lucky
    week is not a Sharpe (decision #63) — and when the return has no spread.
    Sample standard deviation (``ddof=1``), the pandas default the metric
    was first written with.
    """
    finite = np.asarray(pnl, dtype=float)
    finite = finite[~np.isnan(finite)]
    if finite.size < min_obs:
        logger.debug("Sharpe undefined (%d finite bars, need %d)", finite.size, min_obs)
        return np.nan
    std = finite.std(ddof=1)
    if std == 0 or np.isnan(std):
        logger.debug("Sharpe undefined (zero or NaN std)")
        return np.nan
    return float(finite.mean() / std * np.sqrt(trading_period))


class FactorFrames:
    """The series a strategy reads, resolved the same way for every engine.

    A substrategy's factor may come from the traded product's own frame or
    from another product's. Which frame, how it is aligned, and when another
    product is too sparse to be a factor are one set of rules; backtest
    (``Performance``) and search (``Objective``) both read them from here
    rather than carrying a copy each.
    """

    # A factor with fewer trading days than the main product (a 252-day equity
    # factor on a 365-day crypto product) leaves NaN gaps after ``reindex``
    # that make the indicator unreliable. Below this share of main dates
    # covered, the factor is refused.
    MIN_COVERAGE = 0.80

    def __init__(self, all_data: dict, config) -> None:
        self._all = all_data
        self._config = config
        self.main = all_data[config.internal_cusip]

    def factor(self, sub) -> pd.Series:
        """``sub``'s factor column, aligned to the traded product's index."""
        sub_cusip = sub.internal_cusip or self._config.internal_cusip
        sub_df = self._all[sub_cusip]
        if sub_cusip != self._config.internal_cusip:
            self._require_coverage(sub_df, sub_cusip)
        return sub_df[sub.data_column].reindex(self.main.index)

    def single_factor_frame(self) -> pd.DataFrame:
        """A copy of the main frame whose ``factor`` column is the one substrategy's.

        The main frame already carries a ``factor`` column when the product's
        own price is the factor. It is replaced only when the substrategy
        reads another product, or names a column the main frame has — the
        same product's volume, say.
        """
        sub = self._config.get_substrategies()[0]
        sub_cusip = sub.internal_cusip or self._config.internal_cusip
        frame = self.main.copy()
        if sub_cusip != self._config.internal_cusip or sub.data_column in self._all[sub_cusip].columns:
            frame["factor"] = self.factor(sub)
        return frame

    def _require_coverage(self, factor_df: pd.DataFrame, factor_cusip: str) -> None:
        main_dates = set(self.main.index)
        factor_dates = set(factor_df.index)
        missing = main_dates - factor_dates
        coverage = 1.0 - len(missing) / len(main_dates) if main_dates else 1.0
        if coverage < self.MIN_COVERAGE:
            raise ValueError(
                f"Factor '{factor_cusip}' covers only {coverage:.0%} of main product "
                f"'{self._config.internal_cusip}' dates "
                f"({len(factor_dates)} vs {len(main_dates)} trading days). "
                f"Cannot use a product with fewer trading days as a factor "
                f"for a product with more trading days."
            )


class Performance:

    DEFAULT_FEE_BPS = 10.0  # Bybit VIP-0 spot taker; per unit of turnover
    # Below this many finite PnL bars, mean * period is a lucky week, not a Sharpe
    # (decision #63). Owned here — optimizer maps non-finite Sharpe to -inf.
    MIN_METRIC_OBS = 60

    def __init__(self, data, config, window=None, signal=None, *, fee_bps=None) -> None:
        self.config = config
        self.trading_period = config.trading_period
        self.fee_bps = fee_bps if fee_bps is not None else self.DEFAULT_FEE_BPS
        self.transaction_cost = self.fee_bps / 10_000  # bps → decimal

        self._subs = config.get_substrategies()
        self._is_multi = len(self._subs) > 1

        self.all_data = data
        self._frames = FactorFrames(data, config)
        self.data = self._frames.main.copy()

        if window is not None and signal is not None:
            # Legacy/grid-search caller: window/signal passed explicitly
            self.window = window
            self.signal = signal
            if self._is_multi:
                self._windows = window if isinstance(window, tuple) else (window,) * len(self._subs)
                self._signals = signal if isinstance(signal, tuple) else (signal,) * len(self._subs)
            else:
                self._windows = (window,)
                self._signals = (signal,)
        else:
            # Read from config substrategies — the proper path
            self._windows = tuple(s.window for s in self._subs)
            self._signals = tuple(s.signal for s in self._subs)
            self.window = self._windows if self._is_multi else self._windows[0]
            self.signal = self._signals if self._is_multi else self._signals[0]

        self._metric_window = max(self._windows)

        logger.debug("Performance init: window=%s, signal=%s, "
                     "trading_period=%s, fee_bps=%s, multi_factor=%s",
                     self.window, self.signal, config.trading_period,
                     self.fee_bps, self._is_multi)

    def _trade_enrich_positions(self):
        """Compute indicators and ``FinalPosition`` only — no PnL / metrics columns."""
        if self._is_multi:
            self._enrich_multi_factor()
        else:
            self._enrich_single_factor()
        return self

    def enrich_performance(self):
        """Compute indicators, positions, and PnL columns."""
        self._trade_enrich_positions()
        self._compute_pnl_columns()
        return self

    def compute_latest_position(self) -> tuple[float, str]:
        """Latest ``FinalPosition`` using the same math as backtest enrichment."""
        if self._is_multi:
            _, _, final_position = self._compute_multi_factor_outputs()
        else:
            _, final_position = self._compute_single_factor_outputs()
        return _latest_final_position(final_position)

    def _trade_latest_final_position(self) -> tuple[float, str]:
        """Return ``(position, data_as_of)`` after :meth:`_trade_enrich_positions`."""
        return _latest_final_position(self.data["FinalPosition"])

    def _indicator_and_position(
        self,
        sub,
        factor_vals: pd.Series,
        window: int,
        signal: float,
    ) -> tuple[pd.Series, pd.Series]:
        ta = TechnicalAnalysis(pd.DataFrame({"factor": factor_vals}))
        indicator_vals = ta.indicator(sub.indicator_name, window)
        pos = sub.resolve_signal_func()(indicator_vals, signal)
        return indicator_vals, pos

    def _compute_single_factor_outputs(self) -> tuple[pd.DataFrame, pd.Series]:
        """Shared single-factor indicator → position math (backtest + trade)."""
        data = self._frames.single_factor_frame()
        ta = TechnicalAnalysis(data)
        data["factor1"] = data["factor"]
        data["indicator1"] = ta.indicator(self.config.indicator_name, self._windows[0])
        data["position1"] = self.config.signal_func(
            data["indicator1"], self._signals[0],
        )
        return data, data["position1"]

    def _compute_multi_factor_outputs(
        self,
    ) -> tuple[pd.DataFrame, list[tuple[pd.Series, pd.Series, pd.Series]], pd.Series]:
        """Shared multi-factor indicator → position math (backtest + trade)."""
        data = TechnicalAnalysis(self.data.copy()).data
        positions = []
        factor_outputs: list[tuple[pd.Series, pd.Series, pd.Series]] = []
        for i, sub in enumerate(self._subs):
            factor_vals = self._frames.factor(sub)
            indicator_vals, pos = self._indicator_and_position(
                sub, factor_vals, self._windows[i], self._signals[i],
            )
            factor_outputs.append((factor_vals, indicator_vals, pos))
            positions.append(pos)

        indicator_strengths = [indicator_vals.values for _, indicator_vals, _ in factor_outputs]
        combined = combine_positions(
            positions, self.config.conjunction, strengths=indicator_strengths,
        )
        final_position = pd.Series(combined, index=data.index)
        return data, factor_outputs, final_position

    def _enrich_single_factor(self):
        data, final_position = self._compute_single_factor_outputs()
        self.data = data
        self.data["chg"] = self.data["price"].pct_change()
        self.data["FinalPosition"] = final_position

    def _enrich_multi_factor(self):
        data, factor_outputs, final_position = self._compute_multi_factor_outputs()
        self.data = data
        self.data["chg"] = self.data["price"].pct_change()
        for i, (factor_vals, indicator_vals, pos) in enumerate(factor_outputs, start=1):
            self.data[f"factor{i}"] = factor_vals
            self.data[f"indicator{i}"] = indicator_vals
            self.data[f"position{i}"] = pos
        self.data["FinalPosition"] = final_position

    def _compute_pnl_columns(self):
        prior, turnover, pnl = strategy_pnl(
            self.data['FinalPosition'].to_numpy(),
            self.data['chg'].to_numpy(),
            self.transaction_cost,
        )
        self.data['FinalPosition_x1'] = prior
        self.data['trade'] = turnover
        self.data['pnl'] = pnl
        self.data['cumu'], self.data['dd'] = _compound(self.data['pnl'])

        self.data['buy_hold'] = self.data['chg']
        self.data.loc[self.data['FinalPosition_x1'].isna(), 'buy_hold'] = np.nan
        self.data['buy_hold_cumu'], self.data['buy_hold_dd'] = _compound(self.data['buy_hold'])


    def _metric_col(self, col: str) -> pd.Series:
        """PnL / buy-hold slice after indicator warmup."""
        return self.data.iloc[self._metric_window:][col]

    def get_metric_n_obs(self) -> int:
        """Finite strategy-PnL observations after indicator warmup."""
        if "pnl" not in self.data.columns:
            return 0
        return int(self._metric_col("pnl").notna().sum())

    # take account that nan leading zeros
    def get_total_return(self):
        total_return = self.data['cumu'].iloc[-1]
        return total_return

    # take account that nan leading zeros
    def get_annualized_return(self):
        n = self.get_metric_n_obs()
        if n < self.MIN_METRIC_OBS:
            logger.debug("Annualized return undefined (%d finite pnl bars, need %d)",
                         n, self.MIN_METRIC_OBS)
            return np.nan
        return _cagr(self._metric_col("pnl"), self.trading_period)

    def get_sharpe_ratio(self):
        return sharpe_ratio(
            self._metric_col("pnl"), self.trading_period, min_obs=self.MIN_METRIC_OBS,
        )

    def get_max_drawdown(self):
        max_drawdown = self.data['dd'].max()
        return max_drawdown

    def get_calmar_ratio(self):
        max_dd = self.get_max_drawdown()
        if max_dd == 0 or np.isnan(max_dd):
            logger.debug("Calmar ratio undefined (zero or NaN max drawdown)")
            return np.nan
        calmar_ratio = self.get_annualized_return() / max_dd
        return calmar_ratio

    def get_buy_hold_total_return(self):
        total_return = self.data['buy_hold_cumu'].iloc[-1]
        return total_return

    def get_buy_hold_annualized_return(self):
        n = self.get_metric_n_obs()
        if n < self.MIN_METRIC_OBS:
            logger.debug("Buy-hold annualized return undefined (%d finite pnl bars, need %d)",
                         n, self.MIN_METRIC_OBS)
            return np.nan
        return _cagr(self._metric_col("buy_hold"), self.trading_period)

    def get_buy_hold_sharpe_ratio(self):
        return sharpe_ratio(
            self._metric_col("buy_hold"), self.trading_period, min_obs=self.MIN_METRIC_OBS,
        )

    def get_buy_hold_max_drawdown(self):
        max_drawdown = self.data['buy_hold_dd'].max()
        return max_drawdown

    def get_buy_hold_calmar_ratio(self):
        max_dd = self.get_buy_hold_max_drawdown()
        if max_dd == 0 or np.isnan(max_dd):
            logger.debug("Buy-hold Calmar ratio undefined (zero or NaN max drawdown)")
            return np.nan
        calmar_ratio = self.get_buy_hold_annualized_return() / max_dd
        return calmar_ratio

    def get_strategy_performance(self):
        strategy_performance = pd.Series([self.get_total_return(),
                                        self.get_annualized_return(),
                                        self.get_sharpe_ratio(),
                                        self.get_max_drawdown(),
                                        self.get_calmar_ratio()
        ], index=['Total Return', 'Annualized Return', 'Sharpe Ratio', 'Max Drawdown', 'Calmar Ratio'])
        return strategy_performance

    def get_buy_hold_performance(self):
        buy_hold_performance = pd.Series([self.get_buy_hold_total_return(),
                                          self.get_buy_hold_annualized_return(),
                                          self.get_buy_hold_sharpe_ratio(),
                                          self.get_buy_hold_max_drawdown(),
                                          self.get_buy_hold_calmar_ratio()
        ], index=['Total Return', 'Annualized Return', 'Sharpe Ratio', 'Max Drawdown', 'Calmar Ratio'])
        return buy_hold_performance


