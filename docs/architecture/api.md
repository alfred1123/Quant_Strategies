# FastAPI Backend

The `api/` directory contains the FastAPI application that serves the backtest pipeline as a REST API.

## Starting the Server

```bash
source env/bin/activate
uvicorn api.main:app --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/backtest/optimize` | Run parameter grid search (single or multi-factor). Returns top-10 results, Optuna plots, and best params. |
| `POST` | `/backtest/optimize/stream` | SSE-streamed optimization — sends `init`, `progress` (trial/total/best_sharpe), and `result` events in real time. |
| `POST` | `/backtest/performance` | Run a single backtest at fixed params. Returns equity curve, metrics, and daily P&L. |
| `POST` | `/backtest/walk-forward` | Walk-forward overfitting test. Returns IS/OOS metrics, overfitting ratio, and full equity curve. |
| `GET`  | `/refdata/{table_name}` | Fetch a cached REFDATA table (e.g. `indicator`, `signal_type`, `asset_type`). |
| `POST` | `/refdata/refresh` | Reload all REFDATA tables from the database without restarting the server. |

## Single vs Multi-Factor Mode

All backtest endpoints accept `"mode": "single"` or `"mode": "multi"` in the request body:

- **Single mode** — flat `window_range` / `signal_range`
- **Multi mode** — `factors` list with per-factor ranges and a `data_column` per factor (e.g. `"price"`, `"Volume"`)

The service layer dispatches automatically — no separate endpoints.

## SSE Streaming (`/optimize/stream`)

The streaming endpoint uses `StreamingResponse` with Server-Sent Events:

1. **`init`** — sent once with `{ total_trials }` before optimization starts
2. **`progress`** — sent per trial with `{ trial, total, best_sharpe }`
3. **`result`** — sent once with the full optimization result (same shape as `/optimize`)

Backend implementation: `queue.Queue` + `threading.Thread` + `asyncio.to_thread`

## REFDATA Cache

All REFDATA tables are loaded into an in-process dict at startup (`RefDataCache`). The cache is attached to `app.state` and passed to every service call.

- No TTL — REFDATA changes are rare, admin-only
- Refresh without restart via `POST /refdata/refresh`
- If DB is unreachable at startup, the backend **fails fast** — REFDATA is required

## Project Structure

```
api/
├── main.py              # App factory — CORS, lifespan, router registration
├── config.py            # Settings and env var loading
├── routers/
│   ├── backtest.py      # /backtest/* endpoints
│   └── refdata.py       # /refdata/* endpoints
├── schemas/
│   └── backtest.py      # Pydantic request/response models
└── services/
    ├── backtest.py      # Service layer: _build_config, run_optimize, etc.
    └── refdata_cache.py # RefDataCache — loads REFDATA into memory
```
