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

####################################### ta for analysis

# Define a class for Technical Analysis
class ta(perf):
    
    # contructor with attributes as a pd.DataFrame and 3 columns
    # Column load list of 3 columns for analysis (i.e. datetime, value and factor)
    def __init__(self,df,col_list):
        if not isinstance(df,pd.DataFrame):
            raise TypeError("self.df is not a dataframe")
        elif len(col_list):
            raise ValueError("df column list should have a length of 3")
        self.df = df[col_list]
        self.df = self.df.rename(columns=dict(zip(self.df.columns.tolist(),["datetime","value","factor"])))
        self.df['chg'] = self.df.factor.pct_change()
        
    # Calculation for Monthly Average
    def ma(self, timeframe:float, diff:float, trade_days:int, pos = "l"):
        self.df['ma'] = self.df.factor.rolling(int(timeframe)).mean()
        
        # inner function for long-short position
        def ls_pos(row,diff):
            if row.factor - row.ma > diff:
                return 1  
            elif row.factor - row.ma < -diff:
                return -1
            else:
                return 0

        # depending on input to decide position as long or long short
        if pos == "l":
            self.df['pos'] = np.where(self.df.factor - self.df.ma > diff,1,0)
        elif pos == "ls":
            self.df['pos'] = self.df.apply(ls_pos, args = (diff,),axis = 1)
        else:
            raise Exception ("Invalid position input")
        
        self.Perf_col()
        
        return self
    
    # Function to calculate Bollinger Band and position
    # Takes timeframe, diff, trade_days, pos as inputs
    def BBand(self, timeframe:float, z:float, trade_days:int, pos = "l"):
        
        # Calculate bollinger Band
        self.df['ma'] = self.df.factor.rolling(int(timeframe)).mean()
        self.df['mstd'] = self.df.factor.rolling(int(timeframe)).std()
        self.df['zscore'] = (self.df.factor - self.df.ma)/self.df.mstd
        
        # Function to calculate the position based on monthly average difference with factor
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
    dfinstance = ta(df)
    ma = dfinstance.MA(50,0.01,365,"ls")
    bband = dfinstance.BBand(50,2,365,"ls")
    # print(dfinstance.df)
    print("Strategy sharpe:", dfinstance.Sharpe(365))
    end = time()
    print("Time: ", end - start)