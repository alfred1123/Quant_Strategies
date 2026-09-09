# Getting Started

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Used by `setup.sh` → `env/` |
| Node.js 24+ | Installed by `setup.sh` from `.nvmrc` |
| Git | Clone the repo |
| Linux / macOS / WSL | Bash scripts below |
| AWS CLI + SSO | Shared prod DB (default) and prod Liquibase deploy |
| Docker + Compose v2 | Local queue worker (`DB_TARGET=local`) or `appctl prod` |
| Java 17+ | Liquibase — installed automatically by deploy/verify scripts |
| PostgreSQL 17 | Only for a **local** DB copy (`DB_TARGET=local`) |

## One-time setup

```bash
git clone https://github.com/alfred1123/Quant_Strategies.git
cd Quant_Strategies
cp .env.example .env   # fill in keys — ask admin for DB password / AWS access
./setup.sh             # Python venv + npm install
```

## Scripts at a glance

| Script | Purpose |
|---|---|
| `setup.sh` | Create `env/`, install Python + frontend deps |
| `scripts/appctl.sh` | Start/stop **dev** (uvicorn + Vite) or **prod** (Docker Compose). `prod tunnel` is the laptop → Aurora forward on `:5433` |
| `scripts/dbctl.sh` | Dump/restore/reset **local** Postgres (`:5432`) |
| `scripts/liquibase-deploy.sh` | Apply pending DB migrations |
| `scripts/liquibase-verify.sh` | Dry-run: validate changelogs, preview SQL (no apply) |

Admin / debug helpers (see [Login](design/login.md)): `scripts/hash_password.py`, `scripts/diag_login.py`.

## Run the app (dev)

`scripts/appctl.sh` first argument is **how the app runs** (`dev` = uvicorn + Vite on the laptop; `prod` = Docker Compose). It is not which database you talk to.

**Local/dev does not need a tunnel.** `DB_TARGET=local` uses Postgres on `:5432`.

**Prod Aurora from a laptop** is a different command: the SSM port-forward on `:5433`. That is `prod tunnel`, not `dev start`.

### Option A — Local DB (no tunnel)

Offline (or isolated) dev on `localhost:5432` with a local backtest queue. Requires **Docker** for Redis + worker. See [Database dump & restore](guides/database-dump-restore.md) for the first dump.

```bash
# in .env: DB_TARGET=local
./scripts/appctl.sh dev start          # uvicorn + vite + docker-compose.dev.yml
```

Open **http://localhost:5173** (API: http://localhost:8000).

A dump from Aurora (one-time) does need the prod tunnel — that is Option B's command, used only for `dbctl dump`.

### Option B — Prod Aurora from the laptop (prod tunnel)

Uses Aurora through SSM on `localhost:5433`. The laptop is not on the VPC; the forward goes through the **prod** EC2 jump host. AWS SSO must be valid. `dev start` still runs uvicorn/Vite; it does not start this tunnel.

```bash
aws sso login --profile alfcheun
./scripts/appctl.sh prod tunnel start
pg_isready -h 127.0.0.1 -p 5433

# in .env: DB_TARGET=prod  (or leave DB_TARGET unset)
./scripts/appctl.sh dev start
```

```bash
# First-time local copy: tunnel, then dump, then switch to Option A
./scripts/appctl.sh prod tunnel start
./scripts/dbctl.sh reset
./scripts/dbctl.sh dump
./scripts/dbctl.sh restore
./scripts/dbctl.sh bootstrap-roles
# then set DB_TARGET=local and use Option A — no tunnel after that
```

## Database migrations (Liquibase)

Schema changes live under `db/liquidbase/`. Use **`DB_TARGET`** to pick the port (see [Environment variables](env-vars.md)):

| Target | Port | When |
|---|---|---|
| `DB_TARGET=local` | `:5432` | Local Postgres after `dbctl restore` |
| `DB_TARGET=prod` (default) | `:5433` | Aurora via **prod tunnel** (`./scripts/appctl.sh prod tunnel start`) |

