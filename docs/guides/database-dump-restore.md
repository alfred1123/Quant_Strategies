# Database dump & restore

Copy **Aurora (prod)** into a **local Postgres 17** database for offline dev, faster iteration, or safe experimentation. All commands use [`scripts/dbctl.sh`](../../scripts/dbctl.sh).

!!! danger "Sensitive data"
    Dumps include **`CORE_ADMIN.APP_USER` password hashes**, **`API_CREDENTIAL` ciphertext**, strategies, and queue history. Files live in `db/dumps/` (**gitignored**). **Never commit** a dump. Share only over a secure channel. Treat restored local DBs as **prod-equivalent secrets**.

---

## When to use this

| Goal | Use dump/restore? |
|------|-------------------|
| Work **offline** with real REFDATA + users + strategies | **Yes** — set `DB_TARGET=local` after restore |
| Fresh empty schema only (no prod data) | **No** — use `./scripts/dbctl.sh reset` + `DB_TARGET=local ./scripts/liquibase-deploy.sh` |
| Prod **backup** / disaster recovery | **No** — Aurora snapshots + `DeletionPolicy: Retain` (see [Infrastructure](../architecture/infrastructure.md)). `dbctl` is for **developer laptops**, not prod ops. |
| Apply DDL to prod | **No** — use [`liquibase-deploy.sh`](../../scripts/liquibase-deploy.sh) |

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **AWS SSO** | `aws sso login --profile alfcheun` (or your profile) |
| **SSM tunnel** | Aurora reachable at `127.0.0.1:5433` — see below |
| **`.env`** | `QUANTDB_PASSWORD` = Aurora admin password (same as prod tunnel) |
| **PostgreSQL 17 client** | `pg_dump` / `pg_restore` — script uses `/usr/lib/postgresql/17/bin/pg_dump` |
| **Local Postgres 17 server** | Only for **restore** — `sudo systemctl start postgresql` |

Tunnel (automatic via Cursor hook, or manual):

```bash
./scripts/appctl.sh dev tunnel start
# verify
pg_isready -h localhost -p 5433
```

