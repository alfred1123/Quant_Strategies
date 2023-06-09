'''
This script is used to calculate the technical analysis indicators for the stock
for different factors of the stock
'''

import pandas as pd


class TechnicalAnalysis:
    
    # need to check!!!!!
    def __init__(self, data) -> None:
        self.data = data
        
    def get_sma(self, period):
        """_summary_
            simple moving average
            
        Args:
            period (int): moving average period

        Returns:
            _type_: np.array([])
        """
        sma = self.data['factor'].rolling(window=period).mean()
        return sma
    
    def get_ema(self, period):
        """_summary_
            exponential moving average
        Args:
            period (int): moving average period

        Returns:
            _type_: np.array([])
        """
        ema = self.data['factor'].ewm(span=period, adjust=False).mean()
        return ema
    
    # check drop na!!!!!!
    def get_rsi(self, period):
        
        """_summary_
        Args:
            period (int): rsi period

        Returns:
            _type_: np.array([])
        """
        delta = self.data['factor'].diff(1)
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
    
    
    # too many parameters, may tend to overfitting, disabled for now
    # def get_macd(self, period1, period2, period3):
    
    #     """_summary_
    #     Args:
    #         period1 (int): fast ema period
    #         period2 (int): slow ema period
    #         period3 (int): signal ema period
            
    #     Returns:
    #         _type_: np.array([])
    #     """
        
    #     ema1 = self.data['factor'].ewm(span=period1, adjust=False).mean()
    #     ema2 = self.data['factor'].ewm(span=period2, adjust=False).mean()
    #     macd = ema1 - ema2
    #     signal = macd.ewm(span=period3, adjust=False).mean()
    #     return macd, signal
    
    def get_bollinger_band(self, period):
        
        """_summary_
        Args:
            period (int): bollinger band period
            threshold (int): bollinger band threshold
            
        Returns:
            _type_: np.array([])
        """
        
        # self.data['sma'] = self.data['factor'].rolling(window=period).mean()
        # self.data['rstd'] = self.data['factor'].rolling(window=period).std()
        sma = self.data['factor'].rolling(window=period).mean()
        rstd = self.data['factor'].rolling(window=period).std()
        z = (self.data['factor'] - sma) / rstd
        return z
    
    # k is the fast stochastic oscillator, d is the slow stochastic oscillator
    def get_stochastic_oscillator(self, period):
        
        """_summary_
        Args:
            period (int): stochastic oscillator period
        Returns:
            _type_: oscillator moving average
        """
        
        high = self.data['High'].rolling(window=period).max()
        low = self.data['Low'].rolling(window=period).min()
        k = 100 * (self.data['Close'] - low) / (high - low)
        d = k.rolling(window=period).mean()
        return d