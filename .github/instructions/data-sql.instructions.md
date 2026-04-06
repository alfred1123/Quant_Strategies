---
description: "Use when working on database schema, SQL migrations, data storage, or the Postgres layer. Covers naming conventions, schema design, and migration patterns for the db/ module."
applyTo: "db/**"
---
# Data & SQL Rules

## Schema Conventions

- Database name: `TradeBros`. Engine: PostgreSQL 16 (RDS Serverless v2).
- Schema prefixes: `REFDATA.` (reference/lookup), `BT.` (backtest artifacts), `TRADE.` (live execution).
- Primary keys: `<TABLE>_ID` — use `UUID` for entity PKs, `INTEGER GENERATED ALWAYS AS IDENTITY` for sequence PKs.
- Version column `<TABLE>_VID` where applicable.
- Audit columns on every table: `USER_ID TEXT`, `CREATED_AT TIMESTAMPTZ` (or `UPDATED_AT TIMESTAMPTZ`).
- Use `IS_CURRENT_IND CHAR(1)` for soft versioning — no default, no CHECK constraint.

## Postgres Type Rules

- Timestamps: `TIMESTAMPTZ` — never `TEXT` or `CURRENT_TIMESTAMP`. No `DEFAULT`.
- Timezone: all timestamps are UTC. Set DB timezone with `SET timezone = 'UTC';`.
- UUIDs: `UUID` — never `TEXT` for ID columns.
- Flags: `CHAR(1)` with no default — never `BOOLEAN`, never `INTEGER` (0/1). No `CHECK` constraints.
- **No CHECK constraints**: value validation is enforced at the application layer, not in DDL.
- **No DEFAULT values**: do not use `DEFAULT` on any column. All values supplied by the application.
- Money/decimals: `NUMERIC` — never `REAL` or `FLOAT`.
- JSON columns: `JSONB` — never `TEXT` for structured payloads.
- Auto-increment: `INTEGER GENERATED ALWAYS AS IDENTITY` — never `AUTOINCREMENT` (SQLite syntax).
- Strings: `TEXT` is preferred; use `VARCHAR(n)` only when a max-length constraint is needed.

## Planned Tables

See `TODO.md` for full schema — key tables:
- `REFDATA.APP` — registered data sources
- `REFDATA.TM_INTERVAL` — time intervals
- `REFDATA.ORDER_STATE` / `REFDATA.TRANS_STATE` — state machines
- `BT.API_REQUEST` — cached API call metadata
- `TRADE.TRANSACTION` — executed trades

## Migration Rules

- Migrations go in `db/sql/migrations/` numbered sequentially: `001_create_refdata.sql`, `002_create_bt.sql`.
- Every migration must be reversible — include `-- UP` and `-- DOWN` sections.
- Never drop columns in production without a prior release removing code references.
- SQLite files go in `db/store/` (gitignored for production data).

## Data Storage

- Cache API responses to minimize repeat queries (see `BT.API_REQUEST`).
- Raw data in `data/raw/`, processed in `data/processed/`.
- Never store API keys or secrets in the database.
