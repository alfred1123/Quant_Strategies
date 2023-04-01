import sys
sys.path.append("./utils")

import pandas as pd
import numpy as np
import math
from perf import perf

from time import time

# Set display options for pandas dataframes
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)


########################################################################################## Price factor Strategies Calculations ##############################################################################################

# Currently include BBand and MA


# Define a class for price factor quant strategies
class price(perf):
    def __init__(self,df):
        if not isinstance(df,pd.DataFrame):
            raise TypeError("self.df is not a dataframe")
        self.df = df[df.columns[0:2]]
        self.df.columns = ["datetime","adjclose"]

    # Function to calculate Moving Average and position
    # Takes timeframe, diff, trade_days, pos as inputs
    def MA(self, timeframe:int, diff:float, trade_days:int, pos = "l"):
        
        # Select first two columns and rename them
        self.df = self.df[self.df.columns[0:2]]
        self.df = self.df.rename(columns=dict(zip(self.df.columns.tolist(),["datetime","adjclose"])))
        # Calculate change in price and Moving Average
        self.df['chg'] = self.df.adjclose.pct_change()
        self.df['ma'] = self.df.adjclose.rolling(timeframe).mean()
        
        # Function to calculate the position based on monthly average difference with adjclose
        def ls_pos(row,diff):
            if row.adjclose - row.ma > diff:
                return 1  
            elif row.adjclose - row.ma < -diff:
                return -1
            else:
                return 0
        
        
        # If position strategy for 'l'(long) and 'ls' (long-short)
        if pos == "l":
            self.df['pos'] = np.where(self.df.adjclose - self.df.ma > diff,1,0)
        elif pos == "ls":
            self.df['pos'] = self.df.apply(ls_pos, args = (diff,),axis = 1)
                
        else: 
            raise Exception("Invalid pos input")
        
        # Calculate performance columns using Perf_col function
        self.Perf_col()
        
        return self
    


    # Function to calculate Bollinger Band and position
    # Takes timeframe, diff, trade_days, pos as inputs
    def BBand(self, timeframe:int, z:float, trade_days:int, pos = "l"):
        
        # Select first two columns and rename them
        self.df = self.df[self.df.columns[0:2]]
        self.df = self.df.rename(columns=dict(zip(self.df.columns.tolist(),["datetime","adjclose"])))
        # Calculate change in price, moving average, moving standard deviation and z-score
        self.df['chg'] = self.df.adjclose.pct_change()
        self.df['ma'] = self.df.adjclose.rolling(timeframe).mean()
        self.df['mstd'] = self.df.adjclose.rolling(timeframe).std()
        self.df['zscore'] = (self.df.adjclose - self.df.ma)/self.df.mstd
        
        # Function to calculate the position based on monthly average difference with adjclose
        def ls_pos(row,z):
            if row.zscore > z:
                return 1  
            elif row.zscore < -z:
                return -1
            else:
                return 0
        
        
        # If position strategy for 'l'(long) and 'ls' (long-short)
        if pos == "l":
            self.df['pos'] = np.where(self.df.zscore > z,1,0)
        elif pos == "ls":
            self.df['pos'] = self.df.apply(ls_pos, args = (z,),axis = 1)
                
        else: 
            raise Exception("Invalid pos input")
        
        # Calculate performance columns using Perf_col function
        self.Perf_col()
        
        return self


if __name__ == "__main__":
    start = time()
    df = pd.read_excel("data/processed/btcusd_20200510_20230310.xlsx")
    dfinstance = price(df)
    ma = dfinstance.MA(50,0.01,365,"ls")
    bband = dfinstance.BBand(50,2,365,"ls")
    # print(dfinstance.df)
    print("Strategy sharpe:", dfinstance.Sharpe(365))
    end = time()
    print("Time: ", end - start)
