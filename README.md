# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator) and optimized via N-dimensional grid search over parameter space.

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

**Wiki:** [alfred1123.github.io/Quant_Strategies](https://alfred1123.github.io/Quant_Strategies/) — full architecture, guides, design docs, and decisions log. Run `mkdocs serve` to preview locally at `http://localhost:8001`.

---

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/alfred1123/Quant_Strategies.git
cd Quant_Strategies
./setup.sh

# 2. Start the FastAPI backend (Terminal 1)
source env/bin/activate
uvicorn api.main:app --reload

# 3. Start the React frontend (Terminal 2)
cd frontend && npm run dev
```

Open `http://localhost:5173`. Login, then configure and run backtests from the UI.

**Production:** The app is deployed at `http://52.221.3.230/` via GitHub Actions CI/CD.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Tested on 3.12.3 |
| Node.js 24+ | Managed via nvm — `setup.sh` installs from `.nvmrc` |
| PostgreSQL 17 | Connected via `localhost:5433` (AWS SSM port-forward) |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in any keys you need:

```bash
cp .env.example .env
```

| Variable | Required? | Description |
|---|---|---|
| `QUANTDB_HOST` | Yes | PostgreSQL host (default: `localhost`) |
| `QUANTDB_PORT` | Yes | PostgreSQL port (default: `5433`) |
| `QUANTDB_USERNAME` | Yes | Database user |
| `QUANTDB_PASSWORD` | Yes | Database password |
| `ALPHAVANTAGE_API_KEY` | Optional | Free key from [alphavantage.co](https://www.alphavantage.co/support/#api-key) |
| `GLASSNODE_API_KEY` | Optional | On-chain crypto metrics |
| `FUTU_HOST` / `FUTU_PORT` | Optional | Futu OpenD gateway for HK/US equities |

**Yahoo Finance requires no API key** — it is the default data source.

---

## Repository Layout

```
Quant_Strategies/
├── src/                 # Backtesting pipeline (data, strat, perf, param_opt, main)
├── api/                 # FastAPI backend — backtest + auth endpoints
├── frontend/            # React + TypeScript SPA (MUI, TanStack Query, Plotly)
├── tests/               # Unit, integration, and e2e tests
├── docs/                # MkDocs Material wiki
├── db/liquidbase/       # Liquibase changelogs (per-schema deployment)
├── docker/              # Docker + Nginx configs
├── .github/workflows/   # CI/CD (tests + deploy)
└── backup/deco/         # Decommissioned Bybit scripts (reference only)
```

See the [wiki](https://alfred1123.github.io/Quant_Strategies/) for detailed architecture, database schema, API reference, and contributor guides.

---

## Running Tests

```bash
# Backend (from project root)
python -m pytest tests/ -v

# Frontend
cd frontend && npm test
```

---

## CLI Backtest

For running backtests without the UI:

```bash
cd src
python main.py                          # Default: BTC-USD, Bollinger + momentum
python main.py --no-grid                # Skip grid search
python main.py --symbol AAPL --asset equity --window 50 --signal 1.5
python main.py --walk-forward --split 0.7
```

Run `python main.py --help` for all options. See [CLI Backtest guide](https://alfred1123.github.io/Quant_Strategies/guides/cli-backtest/) for full documentation.

---

## Key Documentation

| Topic | Link |
|---|---|
| Architecture overview | [Pipeline](https://alfred1123.github.io/Quant_Strategies/architecture/pipeline/) |
| FastAPI backend | [API docs](https://alfred1123.github.io/Quant_Strategies/architecture/api/) |
| React frontend | [Frontend docs](https://alfred1123.github.io/Quant_Strategies/architecture/frontend/) |
| Database schema | [Database](https://alfred1123.github.io/Quant_Strategies/architecture/database/) |
| Login & authentication | [Login design](https://alfred1123.github.io/Quant_Strategies/design/login/) |
| Indicators & strategies | [Guide](https://alfred1123.github.io/Quant_Strategies/guides/indicators-strategies/) |
| Design decisions | [Decisions log](https://alfred1123.github.io/Quant_Strategies/decisions/) |
| Frontend code audit | [Audit](https://alfred1123.github.io/Quant_Strategies/design/frontend-audit/) |
