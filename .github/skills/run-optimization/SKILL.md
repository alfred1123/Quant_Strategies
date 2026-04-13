---
name: run-optimization
description: 'Run parameter optimization grid search for a backtest strategy. Use when tuning indicator windows and signal thresholds to find optimal Sharpe ratio. Produces heatmap visualization.'
argument-hint: 'Indicator, strategy, symbol, window range, signal range'
---

# Run Parameter Optimization

## When to Use
- Finding optimal indicator window and signal threshold
- Generating Sharpe ratio heatmaps
- Comparing strategy performance across parameter space

## Procedure

### 1. Prepare data

**Preferred source: YahooFinance** (free, no API key, 10+ years daily data).

```python
from data import YahooFinance
from ta import TechnicalAnalysis
from strat import Strategy
from param_opt import ParametersOptimization
import pandas as pd
import numpy as np

yf = YahooFinance()
price = yf.get_historical_price('<symbol>', '<start>', '<end>')

df = pd.DataFrame({
    'datetime': price['t'],
    'price':    price['v'],
    'factor':   price['v'],
})
```

**Symbols**: equities (`AAPL`), crypto (`BTC-USD`), ETFs (`SPY`), indices (`^GSPC`).

**Alternative sources** (require API keys):
```python
from data import AlphaVantage  # Free tier: 25 req/day, ~100 days only
from data import Glassnode     # On-chain crypto metrics
```

### 2. Define parameter grid

Choose ranges based on data resolution:

| Resolution | Window range | Signal range | `trading_period` |
|---|---|---|---|
| Daily bars (equity) | `range(5, 105, 5)` | `np.arange(0.25, 2.75, 0.25)` | `252` |
| Daily bars (crypto) | `range(5, 105, 5)` | `np.arange(0.25, 2.75, 0.25)` | `365` |
| 1h bars (crypto) | `range(0, 8000, 200)` | `np.arange(0, 2.5, 0.25)` | `365 * 24` |
| 10m bars (crypto) | `range(0, 50000, 1000)` | `np.arange(0, 2.5, 0.25)` | `365 * 24 * 6` |

**Important:** Crypto markets trade 24/7/365 — use `365` (not `252`). `252` is for equity markets only.

`trading_period` = number of bars per year (used to annualize Sharpe ratio).

### 3. Run single backtest (optional, for baseline)

```python
ta = TechnicalAnalysis(df)
trading_period = 365  # crypto (24/7/365); use 252 for equities

from perf import Performance
perf = Performance(df, trading_period, ta.get_bollinger_band,
                   Strategy.momentum_band_signal, 20, 1.0)
print(perf.get_strategy_performance())
print(perf.get_buy_hold_performance())
perf.data.to_csv('../../results/perf_<symbol>_<indicator>.csv', index=False)
```

### 4. Run grid search

```python
opt = ParametersOptimization(
    ta.data, trading_period,
    ta.get_bollinger_band,          # indicator function
    Strategy.momentum_band_signal, # strategy function
)

window_list = tuple(range(5, 105, 5))
signal_list = tuple(np.arange(0.25, 2.75, 0.25))

results = pd.DataFrame(
    opt.optimize(window_list, signal_list),
    columns=['window', 'signal', 'sharpe'],
)
results.to_csv('../../results/opt_<symbol>_<indicator>.csv', index=False)

best = results.loc[results['sharpe'].idxmax()]
print(f"Best: window={int(best['window'])}, signal={best['signal']:.2f}, "
      f"Sharpe={best['sharpe']:.4f}")
```

### 5. Visualize

Use `matplotlib.use('Agg')` to save to file (no GUI needed):

```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

pivot = results.pivot(index='window', columns='signal', values='sharpe')
plt.figure(figsize=(12, 8))
sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn', center=0)
plt.title('<Symbol> <Indicator> — Sharpe Ratio Heatmap')
plt.xlabel('Signal Threshold')
plt.ylabel('Indicator Window')
plt.tight_layout()
plt.savefig('../../results/heatmap_<symbol>_<indicator>.png', dpi=150)
```

### 6. Interpret results

- Look for **stable regions** (clusters of high Sharpe), not isolated peaks.
- Best `(window, signal)` pair = highest Sharpe in a stable region.
- Sharpe > 1.5 and Calmar > 1.0 are target thresholds.
- Beware of overfitting on narrow parameter peaks — an isolated bright cell surrounded by low values is suspicious.
- **Bollinger + momentum** works well because z-scores are centered around 0, matching the ±signal thresholds.
- **SMA + momentum** on raw prices doesn't work — prices are always positive, so `signal < 2.5` always triggers long. Use Bollinger z-score or RSI instead.

### 7. Run from command line

```bash
cd src && python main.py
```

**Output files** (saved to `results/`):

| File | Contents |
|------|----------|
| `perf_<symbol>_<indicator>.csv` | Daily PnL, cumulative returns, drawdown, positions |
| `opt_<symbol>_<indicator>.csv` | All grid search results (window, signal, sharpe) |
| `heatmap_<symbol>_<indicator>.png` | Sharpe ratio heatmap |

## Available combinations

**Indicators**: `get_sma`, `get_ema`, `get_rsi`, `get_bollinger_band`, `get_stochastic_oscillator`

**Strategies**: `momentum_band_signal`, `reversion_band_signal`

**Data sources**: `YahooFinance` (preferred), `AlphaVantage`, `Glassnode`, `FutuOpenD`
