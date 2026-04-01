---
name: run-optimization
description: 'Run parameter optimization grid search for a backtest strategy. Use when tuning indicator windows and signal thresholds to find optimal Sharpe ratio. Produces heatmap visualization.'
argument-hint: 'Indicator, strategy, window range, signal range'
---

# Run Parameter Optimization

## When to Use
- Finding optimal indicator window and signal threshold
- Generating Sharpe ratio heatmaps
- Comparing strategy performance across parameter space

## Procedure

### 1. Prepare data

```python
from data import Glassnode
from ta import TechnicalAnalysis
from strat import Strategy
from param_opt import ParametersOptimization
import pandas as pd
import numpy as np

glassnode = Glassnode()
price = glassnode.get_historical_price('<symbol>', '<start>', '<end>', '<resolution>')
factor = glassnode.get_historical_price('<symbol>', '<start>', '<end>', '<resolution>')
df = pd.merge(price, factor, how='inner', on='t')
df.rename(columns={'t': 'datetime', 'v_x': 'price', 'v_y': 'factor'}, inplace=True)
```

### 2. Define parameter grid

Choose ranges based on data resolution:

| Resolution | Window range | Signal range |
|---|---|---|
| 10m bars | `range(0, 50000, 1000)` | `np.arange(0, 2.5, 0.25)` |
| 1h bars | `range(0, 8000, 200)` | `np.arange(0, 2.5, 0.25)` |
| Daily bars | `range(0, 500, 10)` | `np.arange(0, 2.5, 0.25)` |

Calculate `trading_period` = number of bars per year for the resolution.

### 3. Run grid search

```python
ta = TechnicalAnalysis(df)
trading_period = 365 * 24 * 6  # adjust for resolution

opt = ParametersOptimization(
    ta.data, trading_period,
    ta.get_bollinger_band,          # indicator function
    Strategy.momentum_const_signal  # strategy function
)

window_list = tuple(range(0, 50000, 1000))
signal_list = tuple(np.arange(0, 2.5, 0.25))

results = pd.DataFrame(opt.optimize(window_list, signal_list))
results.rename(columns={0: 'window', 1: 'signal', 2: 'sharpe'}, inplace=True)
```

### 4. Visualize

```python
import seaborn as sns
import matplotlib.pyplot as plt

pivot = results.pivot(index='window', columns='signal', values='sharpe')
sns.heatmap(pivot, annot=True, fmt='.2f', cmap='Greens')
plt.title('Sharpe Ratio Heatmap')
plt.show()
```

### 5. Interpret results

- Look for **stable regions** (clusters of high Sharpe), not isolated peaks.
- Best `(window, signal)` pair = highest Sharpe in a stable region.
- Sharpe > 1.5 and Calmar > 1.0 are target thresholds.
- Beware of overfitting on narrow parameter peaks.

## Available combinations

**Indicators**: `get_sma`, `get_ema`, `get_rsi`, `get_bollinger_band`, `get_stochastic_oscillator`

**Strategies**: `momentum_const_signal`, `reversion_const_signal`
