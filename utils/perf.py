import pandas as pd
import math

########################################################################################## Strategy Performance Calculations ##############################################################################################
# Define a class for performance metrics
class perf:
    
    def __init__(self,df) -> None:
        if not isinstance(df,pd.DataFrame):
            raise TypeError("self.df is not a dataframe")
        self.df = df
    
    # Define a method for calculating performance metrics
    def Perf_col(self):
        print(self.df)
        self.df['pos_xt1'] = self.df.pos.shift(1)
        self.df['pnl'] = self.df.pos_xt1 * self.df.chg
        self.df['cumu'] = self.df.pnl.cumsum()
        self.df['dd'] = self.df.cumu - self.df.cumu.cummax()
    
    # Define a method for calculating total return
    def TR(self):
        return float(self.df.cumu.tail(1))
    
    # Define a method for calculating annualized return
    def AR(self,trade_days):
        return self.df.pnl.mean() * trade_days
    
    # Define a method for calculating Sharpe ratio
    def Sharpe(self,trade_days):
        return self.df.pnl.mean() / self.df.pnl.std() * math.sqrt(trade_days)
    
    # Define a method for calculating maximum drawdown
    def MDD(self):
        return abs(min(self.df.dd))
    
    # Define a method for calculating Calmar ratio
    def Calmar(self,trade_days):
        return self.AR(trade_days) / self.MDD()