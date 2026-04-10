# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator) and optimized via N-dimensional grid search over parameter space.

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
| `QUANTDB_HOST` | Optional | PostgreSQL host (default: `localhost`). |
| `QUANTDB_PORT` | Optional | PostgreSQL port (default: `5433`). |
| `QUANTDB_USERNAME` | Optional | Database user for quantdb. |
| `QUANTDB_PASSWORD` | Optional | Database password. |

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
- **Indicator** — Bollinger Band (z-score), SMA, EMA, RSI, Stochastic Oscillator
- **Strategy** — Momentum or Reversion
- **Window / Signal** — parameters for single backtest
- **Grid search rows** — row-based configuration builder (see below)

**Full Analysis tab** (recommended — one-click end-to-end):
1. Configure grid search rows in the sidebar (each row = factor × indicator × strategy × window range × signal range)
2. Click **Run Full Analysis**
3. Grid search runs across all rows, producing a combined results table
4. Walk-forward overfitting test runs automatically on the first row's configuration
5. Interactive heatmap — select any parameter pair as axes, filter remaining dimensions
6. Select parameters to drill into: strategy performance metrics, cumulative return chart, drawdown chart
7. Overfitting ratio with color coding (green/yellow/red)
8. Download grid results, daily PnL, and walk-forward summary as CSV

**Row-based grid search configuration:**

The sidebar grid search section uses a **row-based builder**. Each row independently specifies:
- **Factor** — price or volume
- **Indicator** — Bollinger, SMA, EMA, RSI, or Stochastic Oscillator
- **Strategy** — Momentum or Reversion
- **Window range** — min, max, step
- **Signal range** — min, max, step

Click **➕ Add Row** to add more configurations. Each row runs as a separate sweep and results are combined into a single Sharpe heatmap with per-row metadata (factor, indicator, strategy) as filterable dimensions.

**Single Backtest tab:**
1. Set your parameters in the sidebar
2. Click **Run Backtest**
3. View strategy vs buy-and-hold performance metrics side by side
4. Interactive cumulative return chart and drawdown chart (Plotly — zoom, hover, pan)
5. Download daily PnL as CSV

**Parameter Optimization tab:**
1. Uses the same row-based grid from the sidebar
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

# Sweep multiple indicators and strategies in grid search
python main.py --indicator bollinger sma rsi --strategy momentum reversion

# Stochastic oscillator
python main.py --indicator stochastic --strategy momentum

# Optimize over both price and volume as the indicator factor
python main.py --factor price volume

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
| `--indicator` | `bollinger` | `bollinger`, `sma`, `ema`, `rsi`, `stochastic` — accepts multiple values (sweep in grid search) |
| `--strategy` | `momentum` | `momentum` or `reversion` — accepts multiple values (sweep in grid search) |
| `--factor` | `price` | `price`, `volume`, or both (sweep in grid search) |
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

### FastAPI Backend (`api/`)

A REST API that exposes the backtest pipeline for programmatic access and the TypeScript frontend (Phase 8).

**Start the server:**

```bash
# From project root (venv active)
uvicorn api.main:app --reload --port 8000
```

