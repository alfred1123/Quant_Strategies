'''
This script will use decorators to input functions of technical Analysis 
to optimize the parameters of the model for the trading strategy
'''

import itertools
import logging

import pandas as pd
import numpy as np

from perf import Performance

logger = logging.getLogger(__name__)


class ParametersOptimization:
    
    def __init__(self, data, config, *, fee_bps=None):
        self.data = data
        self.config = config
        self.fee_bps = fee_bps
    
    
        
    
    # According to the technical indictors, 
    # we will input the argument parameters by the sharpe ratio
    # the argument parameters should be in the form of a tuples
    # the function will return the optimized parameters
    
    def optimize(self, indicator_tuple:tuple, strategy_tuple:tuple):
        total = len(indicator_tuple) * len(strategy_tuple)
        logger.info("Starting grid search: %d windows × %d signals = %d combinations",
                    len(indicator_tuple), len(strategy_tuple), total)
        for i, (window, signal) in enumerate(
            itertools.product(indicator_tuple, strategy_tuple)
        ):
            try:
                perf = Performance(self.data, self.config,
                                   window, signal, fee_bps=self.fee_bps)
                perf.enrich_performance()
                sharpe = perf.get_sharpe_ratio()
            except Exception:
                logger.warning("Grid search failed for window=%s, signal=%s",
                               window, signal, exc_info=True)
                sharpe = np.nan
            yield (window, signal, sharpe)
        logger.info("Grid search complete: %d combinations evaluated", total)
     
        
    
    
    
        
        
    