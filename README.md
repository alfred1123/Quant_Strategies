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
cp .env.example .env       # then fill in QUANTDB_PASSWORD, etc.

# 2. Start the AWS SSM tunnel to shared Aurora (5433 -> RDS:5432)
./scripts/appctl.sh dev tunnel start

# 3. Start backend (uvicorn) + frontend (vite)
./scripts/appctl.sh dev start
```

Open `http://localhost:5173`. Login, then configure and run backtests from the UI.

**Optional — work offline against a local Postgres** (no SSM tunnel, no shared DB):

```bash
sudo apt install -y postgresql-17 docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # log out/in
./scripts/dbctl.sh reset && ./scripts/dbctl.sh dump && ./scripts/dbctl.sh restore
echo 'DB_TARGET=local' >> .env
./scripts/appctl.sh dev start    # also brings up Redis + queue worker via docker-compose.dev.yml
```

See [docs/architecture/dev-vs-prod.md](docs/architecture/dev-vs-prod.md#optional-point-dev-at-a-local-postgres) for details. Full dump/restore guide: [docs/guides/database-dump-restore.md](docs/guides/database-dump-restore.md).

**Production:** The app is deployed at `http://52.221.3.230/` via GitHub Actions CI/CD.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Tested on 3.12.3 |
| Node.js 24+ | Managed via nvm — `setup.sh` installs from `.nvmrc` |
| PostgreSQL 17 | Shared Aurora via `localhost:5433` (AWS SSM port-forward), or local install on `:5432` (opt-in via `DB_TARGET=local`) |
| Docker + compose v2 | Only needed for `DB_TARGET=local` (runs Redis + queue worker) or for the prod stack |

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
| `MAX_CONCURRENT_WORKERS` | Optional | Backtest worker subprocesses per `worker_loop` (default `1`) |

**Yahoo Finance requires no API key** — it is the default data source.

### Backtest queue worker (Docker)

The **[backtest queue](docs/design/backtest-queue.md)** runs as a long-lived
Python daemon (`quant.queue.worker_loop`) that claims `QUEUED` rows from
`BT.QUEUE` and spawns one `python -m quant.queue.worker <queue_id>`
subprocess per job. To run it in a container:

```bash
# .env must include working QUANTDB_* credentials and REDIS_URL
# (default in compose: redis://redis:6379)
docker compose up redis worker
docker compose logs -f worker
```

FastAPI publishes REFDATA into Redis on boot, so start the API container
before (or alongside) the worker. The HTTP surface lives on the API
container at `/api/v1/backtest/jobs/*` — there is no separate coordinator port.

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
