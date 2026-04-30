# Dev vs Prod Configuration

This page lists every configuration value that differs between local
development and the production EC2, so developers can restore their
environment after a deploy or onboard quickly.

---

## Quick reference

| Setting | Dev (laptop) | Prod (EC2) | Where it lives |
|---------|-------------|------------|----------------|
| `QUANTDB_HOST` | `localhost` | `quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com` | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `QUANTDB_PORT` | `5433` | `5432` | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `QUANTDB_USERNAME` | shared DB user | same | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `QUANTDB_PASSWORD` | shared DB password | same | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `APP_ENV` | `dev` (default) | `prod` | `docker-compose.prod.yml` |
| `USE_SSM` | `1` (default) | `1` | `docker-compose.yml` (default for both) |
| `COOKIE_SECURE` | unset (defaults to `APP_ENV == prod`) | `0` (HTTP) / `1` (HTTPS) | `docker-compose.prod.yml` / `docker-compose.tls.yml` |
| `CORS_ORIGINS` | `http://localhost:5173` | `http://localhost:5173,http://52.221.3.230` | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `JWT_SECRET` | shared dev secret from SSM | fixed value from SSM | SSM `/quant/dev/` / SSM `/quant/prod/` |
| DB access method | SSM port-forward tunnel | Direct VPC connection | Network topology |
| Nginx config | `nginx.dev.conf` (HTTP only) | Same (HTTP) or `nginx.conf` (TLS via `docker-compose.tls.yml`) | `docker/nginx/` |
| Swagger UI | enabled (`/docs`) | disabled | `api/main.py` checks `APP_ENV` |
| Logging | stdout, plus file (`log/bt_app.log`) when running locally **without** `USE_SSM=1` | stdout only | `api/config.py` `setup_logging()` |

---

## How config is loaded

```
Developer laptop                          Production EC2
─────────────────                         ──────────────
docker compose up                         docker compose -f docker-compose.yml
      │                                         -f docker-compose.prod.yml up
      ▼                                               │
 docker-compose.yml                                   ▼
  APP_ENV=dev                              docker-compose.prod.yml merges:
  USE_SSM=1 (default)                        APP_ENV=prod
      │                                      USE_SSM=1
      ▼                                      COOKIE_SECURE=0
  SSM /quant/dev/*                                │
  loads ALL config:                               ▼
    QUANTDB_HOST (localhost)              SSM /quant/prod/*
    QUANTDB_PORT (5433)                   loads ALL config:
    JWT_SECRET, CORS_ORIGINS, etc.          QUANTDB_HOST (RDS endpoint)
      │                                     QUANTDB_PORT (5432)
      │  (fallback if SSM unreachable:      JWT_SECRET, CORS_ORIGINS, etc.
      │   loads .env instead)                     │
      ▼                                           ▼
  api/config.py                            api/config.py
  _load_from_ssm("dev")                   _load_from_ssm("prod")
  _build_db_conninfo()                    _build_db_conninfo()
      │                                           │
      ▼                                           ▼
  connects to localhost:5433               connects to RDS:5432
  (SSM tunnel to RDS)                     (direct VPC connection)
```

---

## Restoring dev environment

Config is loaded from SSM `/quant/dev/` by default. You just need AWS credentials:

```bash
aws sso login --profile alfcheun
```

If SSM is unreachable (offline, no AWS creds), the API falls back to `.env`.
To set up the fallback file:

```bash
cp .env.example .env
```

Then fill in your credentials:

```bash
# .env — fallback values (only used when SSM is unreachable)
export QUANTDB_HOST=localhost
export QUANTDB_PORT=5433
export QUANTDB_USERNAME=quant_admin
export QUANTDB_PASSWORD=<your_password>
JWT_SECRET=<any_value_or_leave_blank_for_auto>
```

Start the SSM tunnel (runs automatically via Cursor hook, or manually):

