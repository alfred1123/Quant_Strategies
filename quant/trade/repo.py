import ccxt


class CcxtRepo:
    
    def __init__():
        pass
    
    
    def declare_exchange(self,exchnge):
        self.exchange = getattr(ccxt, exchange)({
            'apiKey': os.getenv('BYBIT_API_KEY'),
            'secret': os.getenv('BYBIT_SECRET_KEY'),
        })
        
    def get_markets(self):
        return ccxt.load_markets()
    
    def get_OHLCV(self, symbol):   ## maybe this shall be in INST schema and data source. yes and no, depends do ccxt has the history. else doubting shall we put pricing data from diff data source tgt.
        
        #switch to database input

        ### timestamp adjustment ###
        unix_time = datetime.datetime.timestamp(datetime.datetime.now()) * 1000
        unix_time = unix_time - 100 * (60 * 1000)  # 1m
        # unix_time = unix_time - 100*(60*60*1000) # 1h
        # unix_time = unix_time - 100*(24*60*60*1000) # 1d

        kline_BTC_usdt = self.exchange.fetchOHLCV('BTCUSDT','1m', since=unix_time)
        
        try:
            df_old = pd.read_csv('data.csv')
            df_new = pd.concat([df_old, df_new]).drop_duplicates(subset=['datetime']).reset_index(drop=True)
        except:
            pass

        df_new = df_new[['datetime', 'close']] #check diff to fetch_ticker
        df_new.to_csv('data.csv')
        
    def create_order(self, ticker, orderType, buysell, size, dummy, params) # to be fix
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
        
    
    
    
    
    
    
if __name__ == "__main__":
    