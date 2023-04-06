'''
This script is for retrieving data from different sources of API.
1. Futu OpenD
2. Glassnode

future updates: turn retreiving data function to recursive for memoization and caching
'''

import futu
import requests
import os
from dotenv import load_dotenv
import time
import pandas as pd
from functools import lru_cache

# Create a class for retrieving data from Futu OpenD
class FutuOpenD:
    
    
    
    def __init__(self) -> None:
        load_dotenv()
        self.__host = os.getenv('FUTU_HOST')
        self.__port = int(os.getenv('FUTU_PORT'))
        print(type(self.__host), type(self.__port))
        self.quote_ctx = futu.OpenQuoteContext(host=self.__host, port=self.__port)
        
    # retrieve historical data for stock quotes from Futu OpenD
    @lru_cache(maxsize=32)
    def get_historical_data(self, symbol, start_date, end_date, resolution = 'K_DAY'):
        """_summary_

        Args:
            symbol (str): stock symbol 
            start_date (str): start of date range
            end_date (str): end of date range
            resolution (str): resolution of data, Defaults to 'K_DAY'. (K_YEAR, K_QUARTER, K_MONTH, K_WEEK, K_DAY, K_60M, K_30M, K_15M, K_5M, K_3M, K_1M)

        Returns:
            DataFrame: historical data
            columns: ['code', 'time_key', 'open', 'close', 'high', 'low', 'pe_ratio', 'turnover_rate', 'volume', 'turnover', 'change_rate', 'last_close']
        """
        with self.quote_ctx:
            ret, data, page_req_key = self.quote_ctx.request_history_kline(symbol, start=start_date, end=end_date, ktype=resolution, autype=futu.AuType.QFQ)
            
        return data

class Glassnode:
    
    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv('GLASSNODE_API_KEY')
        # self.__api_url = os.getenv('GLASSNODE_API_URL')
        
    @lru_cache(maxsize=32)    
    def get_historical_price(self, symbol, start_date, end_date, resolution='24h'):
        """_summary_
        
         Args:
            symbol (str): stock symbol 
            start_date (str): start of date range
            end_date (str): end of date range
            resolution (str): resolution of data, Defaults to '24h'(1month, 1w, 24h, 1h, 10m)
            

        Returns:
            DataFrame: historical data
            columns: ['t', 'v']
        """
        # set time to download
        since = int(time.mktime(time.strptime(start_date, "%Y-%m-%d"))) # 2020 May 11
        # since = 1646092800 # 2022 Mar 1
        until = int(time.mktime(time.strptime(end_date, "%Y-%m-%d"))) 

        res = requests.get("https://api.glassnode.com/v1/metrics/market/price_usd_close",
                           params={"a": "BTC", "s": since, "u": until, "api_key": self.__api_key, "i": resolution})
        df = pd.read_json(res.text, convert_dates=['t'])
        
        return df
        
        
        

# print the DataFrame
if __name__ == "__main__":
    
    # start = time.time()
    # futu_opend = FutuOpenD()
    # data = futu_opend.get_historical_data('HK.00700', '2021-01-01', '2023-04-05', 'K_DAY')
    # end = time.time()
    # print(end - start)
    # print(data.columns)
    
    
    start = time.time()
    glassnode = Glassnode()
    data = glassnode.get_historical_price('BTC', '2020-05-11', '2021-04-03')
    end = time.time()
    print(end - start)
    print(data.columns)
    
 
    
    
    


