import ccxt
import time
import pandas as pd
import datetime
import os
from pprint import pprint
from dotenv import load_dotenv

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)


exchange = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY'),
    'secret': os.getenv('BYBIT_SECRET_KEY'),
})

markets = exchange.load_markets() # all avaliable price
symbol = 'BTCUSDT'
market = exchange.market(symbol)
# print(markets)
# print(market)

### get data ###
while True:

    # if datetime.datetime.now().hour == 8 and datetime.datetime.now().minute == 0:
    if datetime.datetime.now().second == 0:

        ### timestamp adjustment ###
        unix_time = datetime.datetime.timestamp(datetime.datetime.now()) * 1000
        unix_time = unix_time - 100 * (60 * 1000)  # 1m
        # unix_time = unix_time - 100*(60*60*1000) # 1h
        # unix_time = unix_time - 100*(24*60*60*1000) # 1d

        kline_BTC_usdt = exchange.fetchOHLCV('BTCUSDT','1m', since=unix_time)

        df_new = pd.DataFrame(kline_BTC_usdt, columns = ['datetime', 'open', 'high', 'low', 'close', 'volume'])

        try:
            df_old = pd.read_csv('data.csv')
            df_new = pd.concat([df_old, df_new]).drop_duplicates(subset=['datetime']).reset_index(drop=True)
        except:
            pass

        df_new = df_new[['datetime', 'close']]
        df_new.to_csv('data.csv')

        time.sleep(1)