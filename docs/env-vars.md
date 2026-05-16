# Environment Variables

Copy the template and fill in any keys you need:

```bash
cp .env.example .env
```

The variables below mirror `.env.example`. Variables with `export` are also sourced by bash scripts (psql, liquibase). Variables without `export` are read by Python (`python-dotenv`).

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
| `QUANTDB_HOST` | Optional | PostgreSQL host (default: `localhost`). |
| `QUANTDB_PORT` | Optional | PostgreSQL port (default: `5433`). |
| `QUANTDB_USERNAME` | Yes | Database user. |
| `QUANTDB_PASSWORD` | Yes | Database password. |
| `QUANTDB_CONNINFO` | Optional | Full libpq connection string. **Overrides** the four `QUANTDB_*` vars above. Must include `sslmode=require`. Use only when you need non-standard libpq options. |
| `QUANTDB_CONNECT_TIMEOUT` | Optional | Seconds for Postgres `connect_timeout` added to the DSN when absent (default: `15`). Prevents hung API requests when the tunnel or host is unreachable. |
| `PGPASSWORD` | Optional | Mirrors `QUANTDB_PASSWORD` so `psql` doesn't prompt interactively. |

## Dev DB target (scripts/appctl.sh)

These vars only apply to local dev (`./scripts/appctl.sh dev start`). Teammates without a local Postgres can ignore them — leaving `DB_TARGET` unset uses the shared Aurora cluster via the SSM tunnel.

| Variable | Required? | Description |
|---|---|---|
| `DB_TARGET` | Optional | `prod` (default) → SSM tunnel on `127.0.0.1:5433` to Aurora. `local` → host-side Postgres 17 on `127.0.0.1:5432` (set up via `./scripts/dbctl.sh`). When `local`, `appctl.sh dev start` ALSO brings up Redis + the Python queue worker via `docker-compose.dev.yml`. |
| `LOCAL_DB_HOST` | Optional | Local Postgres host (default `127.0.0.1`). |
| `LOCAL_DB_PORT` | Optional | Local Postgres port (default `5432`). |
| `LOCAL_DB_NAME` | Optional | Local DB name (default `quantdb`). |
| `LOCAL_DB_USER` | Optional | Local user (default `quant_admin`). |
| `LOCAL_DB_PASSWORD` | Optional | Local user password (default `LetsGetRich888` — change for non-default installs). |
| `MAX_CONCURRENT_WORKERS` | Optional | Max concurrent backtest worker subprocesses spawned by one `quant.queue.worker_loop` (default `1`). Bump only after `SP_CLAIM_NEXT` becomes atomic — see `docs/design/backtest-queue.md` §0. |

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
| `COOKIE_SECURE` | Optional | `1` to force the `Secure` flag on the auth cookie. Default tracks `APP_ENV == prod`. |

User accounts are admin-managed — there is no signup endpoint. See [Login & Authentication](design/login.md) for the provisioning flow.

## Frontend (Vite dev server)

| Variable | Required? | Description |
|---|---|---|
| `VITE_API_URL` | Optional | Backend base URL the Vite dev proxy forwards `/api` to. Default `http://localhost:8000`. |

## Safety

!!! warning
    Never commit `.env` to version control. It is gitignored. Production secrets live in **AWS SSM Parameter Store** (`/quant/prod/*`).
