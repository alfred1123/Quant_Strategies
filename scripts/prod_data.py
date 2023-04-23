'''
This script aims for getting real-time trade data from different exchange.
'''

import ccxt
import time
import pandas as pd
import numpy as np
import datetime
import os
from dotenv import load_dotenv

# this class aims to get the real-time trade data from different exchange
class BybitRealTimeData:
    
    def __init__(self, exchange, symbol, interval, limit):
        self.__bybit_api_key = os.getenv('BYBIT_API_KEY')
        self.__bybit_secret_key = os.getenv('BYBIT_SECRET_KEY')
        self.exchange = exchange
        self.symbol = symbol
        self.interval = interval
        self.limit = limit
        
    def get_data(self):
        return self.exchange.fetchOHLCV(self.symbol, self.interval, self.limit)
    
    def 
    