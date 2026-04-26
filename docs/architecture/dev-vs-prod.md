# Dev vs Prod Configuration

This page lists every configuration value that differs between local
development and the production EC2, so developers can restore their
environment after a deploy or onboard quickly.

---

## Quick reference

| Setting | Dev (laptop) | Prod (EC2) | Where it lives |
|---------|-------------|------------|----------------|
| `QUANTDB_HOST` | `localhost` | `quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com` | `.env` / SSM `/quant/prod/` / `docker-compose.prod.yml` |
| `QUANTDB_PORT` | `5433` | `5432` | `.env` / SSM `/quant/prod/` / `docker-compose.prod.yml` |
| `QUANTDB_USERNAME` | your DB user | same | `.env` / SSM |
| `QUANTDB_PASSWORD` | your DB password | same | `.env` / SSM |
| `APP_ENV` | `dev` (default) | `prod` | `docker-compose.prod.yml` |
| `USE_SSM` | empty (default) | `1` | `docker-compose.prod.yml` |
| `COOKIE_SECURE` | not set (defaults `false`) | `0` (HTTP) / `1` (HTTPS) | `docker-compose.prod.yml` / `docker-compose.tls.yml` |
| `CORS_ORIGINS` | `http://localhost:5173` (default) | `http://localhost:5173,http://52.221.3.230` | SSM `/quant/prod/CORS_ORIGINS` |
| `JWT_SECRET` | auto-generated each restart | fixed value from SSM | SSM `/quant/prod/JWT_SECRET` |
| DB access method | SSM port-forward tunnel | Direct VPC connection | Network topology |
| Nginx config | `nginx.dev.conf` (HTTP only) | Same (HTTP) or `nginx.conf` (TLS via `docker-compose.tls.yml`) | `docker/nginx/` |
| Swagger UI | enabled (`/docs`) | disabled | `api/main.py` checks `APP_ENV` |
| Logging | stdout + file (`log/bt_app.log`) | stdout only | `api/config.py` checks `APP_ENV` |

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
  USE_SSM=  (empty)                          APP_ENV=prod
      │                                      USE_SSM=1
      ▼                                      QUANTDB_HOST=<RDS endpoint>
  env_file: .env                             QUANTDB_PORT=5432
  QUANTDB_HOST=localhost                     COOKIE_SECURE=0
  QUANTDB_PORT=5433                               │
      │                                           ▼
      ▼                                    SSM /quant/prod/*
  api/config.py                            loads QUANTDB_PASSWORD,
  _load_from_dotenv()                      JWT_SECRET, CORS_ORIGINS, etc.
  _build_db_conninfo()                            │
      │                                           ▼
      ▼                                    api/config.py
  connects to localhost:5433               _load_from_ssm("prod")
  (SSM tunnel to RDS)                     _build_db_conninfo()
                                                  │
                                                  ▼
                                           connects to RDS:5432
                                           (direct VPC connection)
```

---

## Restoring dev environment

If your `.env` was overwritten or you're setting up from scratch:

```bash
cp .env.example .env
```

Then fill in your credentials:

```bash
# .env — key values for dev
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

## SSM parameters (prod)

These live at `/quant/prod/` in AWS SSM Parameter Store:

| Parameter | Type | Current value |
|-----------|------|---------------|
| `QUANTDB_HOST` | String | `quantdb-cluster.cluster-...rds.amazonaws.com` |
| `QUANTDB_PORT` | String | `5432` |
| `QUANTDB_USERNAME` | SecureString | `quant_admin` |
| `QUANTDB_PASSWORD` | SecureString | *(stored securely)* |
| `JWT_SECRET` | SecureString | *(stored securely)* |
| `CORS_ORIGINS` | String | `http://localhost:5173,http://52.221.3.230` |
| `FUTU_HOST` | String | `127.0.0.1` |
| `FUTU_PORT` | String | `11111` |

Update a parameter:

```bash
aws ssm put-parameter --name /quant/prod/QUANTDB_HOST \
  --value "new-value" --type String --overwrite --region ap-southeast-1
```

After updating SSM params, restart the API container on EC2:

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
| `docker-compose.yml` | Base services — dev defaults for `APP_ENV`, `USE_SSM` |
| `docker-compose.prod.yml` | Prod API overrides — `APP_ENV=prod`, `USE_SSM=1`, RDS host/port, `COOKIE_SECURE=0` |
| `docker-compose.tls.yml` | TLS layer — `COOKIE_SECURE=1`, `DOMAIN`, certbot |
| `api/config.py` | Config loader — reads `.env` or SSM based on `USE_SSM` |
| `api/auth/router.py` | Cookie `Secure` flag — reads `COOKIE_SECURE` or falls back to `APP_ENV` |
| `api/main.py` | Swagger toggle, CORS — reads `APP_ENV`, `CORS_ORIGINS` |
| `aws/scripts/init-ssm-params.sh` | Bootstraps SSM parameters (run once) |
| `.cursor/hooks/ssm-port-forward-loop.sh` | Auto-starts SSM tunnel for dev |

---

## Docker Compose layering

```bash
# Dev (HTTP, .env, localhost DB)
docker compose up -d --build

# Prod HTTP-only (SSM secrets, direct RDS, no TLS)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Prod with TLS (requires DOMAIN)
export DOMAIN=yourdomain.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls.yml up -d --build
```
