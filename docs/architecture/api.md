# FastAPI Backend

The `quant/api/` directory contains the FastAPI application for backtest, trade, and shared REFDATA endpoints. All `/api/v1/*` routes (except auth and health) require an authenticated session; the **admin**, **market-data**, and **scheduler** routers additionally accept the scheduler Lambda's service bearer token (`require_user_or_service`).

See [System Overview](overview.md) for the full stack.

!!! note "Queue endpoints"
    `/api/v1/backtest/jobs/*` (the backtest queue) is served by this FastAPI process — see decision #32 and [Queued Background Backtests](../design/backtest-queue.md). The Python `quant.queue.worker_loop` daemon (separate container) consumes jobs from `BT.QUEUE`; all HTTP terminates here.

## API namespaces

| Area | Path prefix | Notes |
|------|-------------|--------|
| **Auth** | `/api/v1/auth/*` | Session cookie |
| **Backtest** | `/api/v1/backtest/*` | Sync optimize / performance / walk-forward |
| **Backtest queue** | `/api/v1/backtest/jobs/*` | Async `BT.QUEUE` jobs |
| **Shared config** | `/api/v1/refdata/*`, `/api/v1/inst/*` | Used by Backtest and Trade UIs |
| **Trade — deployments** | `/api/v1/trade/deployments/*` | **Done** (Phase 1.2) |
| **Trade — credentials** | `/api/v1/credentials/*` | **Done** (Phase 1.1) |
| **Trade — strategies** | `/api/v1/strategies` | **Done** (Phase 1.6) — `?versions=best\|all`, `?limit=` |
| **Backtest — promotions** | `/api/v1/backtest/promotions` | **Done** — promotion history for the Promotion tab |
| **Admin / scheduler** | `/api/v1/admin/*`, `/api/v1/market-data/*`, `/api/v1/scheduler/*` | Service-token or session — EventBridge Lambda entry points |

UI mode (`/backtest` vs `/trade`) does **not** change these URLs — each page calls the appropriate prefix.

## Starting the Server

```bash
source env/bin/activate
uvicorn quant.api.main:app --reload --port 8000
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
| `POST` | `/api/v1/backtest/optimize` | Run parameter grid search over a list of factors. Returns top-10 results, grid, and best params. |
| `POST` | `/api/v1/backtest/optimize/stream` | SSE-streamed optimization — sends `init`, `progress`, `result`, and `error` events in real time. |
| `POST` | `/api/v1/backtest/performance` | Run a single backtest at fixed params. Returns equity curve, metrics, and daily P&L. |
| `POST` | `/api/v1/backtest/walk-forward` | Walk-forward overfitting test. Returns IS/OOS metrics, overfitting ratio, and full equity curve. |
| `POST` | `/api/v1/backtest/jobs` | Enqueue a backtest job (202 Accepted). |
| `GET`  | `/api/v1/backtest/jobs` | List queue rows for the current user. |
| `GET`  | `/api/v1/backtest/jobs/{queue_id}` | Job detail + strategy metadata. |
| `POST` | `/api/v1/backtest/jobs/{queue_id}/cancel` | Cancel a queued or running job. |
| `POST` | `/api/v1/backtest/jobs/{queue_id}/reenqueue` | Re-enqueue from a terminal row. |
| `GET`  | `/api/v1/backtest/jobs/{queue_id}/events` | SSE stream of job progress events. |
| `GET`  | `/api/v1/backtest/promotions` | Promotion history rows for the Promotion tab (`?limit=`). |
| `POST` | `/api/v1/backtest/jobs/strategies/{strategy_id}/promote` | Manual promote/demote a strategy VID. |

### Trade (Phase 1.2 — deployments)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/trade/deployments` | Required | Create or re-apply a deployment. Optional `schedule_tm_interval_id` (`REFDATA.TM_INTERVAL`) sets the apply cadence; omit or `null` for manual-only, which is what the UI's schedule dropdown defaults to (see [scheduler §3.1](../design/scheduler-price-bars.md#31-product-ux-how-scheduling-is-enabled)). |
| `GET` | `/api/v1/trade/deployments` | Required | List current deployments for the authenticated user. |
| `GET` | `/api/v1/trade/deployments/{id}` | Required | One deployment (current version). |
| `PATCH` | `/api/v1/trade/deployments/{id}` | Required | Toggle `enabled` / `deployment_status`, or change `schedule_tm_interval_id`. Omitted fields keep their value; explicit `null` clears the schedule. |
| `POST` | `/api/v1/trade/deployments/{id}/stop` | Required | Stop a deployment — disables it and sets `STOPPED`. Idempotent. |
| `POST` | `/api/v1/trade/deployments/{id}/apply` | Required | Run one live-apply cycle now. |
| `POST` | `/api/v1/trade/deployments/dry-run` | Required | Preflight a deployment without placing orders. |
| `GET` | `/api/v1/trade/execution-events` | Required | Recent order attempts across the caller's deployments (`?limit=50`, optional `deployment_id`). |
| `GET` | `/api/v1/trade/transactions` | Required | Recent broker-confirmed fills (`?limit=50`, optional `deployment_id`). |
| `GET` | `/api/v1/trade/deployments/{id}/events` | Required | Execution diary for one deployment. |
| `GET` | `/api/v1/trade/deployments/{id}/transactions` | Required | Fill history for one deployment. |
| `GET` | `/api/v1/trade/accounts/{api_credential_id}/snapshot` | Required | Live balances and open positions for one broker account. Read-only. Query `paper` (default `true`). **404** if the credential is not owned. |

