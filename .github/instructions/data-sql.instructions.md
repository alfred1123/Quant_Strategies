---
description: "Use when working on database schema, SQL migrations, data storage, or the SQLite layer. Covers naming conventions, schema design, and migration patterns for the planned db/ module."
applyTo: "db/**"
---
# Data & SQL Rules

## Schema Conventions

- Database name: `TradeBros`.
- Schema prefixes: `REFDATA.` (reference/lookup), `BACKTEST.` (backtest artifacts), `TRADE.` (live execution).
- Primary keys: `<TABLE>_ID` (UUID), version column `<TABLE>_VID` where applicable.
- Audit columns on every table: `USER_ID`, `CREATED_AT` (or `UPDATE_DB_TS`).
- Use `IS_CURRENT_IND` (Y/N) for soft versioning.

## Planned Tables

See `TODO.md` for full schema — key tables:
- `REFDATA.APP` — registered data sources
- `REFDATA.TM_INTERVAL` — time intervals
- `REFDATA.ORDER_STATE` / `REFDATA.TRANS_STATE` — state machines
- `BACKTEST.API_REQUEST` — cached API call metadata
- `TRADE.TRANSACTION` — executed trades

## Migration Rules

- Migrations go in `db/sql/migrations/` numbered sequentially: `001_create_refdata.sql`, `002_create_backtest.sql`.
- Every migration must be reversible — include `-- UP` and `-- DOWN` sections.
- Never drop columns in production without a prior release removing code references.
- SQLite files go in `db/store/` (gitignored for production data).

## Data Storage

- Cache API responses to minimize repeat queries (see `BACKTEST.API_REQUEST`).
- Raw data in `data/raw/`, processed in `data/processed/`.
- Never store API keys or secrets in the database.
