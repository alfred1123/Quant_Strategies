'''
This script will use decorators to input functions of technical Analysis 
to optimize the parameters of the model for the trading strategy
'''

import pandas as pd
import numpy as np

class Parameters_Optimization:
    
    def __init__(self,data):
        self.data = data
        self.data['Date'] = pd.to_datetime(self.data['Date'])
        self.data.set_index('Date', inplace=True)
        
        
        
        
    