#### Broker failures — status says whether to retry

Anything that reaches an exchange (`dry-run`, `apply`, the account snapshot) can
fail at the broker rather than in our code, and the status separates the two
things a caller can do about it:

| Condition | Status | What the caller does |
|---|---|---|
| Broker rejected the credentials (`BrokerAuthError`) | **400** | Fix the key — retrying is pointless |
| Broker unreachable or erroring (`BrokerConnectionError`) | **503** | Come back on the next tick |
| Bars incomplete (`StaleBarsError`) | **503** | Come back on the next tick |
| Unknown product / no xref (`SymbolMappingError`) | **400** | Fix the request or seed `INST.PRODUCT_XREF` |

A rejected key used to answer **502**, which put a wrong API key in the same
bucket as a platform outage. That is worth stating because the response body
carries the broker's own explanation and the remedy — a **paper** deployment
connects to the venue's *testnet*, so mainnet keys are rejected there — and a
5xx is exactly the response an intermediate proxy is entitled to replace with
its own error page before anyone reads it.

Every handled error is also logged once by `quant/api/exception_handlers.py`
(`METHOD /path -> status: detail`), at `WARNING` for 4xx and `ERROR` for 5xx.
Handling an exception consumes it, so before that a failed request left no
server-side trace at all and could only be reconstructed from the client.

#### Account snapshot

Every field is read from the exchange at request time — nothing comes from our
tables. The point is to show what the account *actually* holds, so a position
opened by hand or left behind by a stopped deployment appears here even though no
`TRADE.DEPLOYMENT` row explains it. Compare with `POSITION_QTY` on
`TRADE.EXECUTION_EVENT`, which records what one apply *saw* at its moment;
this endpoint answers what is true now.

- `balances[]` — `code`, `free`, `used`, `total` per currency. Currencies with
  nothing in them are dropped: a unified account reports every listed asset, and
  a hundred zero rows would bury the one that matters. A currency held only as
  margin (`free` 0, `used` > 0) is kept.
- `positions[]` — signed `qty` (negative short), plus `entry_price`,
  `mark_price`, `notional`, `unrealized_pnl`, `leverage`, `liquidation_price`.
  Optional fields are `null` when the exchange omits them; one missing field
  never fails the snapshot. `symbol` is the raw exchange symbol so it lines up
  with `INST.PRODUCT_XREF`.
- `app_id` is read off the credential row, not taken from the caller — a client
  cannot pair one exchange's keys with another's adapter.
- `paper` defaults to `true`, so a caller that omits it reaches the demo account
  and never real money. The same credential can address both, and they hold
  different money.
- Not cached server-side: each call is a rate-limited exchange round-trip. The
  frontend uses a 30s stale window with an explicit refresh rather than polling.

### Credentials (Phase 1.1 — implemented)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/credentials` | Required | List current user's exchange credentials (masked). |
| `GET` | `/api/v1/credentials/{id}` | Required | One credential (masked). **404** if not owned (never 403). |
| `POST` | `/api/v1/credentials` | Required | Save new broker API key pair. Rate-limited 5/15min per IP. |
| `PUT` | `/api/v1/credentials/{id}` | Required | Rotate keys (soft-version bump). Rate-limited 5/15min per IP. |
| `DELETE` | `/api/v1/credentials/{id}` | Required | Revoke (soft-version; clears ciphertext). Returns 204. |

