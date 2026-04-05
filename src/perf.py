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

from strat import TechnicalAnalysis, StrategyConfig

logger = logging.getLogger(__name__)


class Performance:
    
    
    DEFAULT_FEE_BPS = 5.0  # 5 bps (0.05%) transaction cost per unit of turnover

    def __init__(self, data, config, window, signal, *, fee_bps=None) -> None:
        ta = TechnicalAnalysis(data)
        self.data = ta.data
        self.config = config
        self.trading_period = config.trading_period
        self.indicator_func = getattr(ta, config.indicator_name)
        self.window = window
        self.signal = signal
        self.fee_bps = fee_bps if fee_bps is not None else self.DEFAULT_FEE_BPS
        self.transaction_cost = self.fee_bps / 10_000  # bps → decimal

        logger.debug("Computing performance: window=%s, signal=%s, "
                     "trading_period=%s, fee_bps=%s",
                     window, signal, config.trading_period, self.fee_bps)

        self.enrich_performance()
        
    def enrich_performance(self):
        # strategy daily performance
        self.data['chg'] = self.data['price'].pct_change()
        self.data['indicator'] = self.indicator_func(self.window) # look back window
        self.data['position'] = self.config.signal_func(self.data['indicator'], self.signal) # need insert relation logic
        self.data['position_x1'] = self.data['position'].shift(1)  

        self.data['trade'] = abs(self.data['position'] - self.data['position_x1'])
        self.data['pnl'] = self.data['position_x1']*self.data['chg'] - self.data['trade']*self.transaction_cost
        self.data['cumu'] = self.data['pnl'].cumsum()
        self.data['dd'] = self.data['cumu'].cummax() - self.data['cumu']
        
        # buy and hold daily performance
        self.data['buy_hold'] = self.data['chg']
        self.data.loc[self.data['position_x1'].isnull(), 'buy_hold'] = np.nan
        self.data['buy_hold_cumu'] = self.data['buy_hold'].cumsum()
        self.data['buy_hold_dd'] = self.data['buy_hold_cumu'].cummax() - self.data['buy_hold_cumu']
    
        
    # take account that nan leading zeros    
    def get_total_return(self):
        total_return = self.data['cumu'].iloc[-1]
        return total_return
    
    # take account that nan leading zeros
    def get_annualized_return(self):
        annualized_return = self.data.loc[self.window:len(self.data)-1,'pnl'].mean() * self.trading_period
        return annualized_return
        
    def get_sharpe_ratio(self):
        pnl = self.data.loc[self.window:len(self.data)-1, 'pnl']
        std = pnl.std()
        if std == 0 or np.isnan(std):
            logger.warning("Sharpe ratio undefined (zero or NaN std for pnl)")
            return np.nan
        sharpe_ratio = pnl.mean() / std * np.sqrt(self.trading_period)
        return sharpe_ratio
    
    def get_max_drawdown(self):
        max_drawdown = self.data['dd'].max()
        return max_drawdown
    
    def get_calmar_ratio(self):
        max_dd = self.data['dd'].max()
        if max_dd == 0 or np.isnan(max_dd):
            logger.warning("Calmar ratio undefined (zero or NaN max drawdown)")
            return np.nan
        calmar_ratio = self.data.loc[self.window:len(self.data)-1,'pnl'].mean() / max_dd
        return calmar_ratio
    
    def get_buy_hold_total_return(self):
        total_return = self.data['buy_hold_cumu'].iloc[-1]
        return total_return
    
    def get_buy_hold_annualized_return(self):
        annualized_return = self.data.loc[self.window:len(self.data)-1,'buy_hold'].mean() * self.trading_period
        return annualized_return
    
    def get_buy_hold_sharpe_ratio(self):
        bh = self.data.loc[self.window:len(self.data)-1, 'buy_hold']
        std = bh.std()
        if std == 0 or np.isnan(std):
            logger.warning("Buy-hold Sharpe ratio undefined (zero or NaN std)")
            return np.nan
        sharpe_ratio = bh.mean() / std * np.sqrt(self.trading_period)
        return sharpe_ratio
    
    def get_buy_hold_max_drawdown(self):
        max_drawdown = self.data['buy_hold_dd'].max()
        return max_drawdown
    
    def get_buy_hold_calmar_ratio(self):
        max_dd = self.data['buy_hold_dd'].max()
        if max_dd == 0 or np.isnan(max_dd):
            logger.warning("Buy-hold Calmar ratio undefined (zero or NaN max drawdown)")
            return np.nan
        calmar_ratio = self.data.loc[self.window:len(self.data)-1,'buy_hold'].mean() / max_dd
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
                                          
                                        
    
    

    

    
    