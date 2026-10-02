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
| `QUANTDB_HOST` | `127.0.0.1` (tunnel; `config/db-targets.json`) | `quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com` | JSON default; SSM `/quant/prod/` on EC2 |
| `QUANTDB_PORT` | leave unset — `config/db-targets.json` supplies `5433` | `5432` | SSM (prod); setting it to `5432` in `.env` is refused for `prod` |
| `QUANTDB_USERNAME` | shared DB user | same | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `QUANTDB_PASSWORD` | shared DB password | same | SSM `/quant/dev/` / SSM `/quant/prod/` |
| `APP_ENV` | `dev` (default) | `prod` | `docker-compose.prod.yml` |
| `USE_SSM` | `0` when `DB_TARGET=local`. Unset otherwise: SSM loads only if the value is `1` | `1` | `scripts/appctl.sh`, `docker-compose.dev.yml`; `${USE_SSM:-1}` in `docker-compose.yml` |
| `COOKIE_SECURE` | unset (defaults to `APP_ENV == prod`) | `0` (HTTP) / `1` (HTTPS) | `docker-compose.prod.yml` / `docker-compose.cloudflare.yml` |
| `CORS_ORIGINS` | SSM `/quant/dev/` or `.env` (in-code default `http://localhost:5173`) | SSM `/quant/prod/` (public site URL(s)) | SSM / `.env` |
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
Developer laptop                                 Production EC2
./scripts/appctl.sh dev start                    docker compose -f docker-compose.yml
(uvicorn + Vite on the host)                          -f docker-compose.prod.yml up
        │                                                     │
        ├─ DB_TARGET=local                                    ▼
        │    USE_SSM=0                                 APP_ENV=prod
        │    appctl.sh + docker-compose.dev.yml        USE_SSM=1
        │    .env + config/db-targets.json                   │
        │    Postgres 127.0.0.1:5432                         ▼
        │    redis + worker (compose.dev)            SSM /quant/prod/*
        │                                            QUANTDB_HOST = RDS endpoint
        └─ DB_TARGET=prod (file default)             QUANTDB_PORT = 5432
             USE_SSM=1 loads SSM /quant/<APP_ENV>/   JWT_SECRET, CORS_ORIGINS,
             otherwise .env                          EXCHANGE_SECRETS_KEY (required)
             tunnel 127.0.0.1:5433 → Aurora :5432           │
                    │                                       ▼
                    ▼                                quant/shared/config.py
             quant/shared/config.py                  load_config() → _load_from_ssm("prod")
             load_config()
```

!!! note "There is no dev EC2"
    **Dev and prod share one compute host.** Laptops reach Aurora by SSM
    port-forwarding through the **prod** EC2 instance (`quant-compute` stack).
    There is no separate dev instance — do not hardcode an instance ID in docs
    or scripts; resolve it from CloudFormation (see below) or use
    `./scripts/appctl.sh prod tunnel start`, which reads `SSM_TARGET_INSTANCE`
    from `.env` when set. Local/dev (`DB_TARGET=local`) does not start this
    tunnel.

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

Optional fallback: set `SSM_TARGET_INSTANCE` in `.env` (prod tunnel) or
`EC2_INSTANCE_ID` in GitHub Actions repo variables if CFN lookup fails.

---

## Prod tunnel — laptop to Aurora on 5433

`appctl.sh prod` without `tunnel` is the **Docker Compose stack**. The
forward that puts Aurora on the laptop is a different subcommand:

```bash
aws sso login --profile alfcheun
./scripts/appctl.sh prod tunnel start
./scripts/appctl.sh prod tunnel status
pg_isready -h 127.0.0.1 -p 5433
```

| Port | What it is | Who starts it |
|------|------------|---------------|
| `5432` | Local Postgres (`DB_TARGET=local`) | `systemctl` / `dbctl` — **no tunnel** |
| `5433` | Prod Aurora via SSM through prod EC2 | `./scripts/appctl.sh prod tunnel start` |

`dev tunnel` is the same handler under the old name. `dev start` with
`DB_TARGET=local` must not be asked to open `:5433`.

---

## Restoring dev environment

`load_config()` in `quant/shared/config.py` reads SSM only when `USE_SSM=1`. Native `./scripts/appctl.sh dev start` loads `.env` unless that flag is set. `DB_TARGET=local` forces `USE_SSM=0`. The Compose stack in `docker-compose.yml` defaults `USE_SSM` to `1`, then loads `/quant/<APP_ENV>/` and falls back to `.env` if Parameter Store is unreachable.

```bash
cp .env.example .env
aws sso login --profile alfcheun   # only when USE_SSM=1
```

Names and defaults: [Environment variables](../env-vars.md). How to run: [Getting Started](../getting-started.md).

Local/dev (`DB_TARGET=local`) talks to Postgres on `:5432` and **does not
need a tunnel**. Reaching **prod Aurora** from the laptop is a different
command — see [Prod tunnel](#prod-tunnel-laptop-to-aurora-on-5433).

When `DB_TARGET=prod`, `dev start` will start that prod tunnel if `:5433`
is down. Verify:

```bash
./scripts/appctl.sh prod tunnel status
pg_isready -h 127.0.0.1 -p 5433
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

---

## Local database

`DB_TARGET=local` uses host Postgres on `:5432` and does not open a tunnel. `scripts/appctl.sh` exports `USE_SSM=0` for that target, and `docker-compose.dev.yml` sets the same on the worker. Both ends resolve host and port from `config/db-targets.json` (next section). Setup, the first copy, and daily commands: [Getting Started](../getting-started.md). Dump and restore: [Database dump and restore](../guides/database-dump-restore.md).

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
| `quant/shared/config.py` | `load_config()` reads SSM only when `USE_SSM=1`; otherwise `.env` |
| `quant/api/auth/router.py` | Cookie `Secure` flag — reads `COOKIE_SECURE` or falls back to `APP_ENV` |
| `quant/api/main.py` | Swagger toggle, CORS — reads `APP_ENV`, `CORS_ORIGINS` |
| `aws/scripts/init-ssm-params.sh` | Bootstraps SSM parameters (run once) |
| `.cursor/hooks/ssm-port-forward-loop.sh` | Optional Cursor hook — same prod tunnel on `:5433` |

---

## Docker Compose layering

```bash
# Compose base (HTTP). Laptop dev is `./scripts/appctl.sh dev start`, not this file.
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
