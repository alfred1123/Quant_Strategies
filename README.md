# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator) and optimized via grid search over parameter space.

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

---

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/alfred1123/Quant_Strategies.git
cd Quant_Strategies
./setup.sh                    # creates venv, installs deps, checks .env

# 2. Activate the virtual environment
source env/bin/activate

# 3. Launch the dashboard (no API key needed)
cd src && streamlit run app.py
```

Open the URL shown in the terminal (default: `http://localhost:8501`). The dashboard lets you configure everything from the sidebar — symbol, dates, indicator, strategy, parameters — and run backtests or grid search with one click.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Tested on 3.12.3 |
| pip | Used by `setup.sh` to install dependencies |
| Git | To clone the repo |
| Linux / macOS | Windows works but `setup.sh` is a bash script — run manually or use WSL |

---

## Setup

### Option A: Automated (recommended)

```bash
./setup.sh
```

This script:
1. Creates a virtual environment at `env/`
2. Upgrades pip
3. Installs all packages from `requirements.txt`
4. Checks that `.env` exists (exits with error if missing)

### Option B: Manual

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit with your keys
```

### Environment Variables

Copy the template and fill in any keys you need:

```bash
cp .env.example .env
```

| Variable | Required? | Description |
|---|---|---|
| `ALPHAVANTAGE_API_KEY` | Optional | Free key from [alphavantage.co](https://www.alphavantage.co/support/#api-key). Limited to 25 req/day. |
| `GLASSNODE_API_KEY` | Optional | On-chain crypto metrics. Only if you use the Glassnode data source. |
| `FUTU_HOST` / `FUTU_PORT` | Optional | Only if using Futu OpenD gateway for HK/US equities. |

**Yahoo Finance requires no API key** — it is the default and recommended data source for getting started.

---

## Usage

### Streamlit Dashboard (`app.py`) — Recommended

The easiest way to run backtests. Launch the interactive web dashboard:

```bash
cd src && streamlit run app.py
```

Open the URL printed in the terminal (default: `http://localhost:8501`).

**Sidebar controls:**
- **Symbol** — any Yahoo Finance ticker: `BTC-USD`, `AAPL`, `ETH-USD`, `SPY`, `^GSPC`
- **Date range** — start and end dates for the backtest
- **Asset type** — Crypto (365 days/year) or Equity (252 trading days/year)
- **Indicator** — Bollinger Band (z-score), SMA, EMA, RSI
- **Strategy** — Momentum or Reversion
- **Window / Signal** — parameters for single backtest
- **Grid search bounds** — window min/max/step and signal min/max/step

**Single Backtest tab:**
1. Set your parameters in the sidebar
2. Click **Run Backtest**
3. View strategy vs buy-and-hold performance metrics side by side
4. Interactive cumulative return chart and drawdown chart (Plotly — zoom, hover, pan)
5. Download daily PnL as CSV

**Parameter Optimization tab:**
1. Set grid search ranges in the sidebar
2. Click **Run Grid Search**
3. Progress bar shows completion status
4. View top-10 parameter combinations ranked by Sharpe ratio
5. Interactive heatmap (Sharpe by window × signal) — hover for exact values
6. Download full grid results as CSV

**Tips:**
- Data is cached — switching tabs or re-running with the same symbol/dates won't re-fetch
- For headless servers, add `--server.headless true` to suppress browser auto-open
- To use a different port: `streamlit run app.py --server.port 8502`

---

### CLI Backtest (`main.py`)

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

# Custom output directory
python main.py --outdir /tmp/results
```

All CLI options (run `python main.py --help`):

| Flag | Default | Description |
|---|---|---|
| `--symbol` | `BTC-USD` | Yahoo Finance ticker |
| `--start` | `2016-01-01` | Backtest start date |
| `--end` | `2026-04-01` | Backtest end date |
| `--asset` | `crypto` | `crypto` (365 days/year) or `equity` (252 trading days/year) |
| `--indicator` | `bollinger` | `bollinger`, `sma`, `ema`, `rsi` |
| `--strategy` | `momentum` | `momentum` or `reversion` |
| `--window` | `20` | Indicator window for single backtest |
| `--signal` | `1.0` | Signal threshold for single backtest |
| `--no-grid` | `false` | Skip parameter optimization |
| `--win-min/max/step` | `5/100/5` | Grid search window range |
| `--sig-min/max/step` | `0.25/2.50/0.25` | Grid search signal range |
| `--outdir` | `../results` | Output directory for CSVs and heatmap |
| `--walk-forward` | `false` | Run walk-forward overfitting test |
| `--split` | `0.5` | In-sample ratio for walk-forward split (0.0–1.0) |

**Output files** (saved to `results/` by default):

| File | Contents |
|---|---|
| `perf_<symbol>_<indicator>.csv` | Daily PnL, cumulative returns, drawdown, positions |
| `opt_<symbol>_<indicator>.csv` | Grid search results (window, signal, sharpe) |
| `heatmap_<symbol>_<indicator>.png` | Sharpe ratio heatmap |
| `wf_<symbol>_<indicator>.csv` | Walk-forward in-sample vs out-of-sample comparison |

### Walk-Forward Overfitting Test

The walk-forward test splits data into **in-sample** (training) and **out-of-sample** (validation) periods. It optimizes parameters on in-sample data via grid search, then evaluates the best parameters on out-of-sample data to detect overfitting.

**CLI:**

```bash
# Walk-forward with default 50/50 split
python main.py --walk-forward

