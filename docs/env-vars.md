# Environment Variables

Copy the template and fill in any keys you need:

```bash
cp .env.example .env
```

The variables below cover the core runtime set. See `.env.example` for the full template (Cloudflare, Bybit testnet, ECR image tags, and other optional blocks).

## Data Sources

| Variable | Required? | Description |
|---|---|---|
| `ALPHAVANTAGE_API_KEY` | Optional | Free key from [alphavantage.co](https://www.alphavantage.co/support/#api-key). Limited to 25 req/day. |
| `GLASSNODE_API_KEY` | Optional | On-chain crypto metrics. Only if you use the Glassnode data source. |
| `NASDAQ_DATA_LINK_API_KEY` | Optional | Free key from [data.nasdaq.com](https://data.nasdaq.com/account/profile). |
| `FUTU_HOST` / `FUTU_PORT` | Optional | Only if using Futu OpenD gateway for HK/US equities. Default `127.0.0.1:11111`. |

!!! note
    **Yahoo Finance requires no API key** — it is the default and recommended data source for getting started.

## Database (QuantDB on PostgreSQL)

| Variable | Required? | Description |
|---|---|---|
| `QUANTDB_HOST` | Optional | PostgreSQL host for the `prod` target (default: `localhost`, i.e. the SSM tunnel). |
| `QUANTDB_PORT` | Optional | Port for the `prod` target. **Leave unset on a laptop** — `config/db-targets.json` supplies `5433`. Setting it to `5432` makes `prod` point at the local database, which both resolvers refuse. Prod EC2 gets `5432` from SSM together with the real cluster host. |
| `QUANTDB_USERNAME` | Yes | Database user. |
| `QUANTDB_PASSWORD` | Yes | Database password. |
| `QUANTDB_CONNINFO` | Optional | Full libpq connection string. **Overrides** the four `QUANTDB_*` vars above. Must include `sslmode=require`. Use only when you need non-standard libpq options. |
| `QUANTDB_CONNECT_TIMEOUT` | Optional | Seconds for Postgres `connect_timeout` added to the DSN when absent (default: `15`). Prevents hung API requests when the tunnel or host is unreachable. |
| `PGPASSWORD` | Optional | Mirrors `QUANTDB_PASSWORD` so `psql` doesn't prompt interactively. |

## DB target

`DB_TARGET` selects which of the two databases declared in
`config/db-targets.json` everything connects to — the API, the worker, the CLI,
`dbctl.sh` and Liquibase. Defaults shown below come from that file, not from
code; see [Dev vs Prod](architecture/dev-vs-prod.md#where-local-and-prod-are-defined).

| Variable | Required? | Description |
|---|---|---|
| `DB_TARGET` | Optional | `local` → host-side Postgres 17 on `:5432` (no tunnel; `dev start` also brings up Redis + worker via `docker-compose.dev.yml`). `prod` (default if unset) → Aurora on `:5433` after `./scripts/appctl.sh prod tunnel start`. |
| `LOCAL_DB_HOST` | Optional | Overrides the `local` host (default `127.0.0.1`). |
| `LOCAL_DB_PORT` | Optional | Overrides the `local` port (default `5432`). |
| `LOCAL_DB_NAME` | Optional | Overrides the `local` database (default `quantdb`). |
| `LOCAL_DB_USER` | Optional | Overrides the `local` user (default `quant_admin`). |
| `LOCAL_DB_PASSWORD` | Optional | Local user password (default `LetsGetRich888` — change for non-default installs). |
| `PROD_DB_PORT` | Optional | Overrides the `prod` port ahead of `QUANTDB_PORT`. For a tunnel on a non-standard local port. |
| `MAX_CONCURRENT_WORKERS` | Optional | Max concurrent backtest worker subprocesses spawned by one `quant.queue.worker_loop` (default `1`; prod sets `2`). Safe above 1 — one loop claims sequentially, so the non-atomic claim only races between **separate `worker_loop` replicas**, which is what `docs/design/backtest-queue.md` §0 defers. Bound by cores, not RAM: see [Infrastructure Capacity Review §3.2](design/infra-capacity-review.md#32-three-concurrent-workers-use-two). |
| `DB_POOL_MIN` | Optional | Process Postgres pool floor (default `2`). |
| `DB_POOL_MAX` | Optional | Process Postgres pool cap (default `10`). |
| `DB_POOL_MAX_IDLE` | Optional | Seconds an extra connection may sit unused before the pool closes it (default `600`). |
| `DB_POOL_MAX_LIFETIME` | Optional | Seconds after which a connection is discarded on the next checkout (default `1800`). |
| `DB_POOL_TIMEOUT` | Optional | Seconds to wait for a free pooled connection (default `30`). |

## Liquibase (DB migrations)

| Variable | Required? | Description |
|---|---|---|
| `LIQUIBASE_COMMAND_URL` | Yes (for migrations) | JDBC URL, e.g. `jdbc:postgresql://localhost:5433/quantdb`. |
| `LIQUIBASE_COMMAND_USERNAME` | Yes (for migrations) | Usually `quant_admin` for DDL/DML changes. |
| `LIQUIBASE_COMMAND_PASSWORD` | Yes (for migrations) | Admin password. |

## FastAPI Backend

| Variable | Required? | Description |
|---|---|---|
| `CORS_ORIGINS` | Optional | Comma-separated allowed origins. **Not set in code** — configure via SSM or `.env` when the browser hits the API from a different origin than the API itself. Leave unset for same-origin only (e.g. nginx bundle, or Vite proxying `/api` to the backend). |
| `APP_ENV` | Optional | `dev` (default) or `prod`. Affects logging, cookie `Secure`, JWT enforcement. |
| `USE_SSM` | Optional | `1` (default in `docker-compose.yml`) loads secrets from AWS SSM Parameter Store first, then falls back to `.env`. Set `0` to force `.env`-only mode. |
| `AWS_REGION` | Optional | Region used when `USE_SSM=1`. Default `ap-southeast-1`. |

## Authentication (JWT)

| Variable | Required? | Description |
|---|---|---|
| `JWT_SECRET` | **Required in prod** | Symmetric HS256 signing key (generate via `openssl rand -base64 32`). In dev (`APP_ENV != prod`) the API auto-generates a random secret each startup. In prod the API refuses to start without it. Rotate by changing the value and restarting. |
| `EXCHANGE_SECRETS_KEY` | **Required in prod** (Phase 1.1+) | Fernet key for encrypting `CORE_ADMIN.API_CREDENTIAL` ciphertext (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). SSM: `/quant/prod/EXCHANGE_SECRETS_KEY`. Separate from `JWT_SECRET`. |
| `COOKIE_SECURE` | Optional | `1` to force the `Secure` flag on the auth cookie. Default tracks `APP_ENV == prod`. |

## Ops alerts (Slack)

| Variable | Required? | Description |
|---|---|---|
| `SLACK_WEBHOOK_URL` | Optional | Incoming Webhook for **internal ops alerts** (live-apply failures, stale DB connections, …). Messages are prefixed with a searchable category tag (`[TRADE]`, `[DB]`, … — see `AlertCategory` in `quant/shared/notify.py`). If unset, alerts are logged only. Use a **test channel** in dev; prod ops channel only after the pipeline checklist in [Live Trading Promotion](guides/live-trading-promotion.md). |

User accounts are admin-managed — there is no signup endpoint. See [Login & Authentication](design/login.md) for the provisioning flow.

## Exchange egress

| Variable | Required? | Description |
|---|---|---|
| `CCXT_EGRESS_<EXCHANGE_ID>` | Optional | Extra egress routes for **keyed** ccxt sessions to that venue, named for the ccxt exchange id (`CCXT_EGRESS_BYBIT`, `CCXT_EGRESS_BINANCEUSDM`). The format is comma-separated `name=proxy_url`, e.g. `uk=http://13.43.55.53:3128`. `direct` is always tried as well and cannot be redefined; malformed entries are logged and skipped. Each key is routed to whichever route the venue accepts, and the result is cached in Redis. Unset or blank means direct only. Keyless sessions (venue limits, market data) ignore it. Prod: `/quant/prod/CCXT_EGRESS_BYBIT`. See [Infrastructure: Per-key routing](architecture/infrastructure.md#per-key-routing). |

## Frontend (Vite dev server)

| Variable | Required? | Description |
|---|---|---|
| `VITE_API_URL` | Optional | Backend base URL the Vite dev proxy forwards `/api` to. Default `http://localhost:8000`. |

## Safety

!!! warning
    Never commit `.env` to version control. It is gitignored. Production secrets live in **AWS SSM Parameter Store** (`/quant/prod/*`).
