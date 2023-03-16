import pandas as pd
import numpy as np
import math
from time import time

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

class price():
    def __init__(self,df):
        if not isinstance(df,pd.DataFrame):
            raise TypeError("self.df is not a dataframe")
        self.df = df[df.columns[0:2]]
        self.df.columns = ["datetime","adjclose"]



    def MA(self, timeframe:int, diff:float, trade_days:int, pos = "l"):

        self.df = self.df[self.df.columns[0:2]]
        self.df.columns = ["datetime","adjclose"]
        self.df['chg'] = self.df.adjclose.pct_change()
        self.df['ma'] = self.df.adjclose.rolling(timeframe).mean()
        
        def ls_pos(diff):
            return 1 if self.df.adjclose - self.df.ma > diff else -1 if self.df.col[1] - self.df.ma < -diff else 0
            
        if pos == "l":
            self.df['pos'] = np.where(self.df.adjclose - self.df.ma > diff,1,0)
        elif pos == "ls":
            self.df['pos'] = np.vectorize(ls_pos) 
        else: 
            raise Exception("Invalid pos input")
        
        
        self.df['pos_xt1'] = self.df.pos.shift(1)
        self.df['pnl'] = self.df.pos_xt1* self.df.chg
        self.df['cumu'] = self.df.pnl.cumsum()
        self.df['dd'] = self.df.cumu - self.df.cumu.cummax()
        return self.df

# TR = float(self.df.cumu.tail(1))
# AR = self.df.pnl.mean()*365
# Sharpe = self.df.pnl.mean()*365*math.sqrt(trade_days)
# MDD = abs(min(self.df.dd))
# Calmar = AR/MDD

start = time()
df = pd.read_excel("data/processed/btcusd_20200510_20230310.xlsx")
dfinstance = price(df)
ma = dfinstance.MA(50,0.01,365,"ls")
print(ma)
end = time()
print(end - start)
