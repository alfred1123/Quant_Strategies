import pandas as pd
import numpy as np

class perf:
    
    def perf_col(self,df):
        df['pos_xt1'] = df.pos.shift(1)
        df['pnl'] = df.pos_xt1* df.chg
        df['cumu'] = df.pnl.cumsum()
        df['dd'] = df.cumu - df.cumu.cummax()
        
        
        
    def TR(self,df):
        return float(self.df.cumu.tail(1))
    
    def AR(self,df):
        return self.df.pnl.mean()*365
    
    def Sharpe(self,df):
        return self.df.pnl.mean()*365*math.sqrt(trade_days)
    
    def MDD(self,df):
        return abs(min(self.df.dd))
    
    def Calmar(self,df):
        return self.AR(df)/self.MDD(df)