# 70% in-sample / 30% out-of-sample
python main.py --walk-forward --split 0.7

# Combined with other options
python main.py --symbol AAPL --asset equity --indicator sma --walk-forward --split 0.6
```

**Dashboard:** The "Walk-Forward Test" tab in the Streamlit dashboard provides an interactive split ratio slider and displays:
- Best parameters found on in-sample data
- Side-by-side performance metrics (in-sample vs out-of-sample)
- Overfitting ratio with color coding (green < 0.3, yellow 0.3–0.5, red > 0.5)
- Cumulative return chart with a vertical line marking the split point

**Overfitting ratio:** `1 − (OOS Sharpe / IS Sharpe)`. Values near 0 indicate robust parameters; values near 1 indicate the strategy performs much worse out-of-sample.

---

### Running Tests

```bash
# All tests (from project root)
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# End-to-end tests (hit real APIs — requires network + API keys)
python -m pytest tests/e2e/ -v -m e2e

# Filter by name
python -m pytest tests/ -v -k "bollinger"
```

E2E tests are excluded by default (configured in `pyproject.toml`).

---

## Things to Be Aware Of

### Trading Period

The `trading_period` parameter controls how the Sharpe ratio is annualized:
- **Crypto**: use `365` — markets trade 24/7/365
- **Equity**: use `252` — NYSE/NASDAQ trading days per year

The CLI `--asset` flag sets this automatically. In code, set it via `StrategyConfig(trading_period=...)`.

### Indicator + Strategy Pairing

Not all combinations are meaningful:
- **Bollinger z-score + momentum** works well — z-scores are centered around 0, matching ±signal thresholds
- **SMA/EMA + momentum on raw prices** does not work — prices are always positive, so a low signal threshold always triggers long. Use Bollinger z-score or RSI instead for momentum strategies.

### API Rate Limits

| Source | Rate Limit | Daily Quota | Notes |
|---|---|---|---|
| Yahoo Finance | None | None | Unofficial scraper — may break without warning |
| AlphaVantage (free) | 1 req/sec | 25 req/day | Compact mode returns ~100 most recent trading days only |
| Glassnode | Varies by tier | Varies | Requires paid plan for full history |
| Futu OpenD | N/A | N/A | Requires local desktop gateway running |

### Data Source Behaviour

- `YahooFinance` lazy-imports `yfinance` inside the method (avoids import-time network calls) and has retry logic (3 attempts with 2s backoff).
- `YahooFinance`, `AlphaVantage`, and `Glassnode` return a DataFrame with columns `['t', 'v']` (date string, close price). `FutuOpenD` returns OHLCV columns.
- Results are cached with `@lru_cache` — clear with `.cache_clear()` if re-fetching.

### Transaction Costs

`perf.py` applies a **5 bps (0.05%) fee per unit of turnover** by default, deducted from PnL on every position change. Override via `--fee` in the CLI or the "Transaction fee" input in the dashboard.

### Virtual Environment

`env/` is gitignored — always recreate via `./setup.sh` or manually with `pip install -r requirements.txt`. Do not commit the venv.

---

## Repository Structure

```
Quant_Strategies/
├── src/                     # Backtesting pipeline
│   ├── data.py              # Data sources (YahooFinance, AlphaVantage, Glassnode, FutuOpenD)
│   ├── ta.py                # Technical analysis indicators
│   ├── strat.py             # Signal generation strategies + StrategyConfig dataclass
│   ├── perf.py              # Performance metrics & PnL engine
│   ├── param_opt.py         # Grid-search parameter optimization
│   ├── walk_forward.py      # Walk-forward overfitting test
│   ├── log_config.py        # Centralised logging configuration
│   ├── main.py              # CLI entry point — configurable via argparse
│   └── app.py               # Streamlit web dashboard
│
├── tests/
│   ├── unit/                # Unit tests (mocked, fast)
│   ├── integration/         # Pipeline tests with synthetic data
│   └── e2e/                 # End-to-end tests hitting real APIs
│
├── .env                     # API keys (gitignored — copy from .env.example)
├── .env.example             # Template for API keys
├── results/                 # Output CSVs and heatmap PNGs (gitignored)
├── db/                      # SQLite schema and migrations (planned)
├── backup/
│   └── deco/                # Decommissioned Bybit live trading scripts
│
├── requirements.txt         # Python dependencies
├── pyproject.toml           # pytest configuration
└── setup.sh                 # Automated environment setup
```

---

## Pipeline Architecture

```
data.py ──► ta.py ──► strat.py ──► perf.py ──► param_opt.py ──► walk_forward.py
  │            │           │           │              │                  │
  │            │           │           │              │                  └─ Split data into in-sample / out-of-sample,
  │            │           │           │              │                     optimize on IS, evaluate on OOS, report
  │            │           │           │              │                     overfitting ratio
  │            │           │           │              │
  │            │           │           │              └─ Grid search over (window, signal)
  │            │           │           │                 pairs, returns best Sharpe
  │            │           │           │
  │            │           │           └─ Computes PnL, cumulative return, drawdown,
  │            │           │              Sharpe, Calmar vs buy-and-hold benchmark
  │            │           │
  │            │           └─ Generates position array {-1, 0, 1} from indicator
  │            │              vs threshold signal
  │            │
  │            └─ Calculates indicator values (SMA, EMA, RSI, Bollinger Z,
  │               Stochastic) on the factor column
  │
  └─ Fetches daily close prices from YahooFinance (or AlphaVantage/Glassnode/FutuOpenD)
