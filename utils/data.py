import os
import futu as ft
import pandas as pd
import pandas as pd
from dotenv import load_dotenv



class data():
    
    def __init__(self):
        load_dotenv()
        self.futu_username = os.getenv("FUTU_USER_ID")
        self.futu_password = os.getenv("FUTU_PWD")
        self.futu_host = os.getenv("FUTU_HOST")
        self.futu_port = os.getenv("FUTU_PORT")
    
    def futu_quote(self,code,start,end):
        # connect to Futu API
        quote_ctx = ft.OpenQuoteContext(host=self.futu_host, port=self.futu_port)

        # set the stock code and time ran   ge
        code = 'HK.00700'  # Tencent stock code
        start = '2001-01-01'
        end = '2022-03-18'

        # get the historical K-line data
        ret, data, page_req_key = quote_ctx.request_history_kline(code, start=start, end=end)

        # close the quote context
        quote_ctx.close()

        # convert the data to a pandas DataFrame
        df = pd.DataFrame(data)

        return df
    
    def futu_holding(self):
        
        
        trd_ctx = ft.OpenSecTradeContext(filter_trdmarket = ft.Trd_Market.US, host=self.futu_host, port=self.futu_port, security_firm = ft.SecurityFirm.FUTUSECURITIES)
        ret, df = trd_ctx.position_list_query()
        if ret == ft.RET_OK:
            return df
        else:
            print('position_list_query error: ', df)
        trd_ctx.close()  # Close the current connection

# print the DataFrame
if __name__ == "__main__":
    obj = data()
    print(obj.futu_host,obj.futu_port)

    print(obj.futu_quote('HK.00700',"2001-01-01","2022-03-18"))

    print(obj.futu_holding())
