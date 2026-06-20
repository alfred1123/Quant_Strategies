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
| [`setup.sh`](../setup.sh) | Create `env/`, install Python + frontend deps |
| [`scripts/appctl.sh`](../scripts/appctl.sh) | Start/stop **dev** (uvicorn + Vite) or **prod** (Docker Compose) |
| [`scripts/dbctl.sh`](../scripts/dbctl.sh) | Dump/restore/reset **local** Postgres (`:5432`) |
| [`scripts/liquibase-deploy.sh`](../scripts/liquibase-deploy.sh) | Apply pending DB migrations |
| [`scripts/liquibase-verify.sh`](../scripts/liquibase-verify.sh) | Dry-run: validate changelogs, preview SQL (no apply) |

Admin / debug helpers (see [Login](design/login.md)): `scripts/hash_password.py`, `scripts/diag_login.py`.

## Run the app (dev)

[`appctl.sh`](../scripts/appctl.sh) starts the FastAPI backend and Vite frontend. With `DB_TARGET=local` it also brings up Redis + the queue worker via [`docker-compose.dev.yml`](../docker-compose.dev.yml).

### Option A — Shared prod DB (default)

Uses Aurora via SSM port-forward on `localhost:5433`. No local Postgres or Docker required (backtests queue on the shared worker in prod).

```bash
./scripts/appctl.sh dev tunnel start   # once per session
./scripts/appctl.sh dev start
```

Open **http://localhost:5173** (API: http://localhost:8000).

### Option B — Local DB copy

Offline dev on `localhost:5432` with a full local backtest queue. Requires **Docker** for Redis + worker. See [Database dump & restore](guides/database-dump-restore.md) for detail.

```bash
./scripts/appctl.sh dev tunnel start   # needed for dump from Aurora
./scripts/dbctl.sh reset
./scripts/dbctl.sh dump
./scripts/dbctl.sh restore
./scripts/dbctl.sh bootstrap-roles

# in .env: DB_TARGET=local
./scripts/appctl.sh dev start          # uvicorn + vite + docker-compose.dev.yml
```

## Database migrations (Liquibase)

Schema changes live under `db/liquidbase/`. Use **`DB_TARGET`** to pick the port (see [Environment variables](env-vars.md)):

| Target | Port | When |
|---|---|---|
| `DB_TARGET=local` | `:5432` | Local Postgres after `dbctl restore` |
| `DB_TARGET=prod` (default) | `:5433` | Aurora via SSM tunnel |

```bash
# Preview pending changes (safe — does not apply)
./scripts/liquibase-verify.sh --offline   # XML parse only
DB_TARGET=local ./scripts/liquibase-verify.sh

# Apply pending migrations
DB_TARGET=local ./scripts/liquibase-deploy.sh

# Prod (SSM tunnel must be up; truncates/migrations may wipe BT data — read release notes first)
DB_TARGET=prod ./scripts/liquibase-deploy.sh
```

After a fresh local restore, always run deploy so procs/constraints match source:

```bash
DB_TARGET=local ./scripts/liquibase-deploy.sh
```

!!! tip "Local port override"
    If `.env` sets `LIQUIBASE_COMMAND_URL=…:5433`, it overrides `DB_TARGET=local`. Either unset it or pass an explicit URL:

    ```bash
    DB_TARGET=local LIQUIBASE_COMMAND_URL=jdbc:postgresql://127.0.0.1:5432/quantdb?sslmode=disable ./scripts/liquibase-deploy.sh
    ```

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
