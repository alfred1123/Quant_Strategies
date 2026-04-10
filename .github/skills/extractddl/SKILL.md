---
name: extractddl
description: 'Extract DDL (schema definitions) from the QuantDB PostgreSQL database. Use when you need to inspect live table definitions, compare DB state against source DDL files, or dump schema SQL for any of the project schemas (refdata, bt, trade, core_admin).'
---

# Extract DDL from QuantDB

## Bundled Script

`extract_ddl.sh` — extracts tables + procedures/functions for all project schemas.
Produces one `.sql` file per table/procedure, mirroring the `db/liquidbase/` layout.

```bash
# Run from project root (SSM port-forward must be active)
source .env
bash .github/skills/extractddl/extract_ddl.sh              # → db/syncddl/
bash .github/skills/extractddl/extract_ddl.sh /tmp/my_ddl  # → /tmp/my_ddl/
```

Output layout (mirrors `db/liquidbase/`):
```
db/syncddl/
  refdata/
    tables/APP.sql, INDICATOR.sql, ...
    procedures/SP_GET_ENUM.sql, ...
  bt/
    tables/STRATEGY.sql, RESULT.sql, ...
    procedures/SP_INS_STRATEGY.sql, ...
  trade/
    tables/DEPLOYMENT.sql, LOG.sql, TRANSACTION.sql
  core_admin/
    tables/LOG_PROC_DETAIL.sql
    procedures/CORE_INS_LOG_PROC.sql
```

Excluded automatically: `databasechangelog`, `databasechangeloglock` (Liquibase internals).

## When to Use

- Inspecting the live column structure of a table
- Comparing what is in the DB against the DDL files under `db/liquidbase/`
- Dumping the full DDL of one or more schemas to a file
- Checking for schema drift after manual changes

## Prerequisites

- SSM port-forward must be active on `localhost:5433` (VS Code task `SSM Port Forward (quantdb:5433)` runs automatically on folder open)
- `.env` must be sourced for connection credentials (`QUANTDB_USERNAME`, `QUANTDB_HOST`, `QUANTDB_PORT`, `QUANTDB_PASSWORD`)

## Connection

```bash
source .env
# Short alias used throughout this skill:
PGCONN="postgresql://${QUANTDB_USERNAME}@${QUANTDB_HOST}:${QUANTDB_PORT}/quantdb"
```

For `pg_dump`, export the password so prompts are suppressed:

```bash
export PGPASSWORD="${QUANTDB_PASSWORD}"
```

## Schemas

| Schema | Description |
|--------|-------------|
| `refdata` | Reference / lookup tables (indicators, strategies, asset types, etc.) |
| `bt` | Backtest run tables (strategy, result, API requests) |
| `trade` | Trade deployment and transaction tables |
| `core_admin` | Admin / user tables |

## Quick Inspection — psql Meta-Commands

```bash
# List all tables in a schema
source .env && TERM=dumb PAGER='' psql "$PGCONN" -c "\dt refdata.*"

# Describe a single table
source .env && TERM=dumb PAGER='' psql "$PGCONN" -c "\d refdata.app"

# Describe with storage details (sizes, indexes)
source .env && TERM=dumb PAGER='' psql "$PGCONN" -c "\d+ refdata.app"

# List all tables across all schemas
source .env && TERM=dumb PAGER='' psql "$PGCONN" --csv \
  -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('refdata','bt','trade','core_admin') ORDER BY schemaname, tablename"
```

Always set `TERM=dumb PAGER=''` to prevent psql from opening the alternate terminal buffer.

## Full Schema DDL Dump — pg_dump

```bash
# Single schema to stdout
source .env && export PGPASSWORD="${QUANTDB_PASSWORD}"
pg_dump "host=${QUANTDB_HOST} port=${QUANTDB_PORT} dbname=quantdb user=${QUANTDB_USERNAME}" \
  --schema-only --schema=refdata --no-owner --no-privileges \
  --exclude-table='refdata.databasechangelog*'

# Single schema to file
pg_dump "host=${QUANTDB_HOST} port=${QUANTDB_PORT} dbname=quantdb user=${QUANTDB_USERNAME}" \
  --schema-only --schema=refdata --no-owner --no-privileges \
  --exclude-table='refdata.databasechangelog*' \
  -f /tmp/refdata_ddl.sql

# All project schemas at once
for SCHEMA in refdata bt trade core_admin; do
  pg_dump "host=${QUANTDB_HOST} port=${QUANTDB_PORT} dbname=quantdb user=${QUANTDB_USERNAME}" \
    --schema-only --schema="${SCHEMA}" --no-owner --no-privileges \
    --exclude-table="${SCHEMA}.databasechangelog*" \
    -f "/tmp/${SCHEMA}_ddl.sql"
  echo "Dumped ${SCHEMA} → /tmp/${SCHEMA}_ddl.sql"
done
```

### Key pg_dump Flags

| Flag | Purpose |
|------|---------|
| `--schema-only` | DDL only — no INSERT data |
| `--schema=<name>` | Limit to a single schema |
| `--no-owner` | Omit `ALTER TABLE ... OWNER TO` noise |
| `--no-privileges` | Omit `GRANT/REVOKE` statements |
| `--exclude-table=<pattern>` | Skip Liquibase tracking tables (use pattern `<schema>.databasechangelog*`) |
| `-f <file>` | Write output to file instead of stdout |

## Single Table DDL — pg_dump

```bash
source .env && export PGPASSWORD="${QUANTDB_PASSWORD}"
pg_dump "host=${QUANTDB_HOST} port=${QUANTDB_PORT} dbname=quantdb user=${QUANTDB_USERNAME}" \
  --schema-only --table=refdata.app --no-owner --no-privileges
```

## Redirect Output to Avoid Alternate Buffer

Always redirect `pg_dump` or pipe `psql` results to avoid alternate buffer issues:

```bash
# Redirect to file then cat
source .env && export PGPASSWORD="${QUANTDB_PASSWORD}"
pg_dump "..." --schema-only --schema=refdata -f /tmp/out.sql && cat /tmp/out.sql
```

## Comparing DB vs Source DDL

After extracting live DDL, compare it against the source files:

```bash
# Example: compare live refdata.app against the source DDL file
source .env && export PGPASSWORD="${QUANTDB_PASSWORD}"
pg_dump "host=${QUANTDB_HOST} port=${QUANTDB_PORT} dbname=quantdb user=${QUANTDB_USERNAME}" \
  --schema-only --table=refdata.app --no-owner --no-privileges -f /tmp/live_app.sql

diff /tmp/live_app.sql db/liquidbase/refdata/tables/APP.sql
```

## Checking Liquibase Sync State

To see which changesets have been applied per schema:

```bash
source .env && TERM=dumb PAGER='' psql "$PGCONN" --csv \
  -c "SELECT id, author, exectype, dateexecuted FROM refdata.databasechangelog ORDER BY orderexecuted" \
  > /tmp/refdata_cl.txt && cat /tmp/refdata_cl.txt
```

Replace `refdata` with `bt`, `trade`, or `core_admin` for other schemas. The `public.databasechangelog` table tracks the master changelog (`000-schemas`).
