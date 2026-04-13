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
from strat import StrategyConfig, SignalDirection, SubStrategy

# Legacy single-factor (backward compatible):
config = StrategyConfig(
    ticker="BTC-USD",
    indicator_name="get_bollinger_band",
    signal_func=SignalDirection.momentum_band_signal,
    trading_period=365,
)

# Single-factor with self-describing SubStrategy:
config = StrategyConfig.single(
    "BTC-USD", "get_bollinger_band",
    SignalDirection.momentum_band_signal, 365,
    window=20, signal=1.0,
)

# Multi-factor:
sub1 = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
sub2 = SubStrategy("get_rsi", "reversion_band_signal", 14, 0.5)
config = StrategyConfig(
    "AAPL", "get_sma", SignalDirection.momentum_band_signal, 252,
    conjunction="AND", substrategies=(sub1, sub2),
)
```

**Fields**: `ticker`, `indicator_name`, `signal_func`, `trading_period`, `strategy_id` (auto-UUID), `name`, `conjunction` ("AND"/"OR"), `substrategies` (tuple of `SubStrategy`).

**Transaction fees are NOT part of the config** — they vary by platform and are passed separately via `fee_bps`.

All pipeline constructors accept `StrategyConfig` directly:
- `Performance(data, config, window, signal, *, fee_bps=None)`
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
- `Strategy.momentum_band_signal(data_col, signal)` → numpy array of `{-1, 0, 1}`.
- `Strategy.reversion_band_signal(data_col, signal)` → inverse of momentum.
- These are effectively static methods (no `self` used).
- `StrategyConfig` frozen dataclass — see **StrategyConfig** section above.

### perf.py — Performance Metrics
- `Performance(data, config, window, signal, *, fee_bps=None)`.
- Creates `TechnicalAnalysis` internally and resolves the indicator from `config.indicator_name`.
- Computes `pnl`, `cumu`, `dd` columns in-place on `data`.
- Transaction cost defaults to 5 bps (0.05%); configurable via `fee_bps` kwarg.
- Key metrics: `get_sharpe_ratio()`, `get_max_drawdown()`, `get_calmar_ratio()`.
- Also computes buy-and-hold benchmark columns.

### param_opt.py — Grid Search
- `ParametersOptimization(data, config, *, fee_bps=None)`.
- `optimize(window_tuple, signal_tuple, factor_columns=None)` → generator.
  - Without `factor_columns`: yields `(window, signal, sharpe)` — backward compatible.
  - With `factor_columns` (e.g. `["price", "volume"]`): yields `(window, signal, factor, sharpe)`. For each factor, copies data and sets `data['factor'] = data[factor_col]` before computing performance.

### walk_forward.py — Overfitting Detection
- `WalkForward(data, split_ratio, config, *, fee_bps=None)`.
- `run(window_tuple, signal_tuple)` → `WalkForwardResult` with in-sample/out-of-sample metrics and overfitting ratio.

## Adding a New Indicator

1. Add method to `TechnicalAnalysis` in `ta.py` — input: `period`, output: Series.
2. Verify it works with `Performance` (must accept `indicator_func(window)` signature).
3. Add unit tests in `tests/unit/test_ta.py`.
4. Test in integration via `tests/integration/test_backtest_pipeline.py`.

## Adding a New Strategy

1. Add static method to `Strategy` in `strat.py` — signature: `(data_col, signal) → numpy array`.
2. Output must be float array of `{-1, 0, 1}`, NaN where input is NaN.
3. Add unit tests in `tests/unit/test_strat.py`.
