# Database dump & restore

Copy **Aurora (prod)** into a **local Postgres 17** database for offline dev, faster iteration, or safe experimentation. All commands use `scripts/dbctl.sh`.

!!! danger "Sensitive data"
    Dumps include **`CORE_ADMIN.APP_USER` password hashes**, **`API_CREDENTIAL` ciphertext**, strategies, and queue history. Files live in `db/dumps/` (**gitignored**). **Never commit** a dump. Share only over a secure channel. Treat restored local DBs as **prod-equivalent secrets**.

---

## When to use this

| Goal | Use dump/restore? |
|------|-------------------|
| Work **offline** with real REFDATA + users + strategies | **Yes** — set `DB_TARGET=local` after restore |
| Fresh empty schema only (no prod data) | **No** — use `./scripts/dbctl.sh reset` + `DB_TARGET=local ./scripts/liquibase-deploy.sh` |
| Prod **backup** / disaster recovery | **Not with `dbctl`** — it is for **developer laptops**. Use an Aurora snapshot first, then [Prod backup to S3](#prod-backup-to-s3) if you want a copy off Aurora (see [Infrastructure](../architecture/infrastructure.md)). |
| Apply DDL to prod | **No** — use `scripts/liquibase-deploy.sh` |

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **AWS SSO** | `aws sso login --profile alfcheun` (or your profile) |
| **Prod tunnel** | Aurora reachable at `127.0.0.1:5433` — `./scripts/appctl.sh prod tunnel start` |
| **`.env`** | `QUANTDB_PASSWORD` = Aurora admin password (same as prod tunnel) |
| **PostgreSQL 17 client** | `pg_dump` / `pg_restore` — script uses `/usr/lib/postgresql/17/bin/pg_dump` |
| **Local Postgres 17 server** | Only for **restore** — `sudo systemctl start postgresql` |

The dump reads **prod Aurora**. Local/dev on `:5432` does not need this
forward. Start the **prod tunnel**:

```bash
./scripts/appctl.sh prod tunnel start
pg_isready -h 127.0.0.1 -p 5433
```

The forward is laptop `:5433` → Aurora `:5432` through the **prod** EC2 SSM
jump host. Target instance ID is `SSM_TARGET_INSTANCE` in `.env` or the
default in `appctl.sh` — see [Dev vs Prod — resolve instance ID](../architecture/dev-vs-prod.md#resolve-the-current-prod-ec2-instance-id).

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

Dump format: **custom** (`-Fc`), compressed (`-Z 6`). **283 MiB** as of 2026-09-22
— the ~3–5 MB this guide used to quote predates the `PRICE_BAR` history, so plan
for minutes, not seconds, and expect the tunnel to be the limiting factor.

---

## Prod backup to S3

A dump taken **for prod** does not go through the tunnel at all — it runs on the
EC2 host, which reaches Aurora directly on `:5432`, and lands in
`s3://quant-db-dumps-539163478329/dumps/`. The host has no Postgres 17 client,
so `pg_dump` runs from the `postgres:17-alpine` image (16 refuses a 17.9 server),
and the file is deleted from `/var/tmp` after upload — it carries password hashes
and `API_CREDENTIAL` ciphertext.

```bash
aws ssm send-command --instance-ids "$(aws cloudformation describe-stacks \
    --stack-name quant-compute \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)" \
  --document-name AWS-RunShellScript --timeout-seconds 900 \
  --parameters commands='["bash -s <<'\''EOS'\''
set -euo pipefail
gp() { aws ssm get-parameter --name /quant/prod/$1 --with-decryption \
       --region ap-southeast-1 --query Parameter.Value --output text; }
PGPASSWORD=$(gp QUANTDB_PASSWORD); export PGPASSWORD
F=quantdb_$(date -u +%Y%m%dT%H%M%SZ).dump
docker run --rm -e PGPASSWORD -e PGSSLMODE=require -v /var/tmp:/dump postgres:17-alpine \
  pg_dump -h $(gp QUANTDB_HOST) -p $(gp QUANTDB_PORT) -U $(gp QUANTDB_USERNAME) \
          -d quantdb -Fc -Z 6 -f /dump/$F
aws s3 cp /var/tmp/$F s3://quant-db-dumps-539163478329/dumps/$F
rm -f /var/tmp/$F
EOS"]'
```

The bucket blocks all public access, encrypts with AES256, expires `dumps/`
objects after **90 days**, and grants `PutObject` to `quant-ec2-role` through its
bucket policy — the instance role itself was not changed. The object is an
ordinary `-Fc` dump, so `./scripts/dbctl.sh restore <file>` consumes it after an
`aws s3 cp` down.

This is a **second** line of defence, not the first: Aurora keeps 7 days of
automated backups, and a manual snapshot (`quantdb-pre-infra-reorg-20260923`) is
the cheaper pre-change safety net because it needs no client, no transfer, and
no bucket. Take the S3 dump when you want a copy that outlives the cluster or
restores somewhere that is not Aurora.

---

## Dump prod (detail)

```bash
source .env
./scripts/appctl.sh prod tunnel start   # if not already up
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
| `Prod tunnel is not running on :5433` | `./scripts/appctl.sh prod tunnel start`; confirm AWS SSO; resolve current instance via [Dev vs Prod](../architecture/dev-vs-prod.md#resolve-the-current-prod-ec2-instance-id) if you override `SSM_TARGET_INSTANCE` |
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
