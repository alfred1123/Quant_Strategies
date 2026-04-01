# we will be storing all the strategies here before we move them to the main file
# we will need a unique name for each strategy wtih ID

import numpy as np

class Strategy:
    
    def __init__(self):
        pass
    
    def momentum_const_signal(data_col, signal):
        position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position
    
    def reversion_const_signal(data_col, signal):
        position = np.where(data_col < -signal, 1, np.where(data_col > signal, -1, 0))
        position = position.astype(float)
        position[np.isnan(data_col)] = np.nan
        return position