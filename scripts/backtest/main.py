'''
Backtest pipeline: fetch data, compute indicators, run strategy,
measure performance, and optimize parameters via grid search.

Usage:
    cd scripts/backtest && python main.py
'''


from data import YahooFinance
from ta import TechnicalAnalysis
from perf import Performance
from param_opt import ParametersOptimization
from strat import Strategy
import pandas as pd
import numpy as np
import time
import matplotlib
matplotlib.use('Agg')  # non-interactive backend — saves to file instead of plt.show()
import matplotlib.pyplot as plt
import seaborn as sns

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)


start = time.time()

### DATA ###
# Yahoo Finance — free, no API key, 10+ years of daily data
yf = YahooFinance()
price = yf.get_historical_price('BTC-USD', '2016-01-01', '2026-04-01')

df = pd.DataFrame({
    'datetime': price['t'],
    'price':    price['v'],
    'factor':   price['v'],
})
print(f"Loaded {len(df)} daily bars: {df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}")


### TECHNICAL ANALYSIS ###
# BTC trades 24/7/365 — use 365 for daily bars (252 is for equities only)
trading_period = 365
ta = TechnicalAnalysis(df)


### SINGLE BACKTEST — Bollinger + momentum on BTC ###
period = 20
signal = 1.0

perf = Performance(df, trading_period, ta.get_bollinger_band,
                   Strategy.momentum_const_signal, period, signal)

print("\n=== Strategy Performance (Bollinger 20 / signal 1.0) ===")
print(perf.get_strategy_performance())
print("\n=== Buy & Hold Performance ===")
print(perf.get_buy_hold_performance())

# Save daily PnL to CSV for inspection
perf.data.to_csv('../../results/perf_btc_bollinger.csv', index=False)
print("\nDaily PnL saved to results/perf_btc_bollinger.csv")


### PARAMETER OPTIMIZATION — grid search over window × signal ###
# Bollinger z-score works well with momentum_const_signal because
# the z-score is centered around 0, matching the ±signal thresholds.
window_list = tuple(range(5, 105, 5))            # 5, 10, 15 ... 100
signal_list = tuple(np.arange(0.25, 2.75, 0.25)) # 0.25, 0.50 ... 2.50

param_opt = ParametersOptimization(
    ta.data, trading_period,
    ta.get_bollinger_band,
    Strategy.momentum_const_signal,
)

param_perf = pd.DataFrame(
    param_opt.optimize(window_list, signal_list),
    columns=['window', 'signal', 'sharpe'],
)

# Save raw grid results
param_perf.to_csv('../../results/opt_btc_bollinger.csv', index=False)
print(f"\nGrid search: {len(param_perf)} combinations evaluated")
print(param_perf.sort_values('sharpe', ascending=False).head(10))

# Best parameters
best = param_perf.loc[param_perf['sharpe'].idxmax()]
print(f"\n★ Best: window={int(best['window'])}, signal={best['signal']:.2f}, "
      f"Sharpe={best['sharpe']:.4f}")


### HEATMAP ###
pivot = param_perf.pivot(index='window', columns='signal', values='sharpe')
plt.figure(figsize=(12, 8))
sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn', center=0)
plt.title('BTC Bollinger Momentum — Sharpe Ratio Heatmap')
plt.xlabel('Signal Threshold')
plt.ylabel('Bollinger Window')
plt.tight_layout()
plt.savefig('../../results/heatmap_btc_bollinger.png', dpi=150)
print("Heatmap saved to results/heatmap_btc_bollinger.png")

elapsed = time.time() - start
print(f"\nDone in {elapsed:.1f}s")