```bash
aws ssm start-session \
  --target i-096f85bf84852cce3 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["5433"]}' \
  --profile alfcheun
```

Verify:

```bash
pg_isready -h localhost -p 5433
```

Run locally (no Docker needed for dev):

```bash
uvicorn api.main:app --reload --port 8000
cd frontend && npm run dev
```

Or with Docker:

```bash
docker compose up -d --build
```

---

## SSM parameters

Both dev and prod config live in AWS SSM Parameter Store under `/quant/<env>/`.

### `/quant/dev/` (developer laptops)

| Parameter | Type | Value |
|-----------|------|-------|
| `QUANTDB_HOST` | String | `localhost` |
| `QUANTDB_PORT` | String | `5433` |
| `QUANTDB_USERNAME` | SecureString | `quant_admin` |
| `QUANTDB_PASSWORD` | SecureString | *(stored securely)* |
| `JWT_SECRET` | SecureString | *(shared dev secret)* |
| `CORS_ORIGINS` | String | `http://localhost:5173` |
| `FUTU_HOST` | String | `127.0.0.1` |
| `FUTU_PORT` | String | `11111` |

### `/quant/prod/` (EC2)

| Parameter | Type | Value |
|-----------|------|-------|
| `QUANTDB_HOST` | String | `quantdb-cluster.cluster-...rds.amazonaws.com` |
| `QUANTDB_PORT` | String | `5432` |
| `QUANTDB_USERNAME` | SecureString | `quant_admin` |
| `QUANTDB_PASSWORD` | SecureString | *(stored securely)* |
| `JWT_SECRET` | SecureString | *(stored securely)* |
| `CORS_ORIGINS` | String | `http://localhost:5173,http://52.221.3.230` |
| `FUTU_HOST` | String | `127.0.0.1` |
| `FUTU_PORT` | String | `11111` |

### Bootstrap a new environment

```bash
# Dev params (run once)
APP_ENV=dev bash aws/scripts/init-ssm-params.sh

# Prod params (run once)
bash aws/scripts/init-ssm-params.sh
```

### Update a parameter

```bash
aws ssm put-parameter --name /quant/dev/QUANTDB_HOST \
  --value "new-value" --type String --overwrite --region ap-southeast-1
```

After updating prod SSM params, restart the API container on EC2:

```bash
aws ssm send-command --instance-ids i-096f85bf84852cce3 \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["cd /opt/quant && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"]' \
  --region ap-southeast-1
```

---

## Files that contain environment-specific values

| File | What it configures |
|------|--------------------|
| `.env.example` | Template for developers — all values are dev defaults |
| `.env` | Actual dev config (gitignored, never committed) |
| `docker-compose.yml` | Base services — `USE_SSM=1` default, SSM-first for all envs |
| `docker-compose.prod.yml` | Prod behavioral flags only — `APP_ENV=prod`, `USE_SSM=1`, `COOKIE_SECURE=0` |
| `docker-compose.tls.yml` | TLS layer — `COOKIE_SECURE=1`, `DOMAIN`, certbot |
| `api/config.py` | Config loader — tries SSM first, falls back to `.env` if unreachable |
| `api/auth/router.py` | Cookie `Secure` flag — reads `COOKIE_SECURE` or falls back to `APP_ENV` |
| `api/main.py` | Swagger toggle, CORS — reads `APP_ENV`, `CORS_ORIGINS` |
| `aws/scripts/init-ssm-params.sh` | Bootstraps SSM parameters (run once) |
| `.cursor/hooks/ssm-port-forward-loop.sh` | Auto-starts SSM tunnel for dev |

---

## Docker Compose layering

```bash
# Dev (HTTP, SSM /quant/dev/ config, falls back to .env if offline)
docker compose up -d --build

# Prod HTTP-only (SSM secrets, direct RDS, no TLS)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Prod with TLS (requires DOMAIN)
export DOMAIN=yourdomain.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls.yml up -d --build
```