Interactive docs available at `http://localhost:8000/docs` once running.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/backtest/optimize` | Run parameter grid search (single or multi-factor). Returns top-10 results, Optuna plots, and best params. |
| `POST` | `/backtest/performance` | Run a single backtest at fixed params. Returns equity curve, metrics, and daily P&L. |
| `POST` | `/backtest/walk-forward` | Walk-forward overfitting test. Returns IS/OOS metrics, overfitting ratio, and full equity curve. |
| `GET`  | `/refdata/{table_name}` | Fetch a cached REFDATA table (e.g. `INDICATOR`, `SIGNAL_TYPE`, `ASSET_TYPE`). |
| `POST` | `/refdata/refresh` | Reload all REFDATA tables from the database without restarting the server. |

**Single vs multi-factor mode:**  
All backtest endpoints accept `"mode": "single"` or `"mode": "multi"` in the request body. Single mode takes flat `window_range`/`signal_range`; multi mode takes a `factors` list with per-factor ranges. The service layer dispatches automatically — no separate endpoints.

**REFDATA cache:**  
All REFDATA tables are loaded into an in-process dict at startup (`RefDataCache`). The cache is attached to `app.state` and passed to every service call. Refresh without restart via `POST /refdata/refresh`.

---

### Paper Trading with Futu OpenD

The **Trading** tab in the Streamlit dashboard lets you connect to a running Futu OpenD gateway and execute orders in paper (simulate) or live mode — directly from your backtest results.

#### Prerequisites

1. **Install Futu OpenD** — download from [futunn.com](https://www.futunn.com/download/openAPI) and install on your desktop (Windows/macOS).
2. **Launch Futu OpenD** — open the desktop app and log in. The gateway must be running whenever you trade.
3. **Enable API access** — in Futu OpenD settings, ensure the API server is enabled (default port: `11111`).
4. **Set env vars** — add to your `.env`:
   ```
   FUTU_HOST=127.0.0.1
   FUTU_PORT=11111
   ```
   If running on a remote server, use the IP of the machine running Futu OpenD and allow the port through the firewall.

#### Paper trading walkthrough

1. Launch the dashboard:
   ```bash
   cd src && streamlit run app.py
   ```
2. Go to the **Trading** tab.
3. Configure:
   - **Futu Symbol** — use Futu format: `US.AAPL`, `US.WEAT`, `HK.00700`
   - **Quantity** — number of shares per order
   - **Paper Trading** — toggle ON (enabled by default)
4. Click **Connect to Futu OpenD**. You should see a green "Connected (PAPER mode)" banner.
5. The **Account Overview** section shows your simulated account balance and any open positions.

#### Placing orders

**Manual orders:**
- Select **Side** (BUY/SELL), **Type** (MARKET/LIMIT), and optionally a **Limit Price**.
- Click **Place Order**. The order routes to Futu's paper trading environment.

**Strategy-driven orders:**
- Under **Apply Backtest Strategy**, set the **Window** and **Signal** parameters (pre-filled from the sidebar).
- Click **Generate Signal & Execute**. The dashboard:
  1. Runs the backtest pipeline on the latest data
  2. Reads the most recent position signal (LONG / SHORT / FLAT)
  3. Compares it to your current Futu position
  4. Places the required order(s) to match the signal — including closing opposing positions first

#### Visualising trades in the Futu app

Paper trades placed through the dashboard appear in the **Futu desktop app** (Futu NiuNiu / moomoo) in real time:

- **Portfolio** → **Paper Trading** tab shows your simulated positions, P&L, and market value.
- **Trade** → **Order History** shows all orders placed through the API, including status (filled, pending, cancelled).
- **Charts** — open any symbol's chart in Futu and your paper positions are overlaid as buy/sell markers. Use Futu's built-in technical analysis tools (SMA, Bollinger Bands, RSI, etc.) to cross-reference with your strategy's signals.
- **Alerts** — set price alerts in Futu to get notified when your strategy's signal levels are approached.

> **Tip:** Futu's paper trading environment simulates realistic fills during market hours. Outside trading hours, market orders will queue until the next session opens.

#### From Python (without the dashboard)

```python
from trade import FutuTrader

with FutuTrader(paper=True) as trader:
    # Place a market buy
    result = trader.place_order("US.AAPL", 10, "BUY")
    print(result)  # OrderResult(success=True, order_id='...', message='...')

    # Check positions
    print(trader.get_positions())

    # Apply a strategy signal directly
    trader.apply_signal("US.AAPL", signal_value=1, qty=10)  # go long

    # Cancel all open orders
    trader.cancel_all_orders()
```

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
│   ├── ta.py                # Technical analysis indicators (shim — logic in strat.py)
│   ├── strat.py             # TechnicalAnalysis, SignalDirection, StrategyConfig
│   ├── perf.py              # Performance metrics & PnL engine
│   ├── param_opt.py         # N-dimensional grid-search parameter optimization (OptimizeResult, ParametersOptimization)
│   ├── walk_forward.py      # Walk-forward overfitting test (WalkForward, WalkForwardResult)
│   ├── trade.py             # Futu OpenD paper/live trade execution
│   ├── log_config.py        # Centralised logging configuration
│   ├── main.py              # CLI entry point — configurable via argparse
│   └── app.py               # Streamlit web dashboard [DECO:STREAMLIT]
│
├── api/                     # FastAPI backend (Phase 7+8)
│   ├── main.py              # App factory — CORS, lifespan (REFDATA cache load), router registration
│   ├── routers/
│   │   ├── backtest.py      # POST /backtest/optimize, /backtest/performance, /backtest/walk-forward
│   │   └── refdata.py       # GET /refdata/{table_name}, POST /refdata/refresh
│   ├── schemas/
│   │   └── backtest.py      # Pydantic request/response models (RangeParam.to_values, single/multi modes)
│   └── services/
│       ├── backtest.py      # Service layer: _build_config, _build_param_ranges, run_optimize/performance/walk_forward
│       └── refdata_cache.py # RefDataCache — loads all REFDATA tables into memory at startup
│
├── tests/
│   ├── unit/                # Unit tests (mocked, fast)
│   ├── integration/         # Pipeline tests with synthetic data
│   └── e2e/                 # End-to-end tests hitting real APIs
│
├── .env                     # API keys (gitignored — copy from .env.example)
├── .env.example             # Template for API keys
├── results/                 # Output CSVs and heatmap PNGs (gitignored)
├── db/
│   ├── liquidbase/              # Liquibase changelogs (per-schema deployment)
│   │   ├── quantdb-changelog.xml    # Master — schema & extension creation only
│   │   ├── liquibase.properties     # Master properties (public schema tracking)
│   │   ├── core_admin/              # CORE_ADMIN tables + procedures
│   │   ├── refdata/                 # REFDATA tables + seed data
│   │   ├── bt/                      # BT tables + procedures
│   │   └── trade/                   # TRADE tables
│   └── sql/                         # Standalone SQL scripts
│
├── backup/
│   └── deco/                # Decommissioned Bybit live trading scripts
│
├── requirements.txt         # Python dependencies
├── pyproject.toml           # pytest configuration
└── setup.sh                 # Automated environment setup
```

