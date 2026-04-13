---
description: "Run a backtest with specified parameters: symbol, date range, indicator, and strategy."
agent: "agent"
argument-hint: "Symbol, date range, indicator name, strategy name"
---
Run a backtest using the pipeline in `src/`. 

1. Identify the requested symbol, date range, indicator, and strategy from the user's input.
2. Show what parameters will be used before running.
3. Execute from `src/` using: `cd src && python main.py`
4. Display the strategy performance and buy-and-hold comparison.

Available indicators: `sma`, `ema`, `rsi`, `bollinger_band`, `stochastic_oscillator`
Available strategies: `momentum_band_signal`, `reversion_band_signal`

If the user doesn't specify parameters, suggest sensible defaults (BTC, bollinger_band, momentum, window=20, signal=1.0).
