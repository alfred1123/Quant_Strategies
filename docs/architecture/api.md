# FastAPI Backend

The `api/` directory contains the FastAPI application that serves the backtest pipeline as a REST API. All `/api/v1/*` routes (except auth and health) require an authenticated session.

## Starting the Server

```bash
source env/bin/activate
uvicorn api.main:app --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs`.

The Vite dev proxy forwards `/api` from `http://localhost:5173` to this backend.

## Endpoints

All endpoints below are mounted under the `/api/v1` prefix.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/login` | Public (rate-limited 5/15min per IP) | Issues an `HttpOnly` JWT cookie (`qs_token`). |
| `POST` | `/api/v1/auth/logout` | Required | Clears the session cookie. |
| `GET`  | `/api/v1/auth/me` | Required | Returns the current user (or 401). |

### Backtest

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/backtest/optimize` | Run parameter grid search (single or multi-factor). Returns top-10 results, grid, and best params. |
| `POST` | `/api/v1/backtest/optimize/stream` | SSE-streamed optimization — sends `init`, `progress`, `result`, and `error` events in real time. |
| `POST` | `/api/v1/backtest/performance` | Run a single backtest at fixed params. Returns equity curve, metrics, and daily P&L. |
| `POST` | `/api/v1/backtest/walk-forward` | Walk-forward overfitting test. Returns IS/OOS metrics, overfitting ratio, and full equity curve. |

### REFDATA / Instruments

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/v1/refdata/{table_name}` | Fetch a cached REFDATA table (e.g. `indicator`, `signal_type`, `asset_type`, `app`). |
| `POST` | `/api/v1/refdata/refresh` | Reload all REFDATA tables from the database without restarting the server. Returns 204. |
| `GET`  | `/api/v1/inst/products` | List products (cached `InstrumentCache`). |
| `GET`  | `/api/v1/inst/products/{id}/xrefs` | Vendor-symbol cross-references for a product. |
| `POST` | `/api/v1/inst/refresh` | Reload the instrument cache. Returns 204. |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness — returns 200 if the process is up. |
| `GET`  | `/health/ready` | Readiness — performs a DB ping. |

Health endpoints are **not** under `/api/v1` and are unauthenticated.

## Authentication

Protected routers use `Depends(require_user)` to validate the JWT cookie. Unauthenticated requests get **401 Unauthorized**, which the frontend interceptor uses to evict the cached user and re-render the login page.

Provisioning new users is admin-only (no signup endpoint) — see [Login & Authentication](../design/login.md) for the runbook.

## Single vs Multi-Factor Mode

All backtest endpoints accept `"mode": "single"` or `"mode": "multi"` in the request body:

- **Single mode** — flat `window_range` / `signal_range`
- **Multi mode** — `factors` list with per-factor ranges and a `data_column` per factor (e.g. `"price"`, `"Volume"`)

The service layer dispatches automatically — no separate endpoints.

## SSE Streaming (`/optimize/stream`)

The streaming endpoint uses `StreamingResponse` with Server-Sent Events:

1. **`init`** — sent once with `{ "total": <total_trials> }` before optimization starts
2. **`progress`** — sent per trial with `{ "trial": ..., "total": ..., "best_sharpe": ... }`
3. **`result`** — sent once with the full optimization result (same shape as `/optimize`)
4. **`error`** — sent if optimization fails; payload contains `{ "detail": "..." }`

Backend implementation: `queue.Queue` + `threading.Thread` + `asyncio.to_thread` so the worker can stream progress without blocking the event loop.

## Caches: REFDATA and INST

Two in-process caches load at startup:

- **`RefDataCache`** — all REFDATA tables loaded via `REFDATA.SP_GET_ENUM`. Discovers tables dynamically from `information_schema`.
- **`InstrumentCache`** — products + xrefs from the INST schema.

Both are attached to `app.state` and passed to every service call. Refresh without restart via the `/refresh` endpoints listed above.

If the database is **unreachable at startup**, the backend logs an error and **starts with empty caches** — endpoints that need REFDATA/INST will return 5xx until the database recovers and a refresh runs.

## Project Structure

```
api/
├── main.py              # App factory — CORS, lifespan, router registration
├── config.py            # Settings, env loading, setup_logging()
├── auth/
│   ├── router.py        # /api/v1/auth/* endpoints
│   ├── service.py       # AuthService — password verify (Argon2), JWT
│   ├── dependencies.py  # require_user FastAPI dependency
│   ├── repo.py          # AuthRepo — calls SP_GET_APP_USER_BY_*
│   └── models.py        # Pydantic models (LoginRequest, etc.)
├── routers/
│   ├── backtest.py      # /api/v1/backtest/* endpoints
│   ├── refdata.py       # /api/v1/refdata/* endpoints
│   └── inst.py          # /api/v1/inst/* endpoints
├── schemas/
│   └── backtest.py      # Pydantic request/response models
└── services/
    └── backtest.py      # _build_config, run_optimize, stream_optimize, etc.
```

REFDATA and INST cache classes live in `src/data.py` (shared between the API and the CLI pipeline).
