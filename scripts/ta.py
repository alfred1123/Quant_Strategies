'''
This script is used to calculate the technical analysis indicators for the stock
for different factors of the stock
'''
import pandas as pd


class TechnicalAnalysis:
    
    # need to check!!!!!
    def __init__(self, data) -> None:
        self.data = data
        self.data['Date'] = pd.to_datetime(self.data['Date'])
        self.data.set_index('Date', inplace=True)
        
    def get_sma(self, period, column='Close'):
        sma = self.data[column].rolling(window=period).mean()
        return sma
    
    def get_ema(self, period, column='Close'):
        ema = self.data[column].ewm(span=period, adjust=False).mean()
        return ema
    
    # check drop na!!!!!!
    def get_rsi(self, period, column='Close'):
        delta = self.data[column].diff(1)
        delta = delta.dropna()
        up = delta.copy()
        down = delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up1 = up.rolling(window=period).mean()
        roll_down1 = down.abs().rolling(window=period).mean()
        RS1 = roll_up1 / roll_down1
        rsi = 100.0 - (100.0 / (1.0 + RS1))
        return rsi
    
    
    # too many parameters, may tend to overfitting
    def get_macd(self, period1, period2, period3, column='Close'):
        ema1 = self.data[column].ewm(span=period1, adjust=False).mean()
        ema2 = self.data[column].ewm(span=period2, adjust=False).mean()
        macd = ema1 - ema2
        signal = macd.ewm(span=period3, adjust=False).mean()
        return macd, signal
    
    def get_bollinger_band(self, period, threshold, column='Close'):
        sma = self.data[column].rolling(window=period).mean()
        rstd = self.data[column].rolling(window=period).std()
        upper_band = sma + rstd * threshold
        lower_band = sma - rstd * threshold
        return upper_band, lower_band
    
    # k is the fast stochastic oscillator, d is the slow stochastic oscillator
    def get_stochastic_oscillator(self, period):
        high = self.data['High'].rolling(window=period).max()
        low = self.data['Low'].rolling(window=period).min()
        k = 100 * (self.data['Close'] - low) / (high - low)
        d = k.rolling(window=period).mean()
        return k, d