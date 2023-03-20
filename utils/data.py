import futu as ft
import pandas as pd

class data:
    
    def data_futu(code,start,end,host,port):
        # connect to Futu API
        quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

        # set the stock code and time range
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

# print the DataFrame
if __name__ == "__main__":
    print(data.data_futu('HK.00700',"2001-01-01","2022-03-18","127.0.0.1",11111))

