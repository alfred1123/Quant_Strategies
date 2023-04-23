'''
Collects data from FutuOpenD and Glassnode
performs technical analysis on factors of underlying
create trading strategy on position base on technical analysis
and calculates performance metrics.
'''


from data import FutuOpenD, Glassnode
from ta import TechnicalAnalysis
from perf import Performance
from param_opt import ParametersOptimization
from strat import Strategy
import pandas as pd
import numpy as np
import time
import matplotlib.pyplot as plt
import plotly.express as px
import seaborn as sns

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)


start = time.time()
### DATA ###

# get data from FutuOpenD
# futu_opend = FutuOpenD()
# df = futu_opend.get_historical_data('HK.00700', '2021-01-01', '2021-01-31', 'K_DAY')
# print(df)

# get data from Glassnode
# resolution = '1h' # 1month, 1w, 24h, 1h, 10m
glassnode = Glassnode()
price = glassnode.get_historical_price('BTC', '2020-05-11', '2023-04-22', '10m')
factor = glassnode.get_historical_price('BTC', '2020-05-11', '2023-04-22', '10m')
df = pd.merge(price, factor, how='inner', on='t')
print(df)


#!!!!!!!!!!!!!!!!! ammend data with price and factor for analysis !!!!! need to amend

df.rename(columns={'t':'datetime', 'v_x':'price', 'v_y':'factor'}, inplace=True)



### TECHNICAL ANALYSIS ###

# Think about do we need to load data to ta or only as an interface or static menthod
trading_period = 365*24*6
period = 10
signal = 1

# already change to 'indicator' in ta.py (left as reference)
ta = TechnicalAnalysis(df)
# ta.data['indicator']= ta.get_sma(period)
# ta.data['indicator']= ta.get_ema(period)
# ta.data['indicator']= ta.get_rsi(period)
# ta.data['indicator']= ta.get_bollinger_band(period)
# ta.data['indicator']= ta.get_stochastic_oscillator(period) # dont recommend



### TRADING STRATEGY ###

strat = Strategy()


# def strategy(data_col, signal):
#     position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
#     position = position.astype(float)
#     position[np.isnan(data_col)] = np.nan
#     return position

# ta.data['position'] = np.where(ta.data['ta'] > signal, 1, np.where(ta.data['ta'] < -signal, -1, 0))
# ta.data.loc[ta.data['ta'].isna(), 'position'] = np.nan


### Perf ###

# backtest inconsistent as the data price has no change

# perf = Performance(ta.data, trading_period, ta.get_bollinger_band, strategy, period, signal)

# print(perf.get_strategy_performance())
# print(perf.get_buy_hold_performance())

# perf.data.to_csv('perf.csv')
### Parameters Optimization ###

# possible optmization to find by interquatile range
window_list = tuple(x for x in range(0,50000,1000))
signal_list = tuple(x for x in np.arange(0, 2.5, 0.25))

# param_opt = ParametersOptimization(ta.data, trading_period, ta.get_sma, strategy)
# param_opt = ParametersOptimization(ta.data, trading_period, ta.get_ema, strategy)
# param_opt = ParametersOptimization(ta.data, trading_period, ta.get_rsi, strategy)
param_opt = ParametersOptimization(ta.data, trading_period, ta.get_bollinger_band, strat.momentum_const_signal)


param_perf = pd.DataFrame(param_opt.optimize(window_list, signal_list))
param_perf.rename(columns={0:'window',1:'signal',2:'sharpe'},inplace=True)
print(param_perf)

### plot ###

# fig = px.line(perf.data, x='datetime', y=['cumu', 'buy_hold_cumu'], title='strategy')
# fig.write_html('Trading Strategy.html', auto_open=True)

data_table = param_perf.pivot(index='window',columns='signal',values='sharpe')
sns.heatmap(data_table, annot=True, fmt='g', cmap='Greens')
plt.show()

end = time.time()
print(end-start)


















