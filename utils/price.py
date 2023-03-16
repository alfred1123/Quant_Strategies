import pandas as pd
import numpy as np
import math
from time import time
from perf import perf

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

class price(perf):
    def __init__(self,df):
        if not isinstance(df,pd.DataFrame):
            raise TypeError("self.df is not a dataframe")
        self.df = df[df.columns[0:2]]
        self.df.columns = ["datetime","adjclose"]


    def MA(self, timeframe:int, diff:float, trade_days:int, pos = "l"):

        self.df = self.df[self.df.columns[0:2]]
        self.df = self.df.rename(columns=dict(zip(df.columns.tolist(),["datetime","adjclose"])))
        self.df['chg'] = self.df.adjclose.pct_change()
        self.df['ma'] = self.df.adjclose.rolling(timeframe).mean()
        
        def ls_pos(row,diff):
            print(row)
            if row.adjclose - row.ma > diff:
                return 1  
            elif row.adjclose - row.ma < -diff:
                return -1
            else:
                return 0
            
        if pos == "l":
            self.df['pos'] = np.where(self.df.adjclose - self.df.ma > diff,1,0)
        elif pos == "ls":
            self.df['pos'] = self.df.apply(ls_pos, args = (diff,),axis = 1)
        #     for i in range(len(df)):
        #         if df.adjclose - df.ma > diff:
        #             df.loc[i,'pos'] = 1
        #         if df.adjclose - df.ma < diff:
        #             df.loc[i,'pos'] = -1
        #         else:
        #             df.loc[i,'pos'] = 0
                
        else: 
            raise Exception("Invalid pos input")
        
        super().perf_col(self.df)
        
        
        # self.df['pos_xt1'] = self.df.pos.shift(1)
        # self.df['pnl'] = self.df.pos_xt1* self.df.chg
        # self.df['cumu'] = self.df.pnl.cumsum()
        # self.df['dd'] = self.df.cumu - self.df.cumu.cummax()
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
