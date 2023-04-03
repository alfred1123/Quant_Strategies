'''
This script is for retrieving data from different sources of API.
1. Futu OpenD
2. Glassnode
'''

import futu
import requests
import os
from dotenv import load_dotenv
import datetime as dt
import time
import pandas as pd

# Create a class for retrieving data from Futu OpenD
class FutuOpenD:
    
    
    
    def __init__(self) -> None:
        load_dotenv()
        self.__host = os.getenv('FUTU_HOST')
        self.__port = int(os.getenv('FUTU_PORT'))
        print(type(self.__host), type(self.__port))
        self.quote_ctx = futu.OpenQuoteContext(host=self.__host, port=self.__port)
        
    # retrieve historical data for stock quotes from Futu OpenD
    def get_historical_data(self, symbol, start_date, end_date):
        with self.quote_ctx:
            ret, data, page_req_key = self.quote_ctx.request_history_kline(symbol, start=start_date, end=end_date, autype=futu.AuType.QFQ)
            
        return data

class Glassnode:
    
    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv('GLASSNODE_API_KEY')
        self.__api_url = os.getenv('GLASSNODE_API_URL')
        print(type(self.__api_key), type(self.__api_url))
        
    def get_historical_data(self, symbol, start_date, end_date):
        # set time to download
        since = int(time.mktime(time.strptime(start_date, "%Y-%m-%d"))) # 2020 May 11
        # since = 1646092800 # 2022 Mar 1
        until = int(time.mktime(time.strptime(end_date, "%Y-%m-%d"))) 
        resolution = "1h"

        res = requests.get("https://api.glassnode.com/v1/metrics/market/price_usd_close",
                           params={"a": "BTC", "s": since, "u": until, "api_key": self.__api_key, "i": resolution})
        print(since, until)
        df = pd.read_json(res.text, convert_dates=['t'])
        
        return df
        
        
        

# print the DataFrame
if __name__ == "__main__":
    # futu_opend = FutuOpenD()
    # data = futu_opend.get_historical_data('HK.00700', '2021-01-01', '2021-01-31')
    # print(data)
    
    
    glassnode = Glassnode()
    data = glassnode.get_historical_data('BTC', '2020-05-11', '2021-04-03')
    print(data)
    
 
    
    
    


