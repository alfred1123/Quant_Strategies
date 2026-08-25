# Dev vs Prod Configuration

This page lists every configuration value that differs between local
development and the production EC2, so developers can restore their
environment after a deploy or onboard quickly.

See [System Overview](overview.md) for runtime topologies.

---

## Quick reference

| Setting | Dev (laptop) | Prod (EC2) | Where it lives |
|---------|-------------|------------|----------------|
| `DB_TARGET` | `prod` (tunnel, default) or `local` | `prod` | `.env` — resolved via `config/db-targets.json` |
| `QUANTDB_HOST` | `localhost` (tunnel) | `quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com` | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `QUANTDB_PORT` | leave unset — `config/db-targets.json` supplies `5433` | `5432` | SSM (prod); setting it to `5432` in `.env` is refused for `prod` |
| `QUANTDB_USERNAME` | shared DB user | same | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `QUANTDB_PASSWORD` | shared DB password | same | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `APP_ENV` | `dev` (default) | `prod` | `docker-compose.prod.yml` |
| `USE_SSM` | `1` (default) | `1` | `docker-compose.yml` (default for both) |
| `COOKIE_SECURE` | unset (defaults to `APP_ENV == prod`) | `0` (HTTP) / `1` (HTTPS) | `docker-compose.prod.yml` / `docker-compose.cloudflare.yml` |
| `CORS_ORIGINS` | SSM `/quant/dev/` or `.env` (no in-code default) | SSM `/quant/prod/` (public site URL(s)) | SSM / `.env` |
| `JWT_SECRET` | shared dev secret from SSM | fixed value from SSM | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `EXCHANGE_SECRETS_KEY` | dev SSM or auto-generated ephemeral | **required** — Fernet for credentials | SSM `/quant/prod/EXCHANGE_SECRETS_KEY` |
| EC2 instance | **None** (laptop) | **One** `quant-compute` host (prod only) | CFN stack `quant-compute` → output `InstanceId` |
| DB access method | SSM port-forward **via prod EC2** → Aurora | Direct VPC connection (same EC2) | Network topology |
| Nginx config | `nginx.dev.conf` (HTTP only) | `nginx.cloudflare.conf` (Cloudflare Origin TLS via `docker-compose.cloudflare.yml`); `nginx.conf` for Let's Encrypt via `docker-compose.tls.yml` | `docker/nginx/` |
| Swagger UI | enabled (`/docs`) | disabled | `quant/api/main.py` checks `APP_ENV` |
| Logging | stdout, plus file (`log/bt_app.log`) when running locally **without** `USE_SSM=1` | stdout only | `quant/shared/logging.py` `setup_logging()` |

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
      │  (fallback if SSM unreachable:      JWT_SECRET, CORS_ORIGINS,
      │   loads .env instead)               EXCHANGE_SECRETS_KEY (required)
      │                                           │
      ▼                                           ▼
  quant/shared/config.py                            quant/shared/config.py
  _load_from_ssm("dev")                   _load_from_ssm("prod")
  _build_db_conninfo()                    _build_db_conninfo()
      │                                           │
      ▼                                           ▼
  connects to localhost:5433               connects to RDS:5432
  (SSM tunnel via prod EC2)               (direct VPC connection)
```

!!! note "There is no dev EC2"
    **Dev and prod share one compute host.** Laptops reach Aurora by SSM
    port-forwarding through the **prod** EC2 instance (`quant-compute` stack).
    There is no separate dev instance — do not hardcode an instance ID in docs
    or scripts; resolve it from CloudFormation (see below) or use
    `./scripts/appctl.sh dev tunnel start`, which reads `SSM_TARGET_INSTANCE`
    from `.env` when set.

### Resolve the current prod EC2 instance ID

The instance ID **changes when the compute stack replaces EC2** (AMI upgrade,
instance type change, etc.). CI and ops scripts resolve it at runtime:

```bash
aws cloudformation describe-stacks \
  --stack-name quant-compute \
  --region ap-southeast-1 \
  --profile alfcheun \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
  --output text
```

Optional fallback: set `SSM_TARGET_INSTANCE` in `.env` (dev tunnel) or
`EC2_INSTANCE_ID` in GitHub Actions repo variables if CFN lookup fails.

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

Start the SSM tunnel (preferred — resolves target from `SSM_TARGET_INSTANCE` in
`.env`, or the default in `scripts/appctl.sh`):

```bash
./scripts/appctl.sh dev tunnel start
./scripts/appctl.sh dev tunnel status   # confirms tunnel + DB on :5433
```

The tunnel also starts automatically via the Cursor hook, or when you run
`./scripts/appctl.sh dev start` with `DB_TARGET=prod` (default).

Verify:

```bash
pg_isready -h localhost -p 5433
```

Manual SSM (only if debugging — substitute `$INSTANCE_ID` from the CFN query
above, not a copied literal):

```bash
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name quant-compute \
  --region ap-southeast-1 --profile alfcheun \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"

