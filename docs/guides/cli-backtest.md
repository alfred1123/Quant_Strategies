# CLI Backtest

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

# Sweep multiple indicators and strategies in grid search
python main.py --indicator bollinger sma rsi --strategy momentum reversion

# Stochastic oscillator
python main.py --indicator stochastic --strategy momentum

# Optimize over both price and volume
python main.py --factor price volume

# Custom grid search bounds
python main.py --win-min 10 --win-max 60 --win-step 10 --sig-min 0.5 --sig-max 2.0

# Custom output directory
python main.py --outdir /tmp/results
```

## All CLI Options

Run `python main.py --help` for the full list.

| Flag | Default | Description |
|---|---|---|
| `--symbol` | `BTC-USD` | Yahoo Finance ticker |
| `--start` | `2016-01-01` | Backtest start date |
| `--end` | `2026-04-01` | Backtest end date |
| `--asset` | `crypto` | `crypto` (365 days/year) or `equity` (252 trading days/year) |
| `--indicator` | `bollinger` | `bollinger`, `sma`, `ema`, `rsi`, `stochastic` — accepts multiple |
| `--strategy` | `momentum` | `momentum` or `reversion` — accepts multiple |
| `--factor` | `price` | `price`, `volume`, or both |
| `--window` | `20` | Indicator window for single backtest |
| `--signal` | `1.0` | Signal threshold for single backtest |
| `--no-grid` | `false` | Skip parameter optimization |
| `--win-min/max/step` | `5/100/5` | Grid search window range |
| `--sig-min/max/step` | `0.25/2.50/0.25` | Grid search signal range |
| `--outdir` | `../results` | Output directory for CSVs and heatmap |
| `--walk-forward` | `false` | Run walk-forward overfitting test |
| `--split` | `0.5` | In-sample ratio for walk-forward split (0.0–1.0) |

## Output Files

Saved to `results/` by default:

| File | Contents |
|---|---|
| `perf_<symbol>_<indicator>.csv` | Daily PnL, cumulative returns, drawdown, positions |
| `opt_<symbol>_<indicator>.csv` | Grid search results (window, signal, sharpe) |
| `heatmap_<symbol>_<indicator>.png` | Sharpe ratio heatmap |
| `wf_<symbol>_<indicator>.csv` | Walk-forward in-sample vs out-of-sample comparison |

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