Keys are Fernet-encrypted in Python (`quant/shared/secrets_crypto.py`) before `CALL CORE_ADMIN.SP_INS_API_CREDENTIAL`. Responses never include `*_CIPHERTEXT`. Broker is identified by `app_id` (`REFDATA.APP`). Full flow: [Credential Encryption](credentials.md).

See [Plan to Profit §1.1](../design/plan-to-profit.md#phase-11-user-secrets) and [Login §6.4](../design/login.md#64-reuse-from-login-jwt-credential-api-phase-11).

### Strategies (Phase 1.6 — implemented)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/strategies` | Required | List caller-owned `BT.STRATEGY` rows for the Trade strategy picker. Query `versions=best` (default — `IS_BEST_IND` rows only) or `all`; `limit` defaults to 200. |

Not the same as REFDATA `signal_type` — see [trade-api §2.1](../design/trade-api.md#21-strategy-catalog-phase-16).

### REFDATA / Instruments (shared)

How the cache is published and read: [REFDATA Cache](refdata-cache.md).

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/v1/refdata/{table_name}` | Fetch a cached REFDATA table (e.g. `indicator`, `signal_type`, `asset_type`, `app`). |
| `POST` | `/api/v1/refdata/refresh` | Reload all REFDATA tables from the database without restarting the server. Returns `{"tables": n}`. |
| `GET`  | `/api/v1/inst/products` | List products (cached `InstrumentCache`). |
| `GET`  | `/api/v1/inst/products/{id}/xrefs` | Vendor-symbol cross-references for a product. |
| `POST` | `/api/v1/inst/refresh` | Reload the instrument cache. Returns 204. |

### Admin / scheduler (service token or session)

These routers are mounted with `require_user_or_service` so the EventBridge Lambda can call them with `TRADE_SERVICE_TOKEN`. Human-facing routes on the same routers add `require_user` when needed.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/admin/log-proc-summary/summarize` | Service or session | Aggregate `LOG_PROC_DETAIL` into daily per-procedure summaries. |
| `POST` | `/api/v1/market-data/price-bars/sync` | Service or session | Pre-fetch bars for every instrument a scheduled deployment will trade (bar warmer). |
| `POST` | `/api/v1/scheduler/tick` | Service or session | Apply every deployment currently due across all intervals (hourly platform sweep). |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness — returns 200 if the process is up. |
| `GET`  | `/health/ready` | Readiness — performs a DB ping. |

Health endpoints are **not** under `/api/v1` and are unauthenticated.

## Authentication

Protected routers use `Depends(require_user)` to validate the JWT cookie. Unauthenticated requests get **401 Unauthorized**, which the frontend interceptor uses to evict the cached user and re-render the login page.

Provisioning new users is admin-only (no signup endpoint) — see [Login & Authentication](../design/login.md) for the runbook.

## Factor List (single source of truth)

All backtest requests use a uniform **factor-list** shape. There is no `mode` discriminator and no separate single-factor branch — a "single factor" backtest is just a 1-element `factors` list. This keeps cross-product semantics (factor on a different symbol than the trade asset, e.g. trade SPY but signal off VIX RSI) available for any factor count.

Each `FactorConfig` carries:

- `symbol` / `vendor_symbol` / `data_source` — **where the indicator reads from** (optional; defaults to the top-level trade asset). Set these when the indicator should be computed from a different product than the one being traded.
- `data_column` — which column of the source DataFrame becomes the `factor` series (default `"price"`).
- `indicator` / `strategy` — what to compute and how to turn it into positions.
- `window_range` / `signal_range` — the parameter grid for this factor.

`conjunction` (`"AND"` / `"OR"` / `"FILTER"`) describes how multiple factors' positions are combined. It is **required only when there are 2+ factors** and must be omitted (or `null`) for a single-factor request — the field is meaningless in that case. The service layer dispatches the optimizer based on `len(factors)`:

- 1 factor → `ParametersOptimization.optimize()` returning rows keyed `window` / `signal`
- 2+ factors → `ParametersOptimization.optimize_multi()` returning rows keyed `window_0` / `signal_0` / `window_1` / …

For `/performance`, the caller passes `windows: list[int]` and `signals: list[float]` — one value per factor, in the same order.

## SSE Streaming (`/optimize/stream`)

The streaming endpoint uses `StreamingResponse` with Server-Sent Events:

1. **`init`** — sent once with `{ "total": <total_trials> }` before optimization starts
2. **`progress`** — sent per trial with `{ "trial": ..., "total": ..., "best_sharpe": ... }`
3. **`result`** — sent once with the full optimization result (same shape as `/optimize`)
4. **`error`** — sent if optimization fails; payload contains `{ "detail": "..." }`

Backend implementation: `queue.Queue` + `threading.Thread` + `asyncio.to_thread` so the worker can stream progress without blocking the event loop.

## Caches: REFDATA, INST, BT

At startup the FastAPI lifespan hook also builds `CredentialCrypto` (Fernet key from `EXCHANGE_SECRETS_KEY` — prod fail-fast) and a `DataCaches` bundle wired to Postgres + Redis:

- **`RefDataPublisher`** (`quant/refdata/publisher.py`) — first runs `publish_all()`, which discovers every `REFDATA.*` table via `information_schema`, calls `REFDATA.SP_GET_ENUM`, and writes JSON snapshots under `refdata:<table>` plus a bumped `refdata:version` key in Redis. The same call is exposed at `POST /api/v1/refdata/refresh` for ad-hoc reseeding.
- **`RedisRefData`** (`quant/refdata/reader.py`) — read-only accessor used by request handlers and the worker. Checks `refdata:version` on every `get()` and rebuilds its local snapshot lazily on bump, so long-lived processes always see the current REFDATA without pub/sub.
- **`InstrumentCache`** (`quant/data/instruments.py`) — products + xrefs from the INST schema; loaded at startup and refreshable via `POST /api/v1/inst/refresh`.
- **`BacktestCache`** (`quant/data/backtest_cache.py`) — BT schema read/write used by the optimize/performance services for the dataset cache.

If the REFDATA publish fails at startup the server still boots (REFDATA endpoints 503 until `POST /api/v1/refdata/refresh` succeeds); the instrument-cache load and missing prod secrets still fail the boot.

## Project Structure

```
quant/api/
├── main.py              # App factory — CORS, lifespan, router registration
├── deps.py              # FastAPI dependencies (DataCaches, auth)
├── exception_handlers.py
├── auth/
│   ├── router.py        # /api/v1/auth/* endpoints
│   ├── service.py       # AuthService — password verify (Argon2), JWT
│   ├── dependencies.py  # require_user / require_user_or_service
│   ├── repo.py          # AuthRepo — calls SP_GET_APP_USER_BY_*
│   └── models.py        # Pydantic models (LoginRequest, etc.)
├── credentials/         # Phase 1.1 — exchange API keys
│   ├── router.py        # /api/v1/credentials/* (rate-limited POST/PUT)
│   ├── service.py       # CredentialService — Fernet encrypt, mask responses
│   ├── repo.py          # ApiCredentialRepo — SP_INS/GET/REVOKE
│   └── schemas.py       # CreateCredentialRequest, CredentialResponse, …
├── admin/               # Service-token maintenance (log-proc summary)
│   ├── router.py
│   └── repo.py
├── market_data/         # Bar warmer — POST /market-data/price-bars/sync
│   └── router.py
├── scheduler/           # Platform tick — POST /scheduler/tick
│   └── router.py
├── routers/
│   ├── backtest.py      # /api/v1/backtest/* endpoints
│   ├── deployments.py   # /api/v1/trade/deployments/* + execution diary reads
│   ├── jobs.py          # /api/v1/backtest/jobs/* + manual promote
│   ├── promotion.py     # /api/v1/backtest/promotions
│   ├── strategies.py    # /api/v1/strategies (Phase 1.6)
│   ├── refdata.py       # /api/v1/refdata/* endpoints
│   └── inst.py          # /api/v1/inst/* endpoints
├── schemas/
│   ├── jobs.py
│   ├── promotion.py
│   └── strategies.py
└── services/
    ├── jobs.py          # Enqueue, list, cancel, SSE broker
    ├── promotion.py
    └── strategies.py

quant/shared/config.py              # Settings, env/SSM loading (not under api/)
quant/shared/secrets_crypto.py      # CredentialCrypto — EXCHANGE_SECRETS_KEY + Fernet
quant/strategy/backtest_service.py  # Backtest orchestration (called from routers)
quant/trade/service.py              # TradeService — deployments (Phase 1.2)
quant/trade/db_repo.py              # TradeRepo — SP_INS/GET_DEPLOYMENT
```

REFDATA, INST, and BT cache classes live under `quant/refdata/` and `quant/data/` (shared between the API and the worker via `quant/refdata/bundle.py::DataCaches`). All Postgres access goes through `quant/shared/db.py::DbGateway` — no other module imports `psycopg` (except the `/health/ready` DB ping in `main.py`).