aws ssm start-session \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["5433"]}' \
  --profile alfcheun
```

Run locally (no Docker needed for dev):

```bash
uvicorn quant.api.main:app --reload --port 8000
cd frontend && npm run dev
```

Or with Docker:

```bash
docker compose up -d --build
```

---

## Optional: point dev at a local Postgres

By default `./scripts/appctl.sh dev start` uses the SSM tunnel on `localhost:5433`
to reach the shared Aurora cluster. This is the recommended path — every
teammate gets it for free with just AWS SSO.

If you also want a **local** Postgres (offline work, faster iteration, safe to
break), the toolchain supports it as an opt-in via `DB_TARGET=local`. Teammates
without a local DB are unaffected — leaving `DB_TARGET` unset keeps the prod
tunnel as the default.

### One-time setup

```bash
# 1. Install Postgres 17 client + server (Ubuntu/WSL example, PGDG repo)
sudo apt install -y postgresql-17 postgresql-client-17

# 2. Install Docker + compose v2 (used to run Redis + the Python queue
#    worker that processes backtest jobs). Skip if you already have Docker.
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"     # log out/in, or use `sg docker -c ...`

# 3. Create the local quant_admin user + quantdb database
./scripts/dbctl.sh reset

# 4. Dump prod (uses the SSM tunnel) and restore into local
./scripts/dbctl.sh dump
./scripts/dbctl.sh restore        # picks the newest dump in db/dumps/
```

See [Database dump & restore](../guides/database-dump-restore.md) for full steps, troubleshooting, and security notes.

### Daily usage

```bash
# Append once to .env (per-developer, gitignored)
echo 'DB_TARGET=local' >> .env

# Start: brings up uvicorn + vite natively AND
#   docker-compose.dev.yml (redis + worker) automatically.
# No SSM tunnel needed.
./scripts/appctl.sh dev start