The tunnel forwards **localhost:5433 → Aurora** through the **prod EC2** SSM
jump host (there is no separate dev instance). Target instance ID is resolved
from `SSM_TARGET_INSTANCE` in `.env` or the default in `appctl.sh` — see
[Dev vs Prod — resolve instance ID](../architecture/dev-vs-prod.md#resolve-the-current-prod-ec2-instance-id).

---

## Quick start — prod → local

One-time local DB setup:

```bash
sudo apt install -y postgresql-17 postgresql-client-17   # Ubuntu/WSL example
./scripts/dbctl.sh reset
```

Dump from Aurora and restore locally:

```bash
source .env
./scripts/dbctl.sh dump
./scripts/dbctl.sh restore          # newest file in db/dumps/
./scripts/dbctl.sh bootstrap-roles  # recreate quant_app role omitted from dump
```

Use local DB in dev:

```bash
echo 'DB_TARGET=local' >> .env
./scripts/appctl.sh dev start       # uvicorn + vite + redis + worker
```

See [Dev vs Prod — local Postgres](../architecture/dev-vs-prod.md#optional-point-dev-at-a-local-postgres).

---

## Commands reference

| Command | What it does |
|---------|----------------|
| `./scripts/dbctl.sh dump` | `pg_dump` Aurora via tunnel → `db/dumps/quantdb_YYYYMMDD_HHMMSS.dump` |
| `./scripts/dbctl.sh restore [file]` | `pg_restore` into local `quantdb` (default: latest dump) |
| `./scripts/dbctl.sh reset` | Drop/recreate local `quantdb` + `quant_admin` user |
| `./scripts/dbctl.sh bootstrap-roles` | Create local `quant_app` role + schema grants |
| `./scripts/dbctl.sh status` | Local cluster, schema table counts, latest dump path |
| `./scripts/dbctl.sh psql` | Open `psql` on local `quantdb` |

Dump format: **custom** (`-Fc`), compressed (`-Z 6`). Typical size ~3–5 MB.

---

## Dump prod (detail)

```bash
source .env
./scripts/appctl.sh dev tunnel start   # if not already up
./scripts/dbctl.sh dump
```

What happens:

1. Checks tunnel on `127.0.0.1:5433`
2. Loads `QUANTDB_PASSWORD` from `.env`
3. Sets `PGSSLMODE=require` (Aurora via tunnel expects SSL)
4. Writes `db/dumps/quantdb_<timestamp>.dump`

Restore a **specific** file:

```bash
./scripts/dbctl.sh restore db/dumps/quantdb_20260529_000103.dump
```

---

## Restore (detail)

Restore **destroys and recreates objects** in local `quantdb` (`pg_restore --clean --if-exists`). It does **not** drop the database itself — run `reset` first if you want an empty database.

After restore:

1. **`bootstrap-roles`** — cluster roles are not included in dumps; local apps using `quant_app` need this step.
2. Optional: `DB_TARGET=local ./scripts/liquibase-deploy.sh` if you need SP/DDL drift fixed after a old dump.

Verify:

```bash
./scripts/dbctl.sh status
./scripts/dbctl.sh psql
# then: SELECT count(*) FROM refdata.app;
```

---

## Manual `pg_dump` (without dbctl)

If `dbctl.sh` is unavailable, equivalent dump:

```bash
source .env
export PGPASSWORD="$QUANTDB_PASSWORD"
export PGSSLMODE=require

pg_dump -h 127.0.0.1 -p 5433 -U quant_admin -d quantdb \
  -Fc -Z 6 -v \
  -f db/dumps/quantdb_manual.dump
```

Equivalent restore:

```bash
export PGPASSWORD=LetsGetRich888   # local quant_admin default in dbctl
pg_restore -h localhost -p 5432 -U quant_admin -d quantdb \
  --no-owner --no-privileges --clean --if-exists -j 4 -v \
  db/dumps/quantdb_manual.dump
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `SSM tunnel is not running on :5433` | `./scripts/appctl.sh dev tunnel start`; confirm AWS SSO; resolve current instance via [Dev vs Prod](../architecture/dev-vs-prod.md#resolve-the-current-prod-ec2-instance-id) if you override `SSM_TARGET_INSTANCE` |
| `SSL connection required` / SSL errors on dump | Ensure `PGSSLMODE=require` (set automatically by `dbctl dump`) |
| `.env missing QUANTDB_PASSWORD` | Copy from `.env.example`; use Aurora password from SSM `/quant/prod/QUANTDB_PASSWORD` |
| `pg_dump: command not found` / wrong version | Install `postgresql-client-17`; script expects `/usr/lib/postgresql/17/bin/pg_dump` |
| `Local Postgres is not running` | `sudo systemctl start postgresql` |
| Restore warnings about roles/owners | Expected — run `bootstrap-roles` |
| Restore hangs on large DB | Normal for `-j 4`; wait or reduce parallelism |
| Login fails after restore | Users come from dump — use prod password or admin reset ([Login runbook](../design/login.md)) |
| `EXCHANGE_SECRETS_KEY` mismatch | Local dev auto-generates Fernet key; **re-save credentials** if decrypt fails |

---

## Security checklist

- [ ] Dump files stay under `db/dumps/` (gitignored)
- [ ] Never `git add` `*.dump`
- [ ] Do not store dumps in Slack/email unencrypted
- [ ] Local `quantdb` uses default password `LetsGetRich888` — **localhost only**, not exposed
- [ ] When done with prod copy, `./scripts/dbctl.sh reset` if machine is shared

---

## Related

- [Dev vs Prod — local Postgres](../architecture/dev-vs-prod.md#optional-point-dev-at-a-local-postgres)
- [Database architecture](../architecture/database.md)
- [Environment variables — `DB_TARGET`](../env-vars.md)
- [Login & user provisioning](../design/login.md)
