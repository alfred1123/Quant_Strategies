---
name: db-ddl
description: 'Write or modify Postgres DDL for the TradeBros database. Use when creating tables, altering columns, adding indexes, or writing Liquibase changesets under db/liquidbase/. Enforces project type conventions (UUID, TIMESTAMPTZ, JSONB, CHAR(1) Y/N flags, NUMERIC, IDENTITY).'
---

# DB DDL Skill

## When to Use

- Creating a new table SQL file under `db/liquidbase/<schema>/tables/`
- Altering an existing table DDL
- Adding indexes, constraints, or foreign keys
- Writing Liquibase changelog entries that reference DDL files
- Reviewing DDL for type correctness

## Postgres Type Conventions

Always use native Postgres types. Never use SQLite-style types.

| Concept | Use | Never |
|---------|-----|-------|
| Timestamps | `TIMESTAMPTZ` | `TEXT`, `CURRENT_TIMESTAMP`, `DEFAULT now()` |
| Timezone | All `CREATED_AT` / `UPDATED_AT` store UTC. Set DB timezone: `SET timezone = 'UTC';` | Session-local or unspecified timezones |
| UUIDs | `UUID` | `TEXT` for ID columns |
| Booleans / flags | `CHAR(1)` — no default, no CHECK | `BOOLEAN`, `INTEGER` (0/1) |
| Money / decimals | `NUMERIC` | `REAL`, `FLOAT` |
| JSON payloads | `JSONB` | `TEXT` |
| Auto-increment PK | `INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| Strings | `TEXT` (preferred) or `VARCHAR(n)` if max-length needed | no difference in Postgres |

## File Layout

```
db/liquidbase/
├── quantdb-changelog.xml          # master Liquibase changelog
├── bt/tables/                     # BT schema DDL files
│   ├── STRATEGY.sql
│   ├── RESULT.sql
│   ├── API_REQUEST.sql
│   └── API_REQUEST_PAYLOAD.sql
├── trade/tables/                  # TRADE schema DDL files
│   ├── DEPLOYMENT.sql
│   ├── LOG.sql
│   └── TRANSACTION.sql
└── refdata/
    ├── tables/                    # REFDATA schema DDL files
    │   ├── APP.sql
    │   ├── ASSET_TYPE.sql
    │   ├── INDICATOR.sql
    │   ├── SIGNAL_TYPE.sql
    │   ├── TM_INTERVAL.sql
    │   ├── ORDER_STATE.sql
    │   ├── TRANS_STATE.sql
    │   ├── API_LIMIT.sql
    │   └── TICKER_MAPPING.sql
    └── data/                      # REFDATA seed INSERT files
        ├── ASSET_TYPE.sql
        ├── INDICATOR.sql
        └── SIGNAL_TYPE.sql
```

## Naming Rules

- Schemas: `BT`, `TRADE`, `REFDATA`
- Tables: `SCHEMA.TABLE_NAME` (UPPER_CASE)
- Columns: `UPPER_CASE`
- Primary keys: `<TABLE>_ID` — `UUID` for entities, `INTEGER GENERATED ALWAYS AS IDENTITY` for sequences
- Version columns: `<TABLE>_VID INTEGER`
- Audit columns (every table): `USER_ID TEXT`, `CREATED_AT TIMESTAMPTZ` or `UPDATED_AT TIMESTAMPTZ`
- Soft versioning: `IS_CURRENT_IND CHAR(1)` — no default, no CHECK constraint
- **No foreign keys**: Do NOT use `REFERENCES` or `FOREIGN KEY` constraints. Relationships are enforced at the application layer. Column names still follow the `<PARENT_TABLE>_ID` convention to document intent.
- **No CHECK constraints**: Do NOT use `CHECK` constraints. Value validation is enforced at the application layer. CHECK constraints slow down purge/update operations on large tables.
- **No DEFAULT values**: Do NOT use `DEFAULT` on any column. All values must be explicitly supplied by the application layer.

## Template — New Table

```sql
CREATE TABLE <SCHEMA>.<TABLE> (
    <TABLE>_ID     UUID PRIMARY KEY,        -- or INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY
    -- domain columns --
    -- reference columns use <PARENT_TABLE>_ID naming but NO REFERENCES constraint
    USER_ID        TEXT,
    CREATED_AT     TIMESTAMPTZ
);
```

## Partition Purge Pattern

For append-only tables with high write volume and periodic purge (e.g. `BT.API_REQUEST_PAYLOAD`):

- Use `PARTITION BY RANGE (CREATED_AT)` — partition by quarter.
- New data = INSERT into current partition. No UPDATEs (append-only).
- `IS_CURRENT_IND` lives on the **metadata table** (e.g. `API_REQUEST`), not on the payload table. Payload tables should be updated as little as possible.
- Purge = `DROP TABLE <partition>` — instant, zero VACUUM, full space reclaim.
- PK must include the partition key: `PRIMARY KEY (id_col1, id_col2, CREATED_AT)` (Postgres requires partition key in PK/unique constraints).
- Use **pg_partman** (`CREATE EXTENSION pg_partman`) for automatic quarterly partition creation. Call `partman.create_parent()` with `p_interval := '3 months'` and `p_premake := 4`. Schedule `run_maintenance()` via BGW or cron.

## Liquibase Changeset Patterns

### Inline SQL (indexes, filtered indexes, ad-hoc DDL)

```xml
<changeSet id="2" author="alfcheun">
    <comment>Adding a specific index with a filter</comment>
    <sql>
        CREATE INDEX idx_active_users
        ON users (email)
        WHERE status = 'active';
    </sql>
    <rollback>
        <sql>DROP INDEX idx_active_users;</sql>
    </rollback>
