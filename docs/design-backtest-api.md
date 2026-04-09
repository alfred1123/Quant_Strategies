# Backtest API — Architecture & Concepts

## Overview

The Backtest API is a **FastAPI** server (`api/`) that exposes the Python backtest pipeline (`src/`) as HTTP endpoints. It lets a React/TypeScript frontend (or any HTTP client) run backtests, parameter optimizations, and walk-forward tests without touching Python directly.

```
┌──────────────┐       HTTP/JSON        ┌──────────────────────────────────────┐
│   Frontend   │ ◄────────────────────► │          FastAPI  (api/)             │
│  React / TS  │   localhost:8000       │                                      │
│  :5173       │                        │  routers/        services/           │
└──────────────┘                        │  ┌───────────┐  ┌─────────────────┐  │
                                        │  │ backtest  │─►│ backtest svc    │  │
                                        │  │ refdata   │  │ refdata_cache   │  │
                                        │  └───────────┘  └────────┬────────┘  │
                                        └──────────────────────────┼───────────┘
                                                                   │ imports
                                                          ┌────────▼────────┐
                                                          │    src/ pipeline │
                                                          │  data → strat   │
                                                          │  → perf → opt   │
                                                          │  → walk_forward │
                                                          └────────┬────────┘
                                                                   │
                                                          ┌────────▼────────┐
                                                          │  Yahoo Finance  │
                                                          │  (price data)   │
                                                          └─────────────────┘

                                        ┌─────────────────────────────────────┐
                                        │  PostgreSQL (quantdb)               │
                                        │  REFDATA schema — cached at startup │
                                        │  via SSM tunnel → localhost:5433    │
                                        └─────────────────────────────────────┘
```

## Startup Lifecycle

1. **`uvicorn api.main:app --reload --port 8000`** launches the server.
2. The `lifespan` context manager runs on startup:
   - Calls `setup_logging()` (once, as the entry point).
   - Creates a `RefDataCache` with the PostgreSQL connection string.
   - Calls `cache.load_all()` — fetches all REFDATA tables into an in-process Python dict. If the DB is unreachable, the server still starts but REFDATA endpoints return empty.
   - Stores the cache on `app.state.refdata_cache` so routers can access it.
3. CORS middleware allows the Vite dev server (`localhost:5173`).
4. Two routers are mounted under `/api/v1`:
   - **`/api/v1/backtest/*`** — backtest operations
   - **`/api/v1/refdata/*`** — reference data for UI dropdowns

## Endpoints

### Health

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Returns `{"status": "ok"}` — basic liveness check |

### Backtest (`/api/v1/backtest`)

All backtest endpoints are **POST** — they accept a JSON body and return computed results.

| Method | Path | Request Schema | Response Schema | What it does |
|--------|------|---------------|-----------------|-------------|
| POST | `/backtest/data` | `DataRequest` | `DataResponse` | Fetch historical price data from Yahoo Finance |
| POST | `/backtest/optimize` | `OptimizeRequest` | `OptimizeResponse` | Run grid-search parameter optimization (single or multi-factor) |
| POST | `/backtest/performance` | `PerformanceRequest` | `PerformanceResponse` | Run a single backtest with fixed window/signal and return metrics + equity curve |
| POST | `/backtest/walk-forward` | `WalkForwardRequest` | `WalkForwardResponse` | Run walk-forward overfitting test (train/test split) |

### REFDATA (`/api/v1/refdata`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/refdata/{table_name}` | Return cached rows for a REFDATA table (e.g. `indicator`, `signal_type`, `asset_type`) |
| POST | `/refdata/refresh` | Reload all REFDATA tables from PostgreSQL (admin operation) |

## Request/Response Flow — Example: Optimization

```
Frontend                    Router                  Service                 Pipeline
   │                          │                       │                       │
   │  POST /backtest/optimize │                       │                       │
   │  { symbol, start, end,   │                       │                       │
   │    indicator, strategy,   │                       │                       │
   │    window_range, ... }    │                       │                       │
   │─────────────────────────►│                       │                       │
   │                          │  svc.run_optimize()   │                       │
   │                          │──────────────────────►│                       │
   │                          │                       │  YahooFinance.get_historical_price()
   │                          │                       │──────────────────────►│
   │                          │                       │◄──────────────────────│ DataFrame
   │                          │                       │                       │
   │                          │                       │  Build StrategyConfig │
   │                          │                       │  ParametersOptimization.optimize()
   │                          │                       │──────────────────────►│
   │                          │                       │◄──────────────────────│ param_perf DF
   │                          │                       │                       │
   │                          │                       │  Convert DF → dicts   │
   │                          │◄──────────────────────│  OptimizeResponse     │
   │◄─────────────────────────│  JSON response        │                       │
```

## Three-Layer Architecture

### 1. Routers (`api/routers/`)

Thin HTTP layer. Each endpoint:
- Validates the Pydantic request model automatically.
- Delegates to the corresponding service function.
- Catches exceptions and returns appropriate HTTP errors.

