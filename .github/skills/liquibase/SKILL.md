---
name: liquibase
description: 'Write, debug, or run Liquibase changelogs and changesets for the QuantDB PostgreSQL database. Covers changelog structure, property files, env var configuration, context tagging, procedure deployment, and common pitfalls.'
---

# Liquibase Skill

## When to Use

- Creating or editing changelog XML files under `db/liquidbase/`
- Adding new changeSets (tables, procedures, seed data)
- Debugging Liquibase execution errors
- Configuring connection properties or environment variables
- Running migrations or rollbacks

## Project Layout

```
db/liquidbase/
├── quantdb-changelog.xml              # Master changelog — schemas + extensions ONLY
├── liquibase.properties               # Master properties (public schema tracking)
├── core_admin/
│   ├── liquibase.properties           # liquibase-schema-name=core_admin
│   ├── core_admin-changelog.xml       # CORE_ADMIN tables + procedures
│   ├── tables/
│   └── procedures/
├── refdata/
│   ├── liquibase.properties           # liquibase-schema-name=refdata
│   ├── refdata-changelog.xml          # REFDATA tables + seed data
│   ├── tables/
│   └── data/
├── bt/
│   ├── liquibase.properties           # liquibase-schema-name=bt
│   ├── bt-changelog.xml               # BT tables + procedures
│   ├── tables/
│   └── procedures/
└── trade/
    ├── liquibase.properties           # liquibase-schema-name=trade
    ├── trade-changelog.xml            # TRADE tables
    └── tables/
```

## Deployment Architecture — Per-Schema Tracking

Each schema has its own `databasechangelog` and `databasechangeloglock` tables, controlled by `liquibase-schema-name` in each schema's `liquibase.properties`. This provides:

- **Independent deployments** — deploy one schema without affecting others
- **Clean rollbacks** — `rollback-count` only sees changeSets in that schema
- **No filename/path conflicts** — no `logicalFilePath` hacks needed
- **Schema-scoped history** — `liquibase history` shows only that schema's changeSets

### DATABASECHANGELOG table locations

| Schema | Tracks |
|--------|--------|
| `public` | Schema creation + extensions (`000-schemas`) |
| `core_admin` | CORE_ADMIN tables + procedures |
| `refdata` | REFDATA tables + seed data |
| `bt` | BT tables + procedures |
| `trade` | TRADE tables |

### Per-schema `liquibase.properties` template

```properties
changelog-file=<schema>-changelog.xml
driver=org.postgresql.Driver
liquibase-schema-name=<schema>

# Connection values supplied via LIQUIBASE_COMMAND_* env vars (set in .env).
# Run: source ../../../.env && liquibase --defaults-file=liquibase.properties update
```

## Connection Configuration

**Do NOT hardcode credentials in `liquibase.properties`.**

Liquibase reads `LIQUIBASE_COMMAND_*` environment variables as overrides. Set these in `.env`:

```bash
export LIQUIBASE_COMMAND_URL="jdbc:postgresql://${QUANTDB_HOST}:${QUANTDB_PORT}/quantdb"
export LIQUIBASE_COMMAND_USERNAME="${QUANTDB_USERNAME}"
export LIQUIBASE_COMMAND_PASSWORD="${QUANTDB_PASSWORD}"
```

The `liquibase.properties` file should only contain non-sensitive settings:

```properties
changelog-file=quantdb-changelog.xml
driver=org.postgresql.Driver
```

**`${}` syntax does NOT work inside `.properties` files** — Liquibase treats them as literal strings. Always use `LIQUIBASE_COMMAND_*` env vars for dynamic values.

## Running Liquibase

```bash
# Always source .env first
source .env

# Phase 0 — schemas + extensions (from db/liquidbase/)
cd db/liquidbase
liquibase --defaults-file=liquibase.properties update

# Per-schema deployment (from each schema directory)
cd core_admin && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../refdata  && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../bt       && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../trade    && source ../../../.env && liquibase --defaults-file=liquibase.properties update

# Schema-specific commands
cd db/liquidbase/bt
source ../../../.env
liquibase --defaults-file=liquibase.properties status           # Pending changeSets
liquibase --defaults-file=liquibase.properties history          # Applied changeSets
liquibase --defaults-file=liquibase.properties rollback-count 1 # Roll back last (bt only)
liquibase --defaults-file=liquibase.properties update-sql       # Dry-run
```

## PostgreSQL JDBC Driver

Liquibase requires the PostgreSQL JDBC driver in its `lib/` directory. If missing:

```bash
sudo curl -L -o /opt/liquibase/lib/postgresql-42.7.5.jar \
  https://jdbc.postgresql.org/download/postgresql-42.7.5.jar
```

## Changelog Patterns

### Master changelog — schemas and extensions ONLY

The master `quantdb-changelog.xml` creates schemas and extensions. It does **NOT** include sub-changelogs — each schema is deployed independently.

