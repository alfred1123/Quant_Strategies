# CLI Backtest

The CLI runs **single-symbol, single-indicator, single-strategy** backtests with optional grid search and walk-forward analysis. Multi-factor backtests (combining indicators with AND/OR/FILTER conjunctions) are only available via the API/web UI.

The indicator, strategy and asset-type names are the **REFDATA** names — `REFDATA.INDICATOR.NAME`, `REFDATA.SIGNAL_TYPE.NAME`, `REFDATA.ASSET_TYPE.NAME` — read from the Redis snapshot the API publishes at startup (`RedisRefData`, `REDIS_URL` from `.env`). The CLI holds no list of its own: a name that is not in the table is refused with the names that are, and the grid-search defaults are the indicator's `WIN_*` / `SIG_*` columns. Redis must therefore be reachable (the API has published once), the same requirement the web UI has.

Run from the project root:

```bash
# BTC-USD, Bollinger + momentum, grid search over the indicator's REFDATA defaults
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto

# Quick single backtest (skip grid search)
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --no-grid

# Equity backtest
python -m quant.cli --symbol AAPL --asset equity --indicator sma --strategy reversion --window 50 --signal 1.5

# Custom date range
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --symbol ETH-USD --start 2020-01-01 --end 2026-01-01

# Custom grid search bounds (override the REFDATA defaults)
python -m quant.cli --indicator sma --strategy momentum --asset crypto --win-min 10 --win-max 60 --win-step 10 --sig-min 0.5 --sig-max 2.0

# Walk-forward overfitting test
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --walk-forward --split 0.7

# Verbose / DEBUG logging
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto -v

# Perp taker fee (basis points); default is 10 (Bybit spot)
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --fee 5.5

# Custom output directory
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --outdir /tmp/results
```

## All CLI Options

Run `python -m quant.cli --help` for the full list.

| Flag | Default | Description |
|---|---|---|
| `--symbol` | `BTC-USD` | Yahoo Finance ticker / internal CUSIP |
| `--start` | `2016-01-01` | Backtest start date (YYYY-MM-DD) |
| `--end` | `2026-04-01` | Backtest end date (YYYY-MM-DD) |
| `--asset` | *required* | `REFDATA.ASSET_TYPE.NAME`; its `TRADING_PERIOD` is the Sharpe annualisation (seeded: `crypto` 365, `equity` 252) |
| `--indicator` | *required* | `REFDATA.INDICATOR.NAME` (seeded: `bollinger`, `sma`, `ema`, `rsi`) |
| `--strategy` | *required* | `REFDATA.SIGNAL_TYPE.NAME` (seeded: `momentum`, `reversion`). The band or bounded variant follows the indicator's `IS_BOUNDED_IND`, as in the UI. |
| `--window` | `20` | Indicator window for single backtest |
| `--signal` | `1.0` | Signal threshold for single backtest |
| `--fee` | `10.0` | Transaction fee in basis points (Bybit VIP-0 spot taker). Use `5.5` for USDT perp taker. |
| `--no-grid` | `false` | Skip parameter optimization |
| `--win-min/max/step` | indicator's `WIN_MIN/MAX/STEP` | Grid search window range, in **daily bars**. The UI scales these by bars-per-day when the cadence is not daily; the CLI has no interval flag. |
| `--sig-min/max/step` | indicator's `SIG_MIN/MAX/STEP` | Grid search signal range. An indicator whose row has no `SIG_*` must be given them explicitly. |
| `--walk-forward` | `false` | Run walk-forward overfitting test |
| `--split` | `0.5` | In-sample ratio for walk-forward split (0.0–1.0) |
| `--outdir` | `../results` | Output directory for CSVs and heatmap |
| `--verbose`, `-v` | `false` | Enable DEBUG-level logging |

## Output Files

Saved to `../results` by default (relative to the working directory). The `<tag>` suffix is `<symbol-without-dashes-lower>_<indicator>` (e.g. `btcusd_bollinger`).

| File | Contents |
|---|---|
| `perf_<tag>.csv` | Daily PnL, cumulative returns, drawdown, positions |
| `opt_<tag>.csv` | Grid search results (window, signal, sharpe) |
| `heatmap_<tag>.png` | Sharpe ratio heatmap |
| `wf_<tag>.csv` | Walk-forward in-sample vs out-of-sample comparison |

## Walk-Forward Overfitting Test

The walk-forward test splits data into **in-sample** (training) and **out-of-sample** (validation) periods:

```
|◄──────── 10 years of data ────────►|
|◄── in-sample (5y) ──►|◄── out-of-sample (5y) ──►|
   grid search here          test best params here
```

```bash
# Walk-forward with default 50/50 split
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --walk-forward

# 70% in-sample / 30% out-of-sample
python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --walk-forward --split 0.7
```

**Overfitting ratio:** `1 − (OOS Sharpe / IS Sharpe)`. Values near 0 indicate robust parameters; values near 1 indicate the strategy performs much worse out-of-sample.