```

`main.py` orchestrates the full flow. `app.py` provides the same pipeline via an interactive Streamlit UI.

---

## Available Indicators & Strategies

**Indicators** (`ta.py` — all operate on the `factor` column):

| Method | Description |
|---|---|
| `get_sma(period)` | Simple Moving Average |
| `get_ema(period)` | Exponential Moving Average |
| `get_rsi(period)` | Relative Strength Index (0–100) |
| `get_bollinger_band(period)` | Bollinger Z-score: `(factor - SMA) / rolling_std` |
| `get_stochastic_oscillator(period)` | Stochastic %D (requires High/Low/Close columns — not available in dashboard) |

**Strategies** (`strat.py`):

| Method | Long (+1) | Short (-1) | Flat (0) |
|---|---|---|---|
| `momentum_const_signal` | indicator > +signal | indicator < −signal | otherwise |
| `reversion_const_signal` | indicator < −signal | indicator > +signal | otherwise |

**StrategyConfig** (`strat.py`) — frozen dataclass packaging the strategy identity:

```python
from strat import StrategyConfig, Strategy

config = StrategyConfig(
    indicator_name="get_bollinger_band",           # TechnicalAnalysis method name
    strategy_func=Strategy.momentum_const_signal,  # signal generation function
    trading_period=365,                            # 365 crypto, 252 equity
)

# All pipeline constructors accept config directly:
perf = Performance(data, config, window=20, signal=1.0, fee_bps=5.0)
opt  = ParametersOptimization(data, config, fee_bps=5.0)
wf   = WalkForward(data, split_ratio=0.5, config=config, fee_bps=5.0)
```

Transaction fees (`fee_bps`) are **not** part of the config — they vary by trading platform and are passed separately.

**Performance Metrics** (`perf.py` — computed for both strategy and buy-and-hold):

- Total Return, Annualized Return, Sharpe Ratio, Max Drawdown, Calmar Ratio

---

## Data Sources

| Source | API Key? | Asset Classes | Notes |
|---|---|---|---|
| **YahooFinance** | No | Equities, ETFs, indices, crypto | Free, 10+ years daily data. **Recommended for getting started.** |
| **AlphaVantage** | Yes (free) | Equities, crypto | 25 req/day, ~100 days per request (compact) |
| **Glassnode** | Yes (paid) | Crypto on-chain metrics | Historical price + on-chain factors |
| **Futu OpenD** | No (gateway) | HK & US equities | Requires local Futu desktop client running |
