import ccxt
import time
import pandas as pd
import numpy as np
import datetime
import os
from dotenv import load_dotenv
from pprint import pprint

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

load_dotenv()

exchange = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY'),
    'secret': os.getenv('BYBIT_SECRET_KEY'),
})

markets = exchange.load_markets()
# print(markets)
# print('********************************')
symbol = 'BTCUSDT'
market = exchange.market(symbol)
# print(market)

### signal ###
def signal(df, x, y):

    df['ma'] = df['close'].rolling(x).mean()
    df['sd'] = df['close'].rolling(x).std()
    df['z'] = (df['close'] - df['ma']) / df['sd']

    df['pos'] = np.where(df['z'] > y, 1, 0)

    pos = df['pos'].iloc[-1]

    df['dt'] = pd.to_datetime(df['datetime']/1000, unit='s')

    print(df.tail(3))

    return pos

### trade ###
def trade(pos):

    ### get account info before trade ###
    net_pos = float(exchange.fetchPositions([symbol])[0]['info']['size'])
    

    ### trade ###
    if pos == 1:
        if net_pos == 0:
            print('long ed 0.01')
            order = exchange.create_order('BTCUSDT', 'market', 'buy', bet_size, None)
            pprint(order)

    elif pos == 0:
        if net_pos == bet_size:
            print('sell ed 0.01')
            order = exchange.create_order('BTCUSDT', 'market', 'sell', bet_size, None, params={'reduce_only': True})
            pprint(order)

    time.sleep(1)

    ### get account info after trade ###
    net_pos = float(exchange.fetchPositions([symbol])[0]['info']['size'])
    print('after signal')
    print('nav', datetime.datetime.now(), exchange.fetch_balance()['USDT']['total'])

### param ###
x = 3
y = 0
pos = 0
bet_size = 0.001 #0.001

while True:

    if datetime.datetime.now().second == 5:

        df = pd.read_csv(r'data.csv')

        pos = signal(df, x, y)
        print(pos)

        trade(pos)

        time.sleep(1)
