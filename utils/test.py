import os
import futu as ft
import pandas as pd
from dotenv import load_dotenv


# Set display options for pandas dataframes
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

load_dotenv()


futu_username = os.getenv("FUTU_USER_ID")
futu_password = os.getenv("FUTU_PWD")

trd_ctx = ft.OpenSecTradeContext(filter_trdmarket=ft.TrdMarket.US, host='127.0.0.1', port=11111, security_firm=ft.SecurityFirm.FUTUSECURITIES)
ret, data = trd_ctx.position_list_query()
if ret == ft.RET_OK:
    print(data)
else:
    print('position_list_query error: ', data)
trd_ctx.close()  # Close the current connection