```xml
<changeSet id="000-schemas" author="alfcheun" context="schema" runOnChange="false">
    <sql>
        CREATE SCHEMA IF NOT EXISTS CORE_ADMIN;
        CREATE SCHEMA IF NOT EXISTS BT;
    </sql>
</changeSet>
```

**Do NOT use `<include>`** in the master changelog. Sub-changelogs are deployed separately via per-schema `liquibase.properties`.

### Table changeSets

```xml
<changeSet id="200-bt-strategy" author="alfcheun" context="bt" runOnChange="false">
    <sqlFile path="tables/STRATEGY.sql" relativeToChangelogFile="true"
             splitStatements="true" stripComments="true"/>
    <rollback><sql>DROP TABLE IF EXISTS BT.STRATEGY;</sql></rollback>
</changeSet>
```

- `splitStatements="true"` — for DDL files with multiple statements
- `runOnChange="false"` — tables are immutable once created

### Procedure changeSets

```xml
<changeSet id="210-bt-proc-insert-strategy" author="alfcheun" context="proc" runOnChange="true">
    <sqlFile path="procedures/INSERT_STRATEGY.sql" relativeToChangelogFile="true"
             splitStatements="false" stripComments="true"/>
    <rollback><sql>DROP PROCEDURE IF EXISTS BT.INSERT_STRATEGY;</sql></rollback>
</changeSet>
```

- `splitStatements="false"` — **required** for `$$` dollar-quoted procedure bodies
- `runOnChange="true"` — procedures use `CREATE OR REPLACE` and should re-run when modified

### Seed data changeSets

```xml
<changeSet id="150-refdata-seed-asset-type" author="alfcheun" context="seed" runOnChange="false">
    <sqlFile path="data/ASSET_TYPE.sql" relativeToChangelogFile="true"
             splitStatements="true" stripComments="true"/>
    <rollback><sql>DELETE FROM REFDATA.ASSET_TYPE;</sql></rollback>
</changeSet>
```

## Context Tags

| Context | Used for |
|---------|----------|
| `schema` | Schema / extension creation |
| `refdata` | REFDATA table DDL |
| `bt` | BT table DDL |
| `trade` | TRADE table DDL |
| `proc` | Stored procedures |
| `seed` | Reference data inserts |

Run only specific contexts: `liquibase update --contexts=bt,proc`

## ChangeSet ID Numbering

| Range | Schema / Type |
|-------|---------------|
| 000–009 | Schemas & extensions (master) |
| 010–029 | CORE_ADMIN tables |
| 020–049 | CORE_ADMIN procedures |
| 100–149 | REFDATA tables |
| 150–199 | REFDATA seed data |
| 200–209 | BT tables |
| 210–249 | BT procedures |
| 300–309 | TRADE tables |
| 310–349 | TRADE procedures |

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| `Cannot find database driver` | Missing JDBC JAR | Copy `postgresql-*.jar` to Liquibase `lib/` |
| `Unable to parse URL ${...}` | `${}` in `.properties` file | Use `LIQUIBASE_COMMAND_*` env vars instead |
| `schema "partman" does not exist` | `pg_partman` functions called with wrong schema qualifier | Use `create_parent(...)` without schema prefix (defaults to `public`) |
| `rollback-count` rolls back wrong changeSet | Failed changeSets are NOT recorded | Manually `DROP` partially-created objects, then re-run `update` |
| Procedures fail with syntax error | `splitStatements="true"` splits on `$$` | Set `splitStatements="false"` for procedure files |
| ChangeSets not detected after splitting into sub-changelogs via `<include>` | Filename in DATABASECHANGELOG doesn't match sub-changelog path | Use per-schema deployment with `liquibase-schema-name` instead of `<include>`. Never use `logicalFilePath` hacks |
| `rollback-count N` returns "0 changesets rolled back" | Filename mismatch between DATABASECHANGELOG records and current changelog path | Drop objects manually, truncate/drop DATABASECHANGELOG, redeploy |

## Rollback Notes

- `rollback-count N` rolls back the last N **successfully applied** changeSets
- **Failed changeSets are not recorded** in `DATABASECHANGELOG` — Liquibase doesn't know about them
- PostgreSQL DDL auto-commits, so a failed changeSet may leave partial objects (e.g., table created but `create_parent()` failed)
- Clean up manually with `DROP TABLE/PROCEDURE IF EXISTS`, then re-run `update`

## Checklist

Before adding a new changeSet:

1. Unique ID following the numbering scheme above
2. Correct `context` tag (`bt`, `proc`, `seed`, etc.)
3. `runOnChange` set appropriately (`false` for DDL, `true` for procedures)
4. `splitStatements` set correctly (`true` for DDL, `false` for procedures with `$$`)
5. `relativeToChangelogFile="true"` on all `<sqlFile>` and `<include>` elements
6. `<rollback>` block included
7. SQL file placed in the correct folder (`tables/`, `procedures/`, `data/`)
