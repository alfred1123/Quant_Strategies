'''
This script will use decorators to input functions of technical Analysis 
to optimize the parameters of the model for the trading strategy
'''

import pandas as pd
import numpy as np
import itertools
from ta import TechnicalAnalysis
from perf import Performance

class Parameters_Optimization:
    
    def __init__(self,data):
        self.data = data
        self.data['Date'] = pd.to_datetime(self.data['Date'])
        self.data.set_index('Date', inplace=True)
        
    
    # According to the technical indictors, 
    # we will input the argument parameters by the sharpe ratio
    # the argument parameters should be in the form of a tuples
    def param_opt(self, func, *args:tuple):
        for combinations in itertools.product(list(*args)):
            yield 
    
    # try a fumction to return the inputed arguments of a fucntion
    def param_test_opt(self, func, *args:tuple):
        return *args
   

# Suppose you have a dynamic number of lists
list1 = [1, 2, 3]
list2 = [4, 5]
list3 = [6, 7, 8]

# You can put all lists into a list of lists
all_lists = [list1, list2, list3]

# Use itertools.product() to get all possible combinations
combinations = list(itertools.product(*all_lists))

# Print the result
print(combinations)
print(*all_lists)
    
    
    
        
        
    