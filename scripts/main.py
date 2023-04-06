'''
Collects data from FutuOpenD and Glassnode
performs technical analysis on factors of underlying
create trading strategy on position base on technical analysis
and calculates performance metrics.
'''


from data import FutuOpenD, Glassnode
from ta import TechnicalAnalysis
from perf import Performance
import pandas as pd
import numpy as np
import time


### DATA ###

# get data from FutuOpenD
# futu_opend = FutuOpenD()
# df = futu_opend.get_historical_data('HK.00700', '2021-01-01', '2021-01-31', 'K_DAY')
# print(df)

# get data from Glassnode
glassnode = Glassnode()
price = glassnode.get_historical_price('BTC', '2020-05-11', '2021-04-03', '1h')
factor = glassnode.get_historical_price('ETH', '2020-05-11', '2021-04-03', '1h')
df = pd.merge(price, factor, how='inner', on='t')


#!!!!!!!!!!!!!!!!! ammend data with price and factor for analysis !!!!! need to amend

df.rename(columns={'t':'date', 'v_x':'price', 'v_y':'factor'}, inplace=True)



### TECHNICAL ANALYSIS ###

period = 200
signal = 2
# period1 = 12
# period2 = 26
# period3 = 9

ta = TechnicalAnalysis(df)
# ta.data['ta']= ta.get_sma(period, column='factor'))
# ta.data['ta']= ta.get_ema(period, column='factor'))
# ta.data['ta']= ta.get_rsi(period, column='factor'))
# ta.data['ta']= ta.get_macd(period1, period2, period3, column='factor'))
ta.data['ta']= ta.get_bollinger_band(period,column='factor')
# ta.data['ta']= ta.get_stochastic_oscillator(20,column='factor'))



### TRADING STRATEGY ###
ta.data['position'] = np.where(ta.data['ta'] > signal, 1, np.where(ta.data['ta'] < -signal, -1, 0))
ta.data.loc[ta.data['ta'].isna(), 'position'] = np.nan


### Perf ###

perf = Performance(ta.data,360)
print(perf.get_strategy_performance())
print(perf.get_buy_hold_performance())


















