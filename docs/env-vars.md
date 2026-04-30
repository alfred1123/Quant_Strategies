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
| `PGPASSWORD` | Optional | Mirrors `QUANTDB_PASSWORD` so `psql` doesn't prompt interactively. |

## Liquibase (DB migrations)

| Variable | Required? | Description |
|---|---|---|
| `LIQUIBASE_COMMAND_URL` | Yes (for migrations) | JDBC URL, e.g. `jdbc:postgresql://localhost:5433/quantdb`. |
| `LIQUIBASE_COMMAND_USERNAME` | Yes (for migrations) | Usually `quant_admin` for DDL/DML changes. |
| `LIQUIBASE_COMMAND_PASSWORD` | Yes (for migrations) | Admin password. |

## FastAPI Backend

| Variable | Required? | Description |
|---|---|---|
| `CORS_ORIGINS` | Optional | Comma-separated allowed origins (default covers local Vite dev). |
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