### 2. Services (`api/services/`)

Business logic bridge between HTTP and the pipeline:

- **`backtest.py`** — Converts Pydantic models → `StrategyConfig` and pipeline calls → Pydantic responses. Handles:
  - `_fetch_df()` — fetches data via `YahooFinance` and returns a pipeline-ready DataFrame.
  - `_build_single_config()` / `_build_multi_config()` — constructs `StrategyConfig` (with optional `SubStrategy` list for multi-factor).
  - `_resolve_signal_func()` — maps strategy name strings (e.g. `"momentum_const_signal"`) to actual Python functions.
  - `_extract_optuna_plots()` — serializes Optuna visualizations as Plotly JSON for the frontend.

- **`refdata_cache.py`** — In-process cache for REFDATA tables. One `SELECT * FROM refdata.<table>` per table at startup, stored as `list[dict]`. No TTL — refresh via admin endpoint.

### 3. Pipeline (`src/`)

The existing backtest engine, imported directly by the service layer:

| Module | Role |
|--------|------|
| `data.py` | Data sources — `YahooFinance`, `FutuOpenD`, `Glassnode`, `AlphaVantage` |
| `strat.py` | `TechnicalAnalysis` (indicators: Bollinger, SMA, EMA, RSI), `SignalDirection` (momentum/reversion signals), `StrategyConfig` / `SubStrategy` |
| `perf.py` | `Performance` — computes returns, Sharpe, drawdown, Calmar, equity curves |
| `param_opt.py` | `ParametersOptimization` — Optuna-based grid/TPE search over window × signal space |
| `walk_forward.py` | `WalkForward` — train/test split, optimize in-sample, evaluate out-of-sample, overfitting ratio |

## Single-Factor vs Multi-Factor

The API supports two **modes**:

### Single-Factor (`mode: "single"`)
One indicator + one strategy + one window/signal pair.
```json
{
  "mode": "single",
  "indicator": "get_bollinger_band",
  "strategy": "momentum_const_signal",
  "window_range": { "min": 5, "max": 100, "step": 5 },
  "signal_range": { "min": 0.25, "max": 2.5, "step": 0.25 }
}
```

### Multi-Factor (`mode: "multi"`)
Multiple indicators combined with a conjunction (`AND` / `OR`). Each factor has its own indicator, strategy, data column, and parameter ranges.
```json
{
  "mode": "multi",
  "conjunction": "AND",
  "factors": [
    {
      "indicator": "get_bollinger_band",
      "strategy": "momentum_const_signal",
      "data_column": "price",
      "window_range": { "min": 10, "max": 50, "step": 5 },
      "signal_range": { "min": 0.5, "max": 2.0, "step": 0.5 }
    },
    {
      "indicator": "get_rsi",
      "strategy": "reversion_const_signal",
      "data_column": "price",
      "window_range": { "min": 7, "max": 28, "step": 7 },
      "signal_range": { "min": 20, "max": 40, "step": 5 }
    }
  ]
}
```

## REFDATA — Single Source of Truth

UI dropdowns (indicators, strategies, asset types, etc.) are populated from `REFDATA` tables in PostgreSQL, **not** hardcoded in the frontend or API.

| Dropdown | Table | Key Columns |
|----------|-------|-------------|
| Indicator | `refdata.indicator` | `DISPLAY_NAME`, `METHOD_NAME`, grid defaults (`WIN_MIN`...`SIG_STEP`) |
| Strategy | `refdata.signal_type` | `DISPLAY_NAME`, `FUNC_NAME` |
| Asset type | `refdata.asset_type` | `DISPLAY_NAME`, `TRADING_PERIOD` |
| Data column | `refdata.data_column` | `DISPLAY_NAME`, `COLUMN_NAME` |
| Conjunction | `refdata.conjunction` | `DISPLAY_NAME`, `NAME` |

The cache is loaded once at startup and refreshable via `POST /api/v1/refdata/refresh`.

## Database Connectivity

```
Developer Machine                        AWS
─────────────────                        ───
localhost:5433  ──── SSM Port Forward ──── RDS PostgreSQL (quantdb)
                     (VS Code task)        quantdb-cluster.*.rds.amazonaws.com:5432
```

- SSM port-forward runs as a VS Code background task (`SSM Port Forward (quantdb:5433)`).
- Connection requires `sslmode=require` (enforced by RDS `pg_hba.conf`).
- Credentials come from env vars: `QUANTDB_HOST`, `QUANTDB_PORT`, `QUANTDB_USERNAME`, `QUANTDB_PASSWORD` (set in `.env`).

## Running the API

```bash
# From project root
source .env                    # Load DB credentials
source env/bin/activate        # Activate Python venv
uvicorn api.main:app --reload --port 8000

# Verify
curl http://localhost:8000/health
# → {"status":"ok"}

# Swagger UI
open http://localhost:8000/docs
```