### Database

The project uses **PostgreSQL 17** with Liquibase for schema management. Each schema is deployed independently with its own `databasechangelog` tracking table.

**Schemas:**

| Schema | Purpose |
|--------|--------|
| `CORE_ADMIN` | Logging infrastructure (`LOG_PROC_DETAIL` table, `CORE_INS_LOG_PROC` procedure) |
| `REFDATA` | Reference data (`APP`, `TICKER_MAPPING`, `INDICATOR`, `SIGNAL_TYPE`, etc.) + `SP_GET_ENUM` procedure for cache loading |
| `BT` | Backtest results (`STRATEGY`, `RESULT`, `API_REQUEST`, `API_REQUEST_PAYLOAD`) + insert procedures (`SP_INS_STRATEGY`, `SP_INS_RESULT`, `SP_INS_API_REQUEST`, `SP_INS_API_REQUEST_PAYLOAD`) |
| `TRADE` | Live trading tables (`DEPLOYMENT`, `LOG`, `TRANSACTION`) — procedures deferred |

**Deployment:**

```bash
# Source credentials
source .env

# Phase 0: create schemas + extensions
cd db/liquidbase && liquibase --defaults-file=liquibase.properties update

# Per-schema deployment (each has its own liquibase.properties)
cd core_admin && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../refdata  && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../bt       && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../trade    && source ../../../.env && liquibase --defaults-file=liquibase.properties update
```

See `.github/skills/liquibase/SKILL.md` for full conventions and pitfalls.

---

## Pipeline Architecture

```
data.py ──► strat.py ──► perf.py ──► param_opt.py ──► walk_forward.py
  │            │           │              │                  │
  │            │           │              │                  └─ Split data into in-sample / out-of-sample,
  │            │           │              │                     optimize on IS, evaluate on OOS, report
  │            │           │              │                     overfitting ratio
  │            │           │              │
  │            │           │              └─ N-dimensional grid search over param_grid
  │            │           │                 (window, signal, factor, indicator, strategy),
  │            │           │                 returns best Sharpe
  │            │           │
  │            │           └─ Computes PnL, cumulative return, drawdown,
  │            │              Sharpe, Calmar vs buy-and-hold benchmark
  │            │
  │            └─ TechnicalAnalysis: calculates indicator values (SMA, EMA, RSI,
  │               Bollinger Z, Stochastic) on the factor column.
  │               SignalDirection: generates position array {-1, 0, 1} from
  │               indicator vs threshold signal.
  │
  └─ Fetches daily close prices from YahooFinance (or AlphaVantage/Glassnode/FutuOpenD)
```

`main.py` orchestrates the full flow. `app.py` provides the same pipeline via an interactive Streamlit UI.

---

## Available Indicators & Strategies

**Indicators** (`strat.py` — `TechnicalAnalysis` class, all operate on the `factor` column):

| Method | Description |
|---|---|
| `get_sma(period)` | Simple Moving Average |
| `get_ema(period)` | Exponential Moving Average |
| `get_rsi(period)` | Relative Strength Index (0–100) |
| `get_bollinger_band(period)` | Bollinger Z-score: `(factor - SMA) / rolling_std` |
| `get_stochastic_oscillator(period)` | Stochastic %D — available in both CLI and dashboard |

**Signal Directions** (`strat.py` — `SignalDirection` class):

| Method | Long (+1) | Short (-1) | Flat (0) |
|---|---|---|---|
| `momentum_const_signal` | indicator > +signal | indicator < −signal | otherwise |
| `reversion_const_signal` | indicator < −signal | indicator > +signal | otherwise |

**StrategyConfig** (`strat.py`) — frozen dataclass packaging the strategy identity:

```python
from strat import StrategyConfig, SignalDirection

config = StrategyConfig(
    indicator_name="get_bollinger_band",                    # TechnicalAnalysis method name
    signal_func=SignalDirection.momentum_const_signal,      # signal generation function
    trading_period=365,                                     # 365 crypto, 252 equity
)

# All pipeline constructors accept config directly:
perf = Performance(data, config, window=20, signal=1.0, fee_bps=5.0)
opt  = ParametersOptimization(data, config, fee_bps=5.0)
wf   = WalkForward(data, split_ratio=0.5, config=config, fee_bps=5.0)

# N-dimensional grid search via optimize_grid():
param_grid = {'window': (10, 20, 50), 'signal': (0.5, 1.0, 1.5)}
for result in opt.optimize_grid(param_grid):
    print(result)  # {'window': 10, 'signal': 0.5, 'sharpe': 1.23, ...}
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
