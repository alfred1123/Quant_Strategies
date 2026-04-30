# CLI Backtest

The CLI runs **single-symbol, single-indicator, single-strategy** backtests with optional grid search and walk-forward analysis. Multi-factor backtests (combining indicators with AND/OR/FILTER conjunctions) are only available via the API/web UI.

Run from `src/`:

```bash
cd src

# Default: BTC-USD, Bollinger + momentum, full grid search
python main.py

# Quick single backtest (skip grid search)
python main.py --no-grid

# Equity backtest
python main.py --symbol AAPL --asset equity --window 50 --signal 1.5

# Custom date range
python main.py --symbol ETH-USD --start 2020-01-01 --end 2026-01-01

# Different indicator + strategy
python main.py --indicator sma --strategy reversion

# Custom grid search bounds
python main.py --win-min 10 --win-max 60 --win-step 10 --sig-min 0.5 --sig-max 2.0

# Walk-forward overfitting test
python main.py --walk-forward --split 0.7

# Verbose / DEBUG logging
python main.py -v

# Custom transaction fee (basis points)
python main.py --fee 10

# Custom output directory
python main.py --outdir /tmp/results
```

## All CLI Options

Run `python main.py --help` for the full list.

| Flag | Default | Description |
|---|---|---|
| `--symbol` | `BTC-USD` | Yahoo Finance ticker / internal CUSIP |
| `--start` | `2016-01-01` | Backtest start date (YYYY-MM-DD) |
| `--end` | `2026-04-01` | Backtest end date (YYYY-MM-DD) |
| `--asset` | `crypto` | `crypto` (365 days/year) or `equity` (252 trading days/year) |
| `--indicator` | `bollinger` | One of: `bollinger`, `sma`, `ema`, `rsi` |
| `--strategy` | `momentum` | One of: `momentum`, `reversion` |
| `--window` | `20` | Indicator window for single backtest |
| `--signal` | `1.0` | Signal threshold for single backtest |
| `--fee` | `5.0` | Transaction fee in basis points |
| `--no-grid` | `false` | Skip parameter optimization |
| `--win-min/max/step` | `5/100/5` | Grid search window range |
| `--sig-min/max/step` | `0.25/2.50/0.25` | Grid search signal range |
| `--walk-forward` | `false` | Run walk-forward overfitting test |
| `--split` | `0.5` | In-sample ratio for walk-forward split (0.0–1.0) |
| `--outdir` | `../results` | Output directory for CSVs and heatmap |
| `--verbose`, `-v` | `false` | Enable DEBUG-level logging |

## Output Files

Saved to `results/` by default. The `<tag>` suffix is `<symbol-without-dashes-lower>_<indicator>` (e.g. `btcusd_bollinger`).

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
python main.py --walk-forward

# 70% in-sample / 30% out-of-sample
python main.py --walk-forward --split 0.7
```

**Overfitting ratio:** `1 − (OOS Sharpe / IS Sharpe)`. Values near 0 indicate robust parameters; values near 1 indicate the strategy performs much worse out-of-sample.
