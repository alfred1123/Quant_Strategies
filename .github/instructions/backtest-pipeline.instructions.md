---
description: "Use when modifying or extending the backtest pipeline: data sources, technical indicators, strategies, performance metrics, or parameter optimization. Covers module interfaces and data flow."
applyTo: "src/**"
---
# Backtest Pipeline Rules

## Data Flow

```
data.py → ta.py → strat.py → perf.py → param_opt.py
```

All modules are orchestrated by `main.py`. Imports are **relative** to the `src/` package.

## Module Interfaces

### data.py — Data Sources
- Each source is a class (`FutuOpenD`, `Glassnode`, `AlphaVantage`, `YahooFinance`).
- Returns a DataFrame. Glassnode, AlphaVantage, and YahooFinance return columns `['t', 'v']`.
- API keys loaded from `.env` at the project root via `python-dotenv`; constructors validate that required keys are set.
- `YahooFinance` requires no API key. Supports equities, ETFs, indices, and crypto (e.g. `'BTC-USD'`). Returns 10+ years of free daily data.
- Methods use `@lru_cache` — clear cache in tests.
- AlphaVantage auto-detects crypto vs equity symbols and uses the appropriate API endpoint.

### ta.py — Technical Analysis
- `TechnicalAnalysis(data)` — accepts DataFrame with a `'factor'` column.
- Indicator methods: `get_sma(period)`, `get_ema(period)`, `get_rsi(period)`, `get_bollinger_band(period)`, `get_stochastic_oscillator(period)`.
- Stochastic also requires `'High'`, `'Low'`, `'Close'` columns.
- Returns a Series (same length as input, NaN-padded at start).

### strat.py — Strategy Signals
- `Strategy.momentum_const_signal(data_col, signal)` → numpy array of `{-1, 0, 1}`.
- `Strategy.reversion_const_signal(data_col, signal)` → inverse of momentum.
- These are effectively static methods (no `self` used).

### perf.py — Performance Metrics
- `Performance(data, trading_period, indicator_func, strategy_func, window, signal, *, fee_bps=None)`.
- Computes `pnl`, `cumu`, `dd` columns in-place on `data`.
- Transaction cost defaults to 5 bps (0.05%); configurable via `fee_bps` kwarg.
- Key metrics: `get_sharpe_ratio()`, `get_max_drawdown()`, `get_calmar_ratio()`.
- Also computes buy-and-hold benchmark columns.

### param_opt.py — Grid Search
- `ParametersOptimization(data, trading_period, indicator_func, strategy_func)`.
- `optimize(window_tuple, signal_tuple)` → generator yielding `(window, signal, sharpe)`.

## Adding a New Indicator

1. Add method to `TechnicalAnalysis` in `ta.py` — input: `period`, output: Series.
2. Verify it works with `Performance` (must accept `indicator_func(window)` signature).
3. Add unit tests in `tests/unit/test_ta.py`.
4. Test in integration via `tests/integration/test_backtest_pipeline.py`.

## Adding a New Strategy

1. Add static method to `Strategy` in `strat.py` — signature: `(data_col, signal) → numpy array`.
2. Output must be float array of `{-1, 0, 1}`, NaN where input is NaN.
3. Add unit tests in `tests/unit/test_strat.py`.
