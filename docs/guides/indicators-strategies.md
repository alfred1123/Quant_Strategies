# Indicators & Strategies

!!! note "Scope"
    Indicators and strategies described here are available via the **API/web UI**. The **CLI** (`python main.py`) currently exposes a subset — see [CLI Backtest](cli-backtest.md) for the supported flags.

## Available Indicators

All indicators operate on the `factor` column (which is set to `price` or `volume` depending on the data column selection).

| Method | Description | Bounded? |
|---|---|---|
| `get_sma(period)` | Simple Moving Average | No |
| `get_ema(period)` | Exponential Moving Average | No |
| `get_rsi(period)` | Relative Strength Index (0–100) | Yes |
| `get_bollinger_band(period)` | Bollinger Z-score: `(factor - SMA) / rolling_std` | No |
| `get_stochastic_oscillator(period)` | Stochastic %D | Yes |

## Signal Directions

The backend automatically selects the correct signal variant (band vs bounded) based on the indicator's `IS_BOUNDED_IND` flag in REFDATA:

- **Band signals** — for zero-centered indicators (Bollinger, SMA, EMA)
- **Bounded signals** — for 0–100 indicators (RSI, Stochastic)

| Method | Indicator Type | Long (+1) | Short (-1) | Flat (0) |
|---|---|---|---|---|
| `momentum_band_signal` | Unbounded | indicator > +signal | indicator < −signal | otherwise |
| `reversion_band_signal` | Unbounded | indicator < −signal | indicator > +signal | otherwise |
| `momentum_bounded_signal` | Bounded (0–100) | indicator > signal | indicator < (100 − signal) | otherwise |
| `reversion_bounded_signal` | Bounded (0–100) | indicator < (100 − signal) | indicator > signal | otherwise |

## Indicator + Strategy Pairing

!!! warning "Not all combinations are meaningful"
    - **Bollinger z-score + momentum** works well — z-scores are centered around 0, matching ±signal thresholds
    - **SMA/EMA + momentum on raw prices** does not work — prices are always positive, so a low signal threshold always triggers long. Use Bollinger z-score or RSI instead.

## Conjunction Modes (Multi-Factor)

When combining multiple factors:

| Mode | Behaviour |
|------|-----------|
| **AND** | Position taken only when all factors agree on direction. Ties broken by percentile-rank strength. |
| **OR** | Position taken when any factor signals. Strongest signal wins (percentile-rank tiebreak). |
| **FILTER** | Factor 1 acts as a gate (must be non-zero); factor 2 provides the directional signal. |

## Trading Period

The `trading_period` parameter controls Sharpe ratio annualization:

- **Crypto**: `365` — markets trade 24/7/365
- **Equity**: `252` — NYSE/NASDAQ trading days per year

## Transaction Costs

`perf.py` applies **5 bps (0.05%) fee per unit of turnover** by default. Override via `--fee` in the CLI or the "Transaction fee" input in the dashboard.

## Data Source Behaviour

| Source | Rate Limit | Notes |
|---|---|---|
| Yahoo Finance | None | Unofficial scraper — may break. No API key needed. |
| AlphaVantage (free) | 1 req/sec, 25/day | Compact mode returns ~100 most recent trading days |
| Glassnode | Varies by tier | Requires paid plan for full history |
| Futu OpenD | N/A | Requires local desktop gateway running |

- `YahooFinance` lazy-imports `yfinance` (avoids import-time network calls), retry logic (3 attempts, 2s backoff)
- Results are cached with `@lru_cache` — clear with `.cache_clear()` if re-fetching