# Status confirms which target is active + dev stack health
./scripts/appctl.sh dev status
#   Mode: dev  (DB_TARGET=local)
#   backend: running (..., port 8000)
#   frontend: running (..., port 5173)
#   DB: reachable on 127.0.0.1:5432  (local)
#   dev stack:
#     quant-dev-worker        Up
#     quant-dev-redis         Up (healthy)
```

`./scripts/appctl.sh dev kill` (or `stop`) tears down everything — uvicorn,
vite, **and** the compose stack — so nothing lingers between sessions.

What runs where:

| Component | Where | Port | Source of truth |
|-----------|-------|------|-----------------|
| FastAPI (uvicorn --reload) | host (native) | 8000 | `quant/api/`, `quant/` |
| Vite dev server | host (native) | 5173 | `frontend/` |
| PostgreSQL 17 | host (native, systemd) | 5432 | `pg_dump` of Aurora |
| Redis 7 | docker | 6379 | `docker-compose.dev.yml` |
| Worker (`quant.queue.worker_loop`) | docker (host network) | — | `docker-compose.dev.yml` |

The worker container uses `network_mode: host` so it can reach the
host-side Postgres at `127.0.0.1:5432` and the host-side Redis at
`127.0.0.1:6379` without any extra docker network plumbing (Linux/WSL2
only). FastAPI hydrates Redis with all REFDATA tables on boot — verify
with `docker exec quant-dev-redis redis-cli keys 'refdata:*'`. The worker
then claims `QUEUED` rows from `BT.QUEUE` and spawns one
`python -m quant.queue.worker <queue_id>` subprocess per job.

To switch back to the shared prod DB, comment out / remove `DB_TARGET=local`
from `.env` (or run `DB_TARGET=prod ./scripts/appctl.sh dev start` for a
one-off override).

How it works: `appctl.sh` passes `DB_TARGET=local` (plus `USE_SSM=0`, so the API
does not fetch prod credentials it will not use) to uvicorn and to the worker
container. Nothing hands over a host or a port — both ends resolve the target
themselves from `config/db-targets.json`, described next.

---

## Where `local` and `prod` are defined

`config/db-targets.json` is the single declaration of the two databases this
project talks to. `DB_TARGET` picks one:

| Target | Host | Port | TLS | What it is |
|--------|------|------|-----|------------|
| `local` | `127.0.0.1` | `5432` | disabled | Laptop Postgres 17, restored from a dump |
| `prod` | `127.0.0.1` | `5433` | required | Aurora through the SSM tunnel |

Two consumers read that file, which is the point — before it existed, six
places carried their own copy of these values and they had drifted:

- `quant/shared/config.py` — `db_target()` and `db_settings()`, for the API,
  the worker, the CLI and `scripts/bybit_local_testnet.py`.
- `scripts/lib/db-target.sh` — for `appctl.sh`, `dbctl.sh`,
  `liquibase-deploy.sh` and `liquibase-verify.sh`.

Per field the file also lists the environment variables that override the
default, highest precedence first. That is how one `prod` entry serves both
ends: on a laptop the default `5433` is the tunnel, while on EC2 the
SSM-supplied `QUANTDB_HOST` and `QUANTDB_PORT` point straight at Aurora on
`5432`. `QUANTDB_CONNINFO` still bypasses everything with a literal DSN.

The file ships in the application image (`COPY config/db-targets.json` in the
`Dockerfile`) because the API reads it during startup and will not boot without
it.

!!! warning "`prod` may never resolve onto the local database"
    Both resolvers refuse a `prod` connection to loopback on the local port,
    because that combination can only be the laptop. It is reachable through a
    stale `QUANTDB_PORT=5432` in `.env`, and the failure it prevents is the bad
    kind: writes labelled prod landing in the local dump, or a "prod check"
    reporting local rows. The guard cannot fire on EC2, where prod is the
    cluster endpoint rather than loopback. If you hit it, remove `QUANTDB_PORT`
    from `.env` — the tunnel port is already the declared default — or select
    `DB_TARGET=local` if that is what you meant.

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
| `EXCHANGE_SECRETS_KEY` | SecureString | *(optional — dev auto-generates ephemeral if absent)* |
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
| `EXCHANGE_SECRETS_KEY` | SecureString | *(required — API refuses to boot without it)* |
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

After updating prod SSM params, restart the API container on the **prod EC2**
(not your laptop). Prefer a normal deploy (push to `main` or `workflow_dispatch`
on the deploy workflow). For a manual restart, resolve the instance ID first:

```bash
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name quant-compute \
  --region ap-southeast-1 \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"

aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters file://aws/scripts/ssm-ec2-deploy.json \
  --region ap-southeast-1
```

---

## Files that contain environment-specific values

| File | What it configures |
|------|--------------------|
| `config/db-targets.json` | What `local` and `prod` mean — host, port, database, user, TLS |
| `scripts/lib/db-target.sh` | Shell resolver for the above (`appctl`, `dbctl`, Liquibase) |
| `.env.example` | Template for developers — all values are dev defaults |
| `.env` | Actual dev config (gitignored, never committed) |
| `docker-compose.yml` | Base services — `USE_SSM=1` default, SSM-first for all envs |
| `docker-compose.prod.yml` | Prod behavioral flags only — `APP_ENV=prod`, `USE_SSM=1`, `COOKIE_SECURE=0` |
| `docker-compose.tls.yml` | TLS layer — `COOKIE_SECURE=1`, `DOMAIN`, certbot |
| `quant/shared/config.py` | Config loader — tries SSM first, falls back to `.env` if unreachable |
| `quant/api/auth/router.py` | Cookie `Secure` flag — reads `COOKIE_SECURE` or falls back to `APP_ENV` |
| `quant/api/main.py` | Swagger toggle, CORS — reads `APP_ENV`, `CORS_ORIGINS` |
| `aws/scripts/init-ssm-params.sh` | Bootstraps SSM parameters (run once) |
| `.cursor/hooks/ssm-port-forward-loop.sh` | Auto-starts SSM tunnel for dev |

---

## Docker Compose layering

```bash
# Dev (HTTP, local build)
docker compose up -d --build

# Prod — CI deploys via ECR pull (no --build on EC2). Manual equivalent:
export IMAGE_TAG=<git-sha>
export APP_IMAGE=<acct>.dkr.ecr.ap-southeast-1.amazonaws.com/quant-app:${IMAGE_TAG}
export NGINX_IMAGE=<acct>.dkr.ecr.ap-southeast-1.amazonaws.com/quant-nginx:${IMAGE_TAG}
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans

# Prod with TLS (requires DOMAIN)
export DOMAIN=yourdomain.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls.yml up -d
```