```bash
# Preview pending changes (safe — does not apply)
./scripts/liquibase-verify.sh --offline   # XML parse only
DB_TARGET=local ./scripts/liquibase-verify.sh

# Apply pending migrations
DB_TARGET=local ./scripts/liquibase-deploy.sh

# Prod schema (Aurora) — GitHub Actions → **database** workflow (verify or deploy)
# Or: bash aws/scripts/liquibase-ssm-run.sh verify main

# Prod Aurora from the laptop (prod tunnel on :5433 must be up)
./scripts/appctl.sh prod tunnel start
PROD_DB_PORT=5433 APP_ENV=prod USE_SSM=1 ./scripts/liquibase-verify.sh
PROD_DB_PORT=5433 APP_ENV=prod USE_SSM=1 ./scripts/liquibase-deploy.sh
```

After a fresh local restore, always run deploy so procs/constraints match source:

```bash
DB_TARGET=local ./scripts/liquibase-deploy.sh
```

!!! tip "Local port override"
    An explicit `DB_TARGET` always wins over `LIQUIBASE_COMMAND_URL`. If `.env` sets
    `LIQUIBASE_COMMAND_URL=…:5433` and you run `DB_TARGET=local`, the script uses
    the local target URL — a shell-exported URL that contradicts `DB_TARGET` makes
    the script exit with a conflict error. To aim at a custom URL without a target,
    leave `DB_TARGET` unset and set `LIQUIBASE_COMMAND_URL` directly.

Compare live DB vs source DDL: `.github/skills/extractddl/extract_ddl.sh` → diff against `db/liquidbase/` (see [Database](architecture/database.md)).

## Docker

| Mode | Command | What runs |
|---|---|---|
| **Dev support stack** | `./scripts/appctl.sh dev start` with `DB_TARGET=local` | `redis` + `worker` from `docker-compose.dev.yml` |
| **Prod stack (local smoke test)** | `./scripts/appctl.sh prod start` | `docker-compose.yml` + `docker-compose.prod.yml` — nginx, api, worker, redis |
| **Prod stack (EC2)** | Deploy pipeline / `aws/scripts/ec2-deploy.sh` | Same compose files on the server |

Dev support stack only — when not using `appctl`:

```bash
docker compose -f docker-compose.dev.yml up -d        # redis + worker
docker compose -f docker-compose.dev.yml logs -f worker
docker compose -f docker-compose.dev.yml down
```

Prod stack logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

## Day-to-day commands

| Command | Purpose |
|---|---|
| `./scripts/appctl.sh dev status` | Backend, frontend, tunnel, DB, dev Docker stack |
| `./scripts/appctl.sh dev stop` | Graceful shutdown |
| `./scripts/appctl.sh dev kill` | Force stop everything |
| `./scripts/appctl.sh dev restart` | Stop + start |
| `./scripts/appctl.sh prod status` | Production compose containers |
| `./scripts/dbctl.sh status` | Local Postgres + latest dump |
| `./scripts/dbctl.sh psql` | Shell into local `quantdb` |

Logs: `log/backend.log`, `log/frontend.log`, `log/tunnel.log`.

## Login

The SPA requires an authenticated session. Accounts are **admin-managed** — no self-signup. Provision users with `scripts/hash_password.py`. See [Login & Authentication](design/login.md).

## Wiki

```bash
source env/bin/activate
mkdocs serve
```

Open **http://localhost:8001**.

## Further reading

- [Dev vs prod](architecture/dev-vs-prod.md) — `DB_TARGET`, tunnel, Docker worker
- [Database](architecture/database.md) — Liquibase layout, release workflow
- [Environment variables](env-vars.md) — `.env` reference
- [New user: run a backtest](guides/new-user-website.md) — UI walkthrough
