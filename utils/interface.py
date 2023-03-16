import pandas as pd

Class perf_interface:
    
    def strategy_perf_col(self,df):
        df['pos_xt1'] = df.pos.shift(1)
        df['pnl'] = df.pos_xt1* df.chg
        df['cumu'] = df.pnl.cumsum()
        df['dd'] = df.cumu - df.cumu.cummax()
        
        