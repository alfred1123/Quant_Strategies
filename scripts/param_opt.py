'''
This script will use decorators to input functions of technical Analysis 
to optimize the parameters of the model for the trading strategy
'''

import pandas as pd
import numpy as np
import itertools
from perf import Performance

class ParametersOptimization:
    
    def __init__(self, data, trading_period, indicator_func, strategy_func):
        self.data = data
        self.trading_period = trading_period
        self.indicator_func = indicator_func
        self.strategy_func = strategy_func
        
    
    # According to the technical indictors, 
    # we will input the argument parameters by the sharpe ratio
    # the argument parameters should be in the form of a tuples
    # the function will return the optimized parameters
    
    def optimize(self, indicator_tuple:tuple, strategy_tuple:tuple):
        for window, signal in list(itertools.product(indicator_tuple, strategy_tuple)):
            perf = Performance(self.data, self.trading_period, self.indicator_func, self.strategy_func, window, signal)
            yield (window, signal, perf.get_sharpe_ratio())
            
        
    
    
    
        
        
    