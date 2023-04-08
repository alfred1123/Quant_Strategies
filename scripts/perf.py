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

import pandas as pd
import numpy as np
import time

class Performance:
    
    
    # assume that 0.05bps 
    def __init__(self, data, trading_periods, indicator_func, strategy_func, mv_period, signal) -> None:
        self.data = data
        self.trading_periods = trading_periods
        self.indicator_func = indicator_func
        self.strategy_func = strategy_func
        self.mv_period = mv_period
        self.signal = signal
        
        # strategy daily performance
        self.data['chg'] = self.data['price'].pct_change()
        self.data['indicator'] = self.indicator_func(self.mv_period)
        self.data['position'] = self.strategy_func(self.data['indicator'], self.signal)
        self.data['position_x1'] = self.data['position'].shift(1)
        
        # window still take account of other not leading np.nan values that will need to be fixed
        self.window = self.data['position_x1'].isnull().sum()  

        self.data['trade'] = abs(self.data['position_x1'] - self.data['position'])
        self.data['pnl'] = self.data['position_x1']*self.data['chg'] - self.data['trade']*0.00005
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
        annualized_return = self.data.loc[self.window:len(self.data)-1,'pnl'].mean() * self.trading_periods
        return annualized_return
        
    def get_sharpe_ratio(self):
        sharpe_ratio = self.data.loc[self.window:len(self.data)-1,'pnl'].mean() / self.data.loc[self.window:len(self.data)-1,'pnl'].std() * np.sqrt(self.trading_periods)
        return sharpe_ratio
    
    def get_max_drawdown(self):
        max_drawdown = self.data['dd'].max()
        return max_drawdown
    
    def get_calmar_ratio(self):
        calmar_ratio = self.data.loc[self.window:len(self.data)-1,'pnl'].mean() / self.data['dd'].max()
        return calmar_ratio
    
    def get_buy_hold_total_return(self):
        total_return = self.data['buy_hold_cumu'].iloc[-1]
        return total_return
    
    def get_buy_hold_get_annualized_return(self):
        annualized_return = self.data.loc[self.window:len(self.data)-1,'buy_hold'].mean() * self.trading_periods
        return annualized_return
    
    def get_buy_hold_sharpe_ratio(self):
        sharpe_ratio = self.data.loc[self.window:len(self.data)-1,'buy_hold'].mean() / self.data.loc[self.window:len(self.data)-1,'buy_hold'].std() * np.sqrt(self.trading_periods)
        return sharpe_ratio
    
    def get_buy_hold_max_drawdown(self):
        max_drawdown = self.data['buy_hold_dd'].max()
        return max_drawdown
    
    def get_buy_hold_calmar_ratio(self):
        calmar_ratio = self.data.loc[self.window:len(self.data)-1,'buy_hold'].mean() / self.data['buy_hold_dd'].max()
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
                                          self.get_buy_hold_get_annualized_return(),
                                          self.get_buy_hold_sharpe_ratio(),
                                          self.get_buy_hold_max_drawdown(),
                                          self.get_buy_hold_calmar_ratio()
        ], index=['Total Return', 'Annualized Return', 'Sharpe Ratio', 'Max Drawdown', 'Calmar Ratio'])
        return buy_hold_performance
                                          
                                        
    
    

    

    
    