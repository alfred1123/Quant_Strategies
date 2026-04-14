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

from strat import TechnicalAnalysis, StrategyConfig, combine_positions

logger = logging.getLogger(__name__)


class Performance:
    
    
    DEFAULT_FEE_BPS = 5.0  # 5 bps (0.05%) transaction cost per unit of turnover

    def __init__(self, data, config, window=None, signal=None, *, fee_bps=None) -> None:
        self.config = config
        self.trading_period = config.trading_period
        self.fee_bps = fee_bps if fee_bps is not None else self.DEFAULT_FEE_BPS
        self.transaction_cost = self.fee_bps / 10_000  # bps → decimal

        self._subs = config.get_substrategies()
        self._is_multi = len(self._subs) > 1

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
        self.data = data

        logger.debug("Performance init: window=%s, signal=%s, "
                     "trading_period=%s, fee_bps=%s, multi_factor=%s",
                     self.window, self.signal, config.trading_period,
                     self.fee_bps, self._is_multi)

    def enrich_performance(self):
        """Compute indicators, positions, and PnL columns.

        Dispatches to single-factor or multi-factor path based on config.
        Returns self for optional call chaining.
        """
        if self._is_multi:
            self._enrich_multi_factor()
        else:
            self._enrich_single_factor()
        self._compute_pnl_columns()
        return self

    def _enrich_single_factor(self):
        ta = TechnicalAnalysis(self.data)
        self.data = ta.data
        self.indicator_func = getattr(ta, self.config.indicator_name)
        self.data['chg'] = self.data['price'].pct_change()
        self.data['factor1'] = self.data['factor']
        self.data['indicator1'] = self.indicator_func(self._windows[0])
        self.data['position1'] = self.config.signal_func(
            self.data['indicator1'], self._signals[0])
        self.data['FinalPosition'] = self.data['position1']

    def _enrich_multi_factor(self):
        ta_base = TechnicalAnalysis(self.data.copy())
        self.data = ta_base.data
        self.indicator_func = getattr(ta_base, self._subs[0].indicator_name)
        self.data['chg'] = self.data['price'].pct_change()

        positions = []
        for i, sub in enumerate(self._subs):
            idx = i + 1
            # Per-factor column: factorN from the sub's data_column
            self.data[f'factor{idx}'] = self.data[sub.data_column]
            # Build a TA instance on this factor's data
            cols = list(dict.fromkeys(['price', 'factor', sub.data_column]))
            sub_data = self.data[cols].copy()
            sub_data['factor'] = self.data[sub.data_column]
            ta = TechnicalAnalysis(sub_data)
            indicator_func = getattr(ta, sub.indicator_name)
            indicator_vals = indicator_func(self._windows[i])
            # Reindex to match self.data — some indicators (e.g. RSI) drop rows
            indicator_vals = indicator_vals.reindex(self.data.index)
            signal_func = sub.resolve_signal_func()
            pos = signal_func(indicator_vals, self._signals[i])

            self.data[f'indicator{idx}'] = indicator_vals
            self.data[f'position{idx}'] = pos
            positions.append(pos)

        indicator_strengths = [self.data[f'indicator{i+1}'].values
                               for i in range(len(self._subs))]
        combined = combine_positions(positions, self.config.conjunction,
                                     strengths=indicator_strengths)
        self.data['FinalPosition'] = combined

    def _compute_pnl_columns(self):
        self.data['FinalPosition_x1'] = self.data['FinalPosition'].shift(1)
        self.data['trade'] = abs(self.data['FinalPosition'] - self.data['FinalPosition_x1'])
        self.data['pnl'] = (self.data['FinalPosition_x1'] * self.data['chg']
                            - self.data['trade'] * self.transaction_cost)
        self.data['cumu'] = self.data['pnl'].cumsum()
        self.data['dd'] = self.data['cumu'].cummax() - self.data['cumu']

        self.data['buy_hold'] = self.data['chg']
        self.data.loc[self.data['FinalPosition_x1'].isnull(), 'buy_hold'] = np.nan
        self.data['buy_hold_cumu'] = self.data['buy_hold'].cumsum()
        self.data['buy_hold_dd'] = (self.data['buy_hold_cumu'].cummax()
                                    - self.data['buy_hold_cumu'])
    
        
    # take account that nan leading zeros    
    def get_total_return(self):
        total_return = self.data['cumu'].iloc[-1]
        return total_return
    
    # take account that nan leading zeros
    def get_annualized_return(self):
        annualized_return = self.data.loc[self._metric_window:len(self.data)-1,'pnl'].mean() * self.trading_period
        return annualized_return
        
    def get_sharpe_ratio(self):
        pnl = self.data.loc[self._metric_window:len(self.data)-1, 'pnl']
        std = pnl.std()
        if std == 0 or np.isnan(std):
            logger.debug("Sharpe ratio undefined (zero or NaN std for pnl)")
            return np.nan
        sharpe_ratio = pnl.mean() / std * np.sqrt(self.trading_period)
        return sharpe_ratio
    
    def get_max_drawdown(self):
        max_drawdown = self.data['dd'].max()
        return max_drawdown
    
    def get_calmar_ratio(self):
        max_dd = self.data['dd'].max()
        if max_dd == 0 or np.isnan(max_dd):
            logger.debug("Calmar ratio undefined (zero or NaN max drawdown)")
            return np.nan
        calmar_ratio = self.data.loc[self._metric_window:len(self.data)-1,'pnl'].mean() / max_dd
        return calmar_ratio
    
    def get_buy_hold_total_return(self):
        total_return = self.data['buy_hold_cumu'].iloc[-1]
        return total_return
    
    def get_buy_hold_annualized_return(self):
        annualized_return = self.data.loc[self._metric_window:len(self.data)-1,'buy_hold'].mean() * self.trading_period
        return annualized_return
    
    def get_buy_hold_sharpe_ratio(self):
        bh = self.data.loc[self._metric_window:len(self.data)-1, 'buy_hold']
        std = bh.std()
        if std == 0 or np.isnan(std):
            logger.debug("Buy-hold Sharpe ratio undefined (zero or NaN std)")
            return np.nan
        sharpe_ratio = bh.mean() / std * np.sqrt(self.trading_period)
        return sharpe_ratio
    
    def get_buy_hold_max_drawdown(self):
        max_drawdown = self.data['buy_hold_dd'].max()
        return max_drawdown
    
    def get_buy_hold_calmar_ratio(self):
        max_dd = self.data['buy_hold_dd'].max()
        if max_dd == 0 or np.isnan(max_dd):
            logger.debug("Buy-hold Calmar ratio undefined (zero or NaN max drawdown)")
            return np.nan
        calmar_ratio = self.data.loc[self._metric_window:len(self.data)-1,'buy_hold'].mean() / max_dd
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
                                          
                                        
    
    

    

    
    