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

class Performance:
    
    
    # assume that 0.05bps 
    def __init__(self, data, trading_days) -> None:
        self.data = data
        self.trading_days = trading_days
        
        # strategy daily performance
        self.data['chg'] = self.data['close'].pct_change()
        self.data['position_x1'] = self.data['position'].shift(1)
        
        # window still take account of other not leading np.nan values that will need to be fixed
        self.window = ~self.data['position_x1'].notnull().sum()  

        self.data['trade'] = abs(df['position_x1'] - df['position'])
        self.data['pnl'] = self.data['position_x1']*self.data['chg'] - self.data['trade']*0.00005
        self.data['cumu'] = self.data['pnl'].cumsum()
        self.data['dd'] = self.data['cumu'].cummax() - self.data['cumu']
        
        # buy and hold daily performance
        self.data['buy_hold'] = self.data['chg']
        position_leading_na = self.data['position_x1'].isnull()
        self.data.loc[position_leading_na, 'buy_hold'] = np.nan
        self.data['buy_hold_cumu'] = self.data['buy_hold'].cumsum()
        self.data['buy_hold_dd'] = self.data['buy_hold_cumu'].cummax() - self.data['buy_hold_cumu']
        
        
    # take account that nan leading zeros    
    def get_total_return(self):
        total_return = self.data['cumu'][-1]
        return total_return
    
    # take account that nan leading zeros
    def get_annualized_return(self):
        annualized_return = self.data.loc[self.window:len(self.data),'pnl'].mean() * self.trading_days
        
    def get_sharpe_ratio(self):
        sharpe_ratio = self.data.loc[self.window:len(self.data),'pnl'].mean() / self.data[self.window:len(self.data),'pnl'].std() * np.sqrt(self.trading_days)
        return sharpe_ratio
    
    def get_max_drawdown(self):
        max_drawdown = self.data['dd'].min()
        return max_drawdown
    
    def get_calmar_ratio(self):
        calmar_ratio = self.data.loc[self.window:len(self.data),'pnl'].mean() / abs(self.data['dd'].min())
        return calmar_ratio
    
    def get_buy_hold_total_return(self):
        total_return = self.data['buy_hold_cumu'][-1]
        return total_return
    
    def get_buy_hold_get_annualized_return(self):
        annualized_return = self.data.loc[self.window:len(self.data),'buy_hold'].mean() * self.trading_days
        return annualized_return
    
    def get_buy_hold_sharpe_ratio(self):
        sharpe_ratio = self.data.loc[self.window:len(self.data),'buy_hold'].mean() / self.data.loc[self.window:len(self.data),'buy_hold'].std() * np.sqrt(self.trading_days)
        return sharpe_ratio
    
    def get_buy_hold_max_drawdown(self):
        max_drawdown = self.data['buy_hold_dd'].min()
        return max_drawdown
    
    def get_buy_hold_calmar_ratio(self):
        calmar_ratio = self.data.loc[self.window:len(self.data),'buy_hold'].mean() / abs(self.data['buy_hold_dd'].min())
        return calmar_ratio

    

    
    