</changeSet>
```

### External SQL file (tables, views, large scripts)

```xml
<changeSet id="3" author="alfcheun">
    <sqlFile
        path="scripts/v1_create_views.sql"
        relativeToChangelogFile="true"
        splitStatements="true"
        stripComments="true"/>
    <rollback>
        <sql>DROP VIEW user_summary;</sql>
    </rollback>
</changeSet>
```

- Use `<sql>` for short, single-purpose statements (indexes, grants, extensions).
- Use `<sqlFile>` for table DDL and multi-statement scripts — keeps changesets concise.
- Always include a `<rollback>` block.
- Use `relativeToChangelogFile="true"` so paths resolve from the changelog location.

## Checklist

Before committing a DDL file:

1. All timestamps are `TIMESTAMPTZ` — no `TEXT`, no `CURRENT_TIMESTAMP`, no `DEFAULT`
2. All IDs are `UUID` or `INTEGER GENERATED ALWAYS AS IDENTITY` — no `AUTOINCREMENT`
3. All flags are `CHAR(1)` with no default — no `BOOLEAN`, no `CHECK` constraint
4. All decimal/money columns are `NUMERIC` — no `REAL`
5. All JSON columns are `JSONB` — no `TEXT`
6. Audit columns (`USER_ID`, `CREATED_AT` or `UPDATED_AT`) present on every table
7. **No foreign key constraints** — no `REFERENCES`, no `FOREIGN KEY`. Relationships documented via column naming only
8. **No CHECK constraints** — no `CHECK`. Value validation at application layer only
9. **No inline payload** on metadata tables — large payloads go in a dedicated (optionally partitioned) table
10. **No DEFAULT values** — no `DEFAULT` on any column. All values supplied by application
11. File is named `<TABLE_NAME>.sql` and placed in the correct schema folder

## Stored Procedure Conventions

### Parameter Naming

- Input parameters: `IN_XXX` (UPPER_CASE, prefixed with `IN_`)
- Output parameters: `OUT_XXX` (UPPER_CASE, prefixed with `OUT_`)
- Local variables: `V_XXX` (UPPER_CASE, prefixed with `V_`)
- Always use explicit `IN` / `OUT` keywords — never rely on implicit direction

### Required OUT Parameters

Every procedure MUST include these two OUT parameters for error reporting:

| Parameter | Type | Purpose |
|-----------|------|---------|
| `OUT_SQLSTATE` | `TEXT` | PostgreSQL 5-char SQLSTATE code (`'00000'` = success) |
| `OUT_SQLERRMC` | `TEXT` | Error message text (custom or system-generated) |

### Error Handling Pattern

All procedures use `LANGUAGE plpgsql` with `EXCEPTION WHEN OTHERS` and `GET STACKED DIAGNOSTICS`:

```sql
CREATE OR REPLACE PROCEDURE <SCHEMA>.<PROC_NAME>(
    IN  IN_COL1       TEXT,
    IN  IN_COL2       INTEGER,
    OUT OUT_SQLSTATE   TEXT,
    OUT OUT_SQLERRMC   TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLERRMC := NULL;

    INSERT INTO <SCHEMA>.<TABLE> (COL1, COL2)
    VALUES (IN_COL1, IN_COL2);

EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            OUT_SQLSTATE = RETURNED_SQLSTATE,
            OUT_SQLERRMC = MESSAGE_TEXT;
END;
$$;
```

### Procedure Logging

All non-trivial procedures should log to `CORE_ADMIN.LOG_PROC_DETAIL` via `CORE_ADMIN.CORE_INS_LOG_PROC`.

### SQL Style

- All SQL keywords in UPPER CASE: `CREATE`, `INSERT INTO`, `VALUES`, `BEGIN`, `END`, `EXCEPTION`
- All identifiers (table, column, param names) in UPPER CASE
- Use `LANGUAGE plpgsql` — never `LANGUAGE SQL` for procedures with error handling
- Use `CREATE OR REPLACE PROCEDURE` — enables `runOnChange="true"` in Liquibase

### DB2 → PostgreSQL Migration Reference

| DB2 Concept | PostgreSQL Equivalent |
|-------------|----------------------|
| `SPECIFIC <name>` | Not supported — remove |
| `MODIFIES SQL DATA` | Not needed — implicit |
| `NOT DETERMINISTIC` | Not needed — implicit for procedures |
| `NULL CALL` | `CALLED ON NULL INPUT` (default) — remove |
| `DOUBLE` | `DOUBLE PRECISION` |
| `P1:BEGIN ... END P1` | `BEGIN ... END` (no labels needed) |
| `DECLARE EXIT HANDLER FOR SQLEXCEPTION` | `EXCEPTION WHEN OTHERS THEN` block |
| `DECLARE V_X TYPE;` | `DECLARE` block before `BEGIN` |
| `SQLCODE` (integer) | `RETURNED_SQLSTATE` (5-char text via `GET STACKED DIAGNOSTICS`) |
| `SQLERRM` / `SQLERRMC` | `MESSAGE_TEXT` (via `GET STACKED DIAGNOSTICS`) |
| `SYSIBM.SYSDUMMY1` | Not needed — use `GET STACKED DIAGNOSTICS` directly |
| `COMMIT` / `ROLLBACK` inside proc | Supported in `PROCEDURE` (not `FUNCTION`) — but default is atomic within caller's transaction |

### File Layout for Procedures

```
db/liquidbase/<schema>/procedures/<PROC_NAME>.sql
```

Procedure files are named `<PROC_NAME>.sql` in UPPER_CASE, placed in the `procedures/` subfolder of the schema directory.
