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


### DATA ###

# get data from FutuOpenD
# futu_opend = FutuOpenD()
# df = futu_opend.get_historical_data('HK.00700', '2021-01-01', '2021-01-31', 'K_DAY')
# print(df)

# get data from Glassnode
glassnode = Glassnode()
df = glassnode.get_historical_price('BTC', '2020-05-11', '2021-04-03', '1h')
print(df)

glassnode = Glassnode()
df = glassnode.get_historical_price('BTC', '2020-05-11', '2021-04-03', '1h')
print(df)


#!!!!!!!!!!!!!!!!! ammend data for analysis !!!!! need to amend
df = df[['t','v']]
df



### TECHNICAL ANALYSIS ###
ta = TechnicalAnalysis(df)
