# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator). Parameter search scores every cell when the grid fits the budget in `CONFIG.BACKTEST_SEARCH`, and samples distinct cells after that (decision #91).

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

**Wiki:** [alfred1123.github.io/Quant_Strategies](https://alfred1123.github.io/Quant_Strategies/) — full architecture, guides, design docs, and decisions log. Run `mkdocs serve` to preview locally at `http://localhost:8001`.

---

## Quick Start

```bash
git clone https://github.com/alfred1123/Quant_Strategies.git
cd Quant_Strategies
./setup.sh
cp .env.example .env
```

Setup, run modes, and the first local database copy: [Getting Started](docs/getting-started.md). Dump and restore: [Database dump and restore](docs/guides/database-dump-restore.md).

Open `http://localhost:5173` after `./scripts/appctl.sh dev start`.

**Production:** [https://algodaemon.com](https://algodaemon.com)

---

## Prerequisites

[Getting Started — Prerequisites](docs/getting-started.md#prerequisites).

---

## Environment variables

Names, which are required, and where each default lives: [Environment variables](docs/env-vars.md). On a laptop, leave `QUANTDB_PORT` unset.

### Backtest queue worker

The [backtest queue](docs/design/backtest-queue.md) is a long-lived `quant.queue.worker_loop` that claims `QUEUED` rows from `BT.QUEUE` and spawns one `python -m quant.queue.worker <queue_id>` subprocess per job. How to start it: [Getting Started — Docker](docs/getting-started.md#docker).

## Repository Layout

```
Quant_Strategies/
├── quant/                     # Pipeline + FastAPI backend (api/, data/, refdata/, strategy/, queue/, cli)
├── frontend/                  # React + TypeScript SPA (MUI, TanStack Query, Plotly)
├── tests/                     # Unit, integration, and e2e tests
├── docs/                      # MkDocs Material wiki
├── db/liquidbase/             # Liquibase changelogs (per-schema deployment)
├── config/db-targets.json     # what DB_TARGET=local / prod mean (host, port, TLS)
├── config/scheduler/          # EventBridge schedules for recurring tasks
├── docker-compose.yml         # prod base — redis, api, worker, nginx
├── docker-compose.prod.yml    # prod overrides (APP_ENV, USE_SSM, COOKIE_SECURE)
├── docker-compose.dev.yml     # dev support stack — redis + worker only (DB_TARGET=local)
├── docker/                    # Docker + Nginx configs
├── scripts/appctl.sh          # dev/prod lifecycle (uvicorn, vite, tunnel, compose)
├── scripts/dbctl.sh           # local Postgres dump/restore/reset
├── .github/workflows/         # CI/CD (tests + deploy)
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
python -m quant.cli                          # Default: BTC-USD, Bollinger + momentum
python -m quant.cli --no-grid                # Skip grid search
python -m quant.cli --symbol AAPL --asset equity --window 50 --signal 1.5
python -m quant.cli --walk-forward --split 0.7
```

Run `python -m quant.cli --help` for all options. See [CLI Backtest guide](https://alfred1123.github.io/Quant_Strategies/guides/cli-backtest/) for full documentation.

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
