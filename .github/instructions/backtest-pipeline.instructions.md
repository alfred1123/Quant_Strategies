---
description: "Use when modifying or extending the backtest pipeline: data sources, technical indicators, strategies, performance metrics, or parameter optimization. Covers module interfaces and data flow."
applyTo: "src/**"
---
# Backtest Pipeline Rules

## Data Flow

```
data.py → ta.py → strat.py → perf.py → param_opt.py → walk_forward.py
```

All modules are orchestrated by `main.py`. Imports are **relative** to the `src/` package.

## StrategyConfig

`StrategyConfig` (in `strat.py`) is a frozen dataclass that packages the strategy identity — reusable across backtest and live trading:

```python
from strat import StrategyConfig, FactorConfig, Strategy

# Single-factor (backward-compatible)
config = StrategyConfig(
    factors=(FactorConfig('price', 'get_bollinger_band'),),
    strategy_func=Strategy.momentum_const_signal,
    trading_period=365,                    # 365 crypto, 252 equity
)

# Multi-factor conjunction
config = StrategyConfig(
    factors=(
        FactorConfig('price', 'get_bollinger_band'),
        FactorConfig('volume', 'get_bollinger_band'),
    ),
    strategy_func=Strategy.momentum_const_signal,
    trading_period=365,
    conjunction='AND',  # 'AND' | 'OR'
)
```

- `FactorConfig(column, indicator_name)` — defines a single factor (data column + indicator method).
- `conjunction` defaults to `'AND'`.
- Window and signal are optimization parameters, NOT part of config.

**Transaction fees are NOT part of the config** — they vary by platform and are passed separately via `fee_bps`.

All pipeline constructors accept `StrategyConfig` directly:
- `Performance(data, config, windows, signals, *, fee_bps=None)` — windows/signals are tuples (one per factor), or scalars for single-factor.
- `ParametersOptimization(data, config, *, fee_bps=None)`
- `WalkForward(data, split_ratio, config, *, fee_bps=None)`

Each constructor creates `TechnicalAnalysis` internally — callers pass raw data, not `ta.data`.

## Module Interfaces

### data.py — Data Sources
- Each source is a class (`FutuOpenD`, `Glassnode`, `AlphaVantage`, `YahooFinance`).
- Returns a DataFrame. Glassnode, AlphaVantage, and YahooFinance return columns `['t', 'v']`. YahooFinance also returns `'volume'`.
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
- `StrategyConfig` frozen dataclass — see **StrategyConfig** section above.
- `FactorConfig(column, indicator_name)` — frozen dataclass for a single factor.
- `combine_positions(factor_positions, conjunction)` — combines per-factor positions via AND/OR.

### perf.py — Performance Metrics
- `Performance(data, config, windows, signals, *, fee_bps=None)`.
- `windows` and `signals` are tuples (one per factor), or scalars for single-factor backward compat.
- Creates `TechnicalAnalysis` per-factor internally, resolves indicators from `config.factors`.
- Uses `combine_positions()` for multi-factor conjunction.
- `warmup = max(windows)` for metric slicing.

### param_opt.py — Grid Search
- `ParametersOptimization(data, config, *, fee_bps=None)`.
- `optimize_grid(param_grid)` — sweeps N-dimensional parameter grid.
  - Single-factor: `{'window': (...), 'signal': (...)}`.
  - Multi-factor indexed: `{'window_0': (...), 'signal_0': (...), 'window_1': (...), 'signal_1': (...)}`.
  - Optional: `factor`, `indicator`, `strategy` dimensions.
- `optimize(window_tuple, signal_tuple, factor_columns=None)` — backward-compatible wrapper.

### walk_forward.py — Overfitting Detection
- `WalkForward(data, split_ratio, config, *, fee_bps=None)`.
- `run(window_tuple, signal_tuple)` or `run(param_grid={...})` for multi-factor.
- Returns `WalkForwardResult` with per-factor best windows/signals.

## Adding a New Indicator

1. Add method to `TechnicalAnalysis` in `ta.py` — input: `period`, output: Series.
2. Verify it works with `Performance` (must accept `indicator_func(window)` signature).
3. Add unit tests in `tests/unit/test_ta.py`.
4. Test in integration via `tests/integration/test_backtest_pipeline.py`.

## Adding a New Strategy

1. Add static method to `Strategy` in `strat.py` — signature: `(data_col, signal) → numpy array`.
2. Output must be float array of `{-1, 0, 1}`, NaN where input is NaN.
3. Add unit tests in `tests/unit/test_strat.py`.
