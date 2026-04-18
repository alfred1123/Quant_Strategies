# Database

The project uses **PostgreSQL 17** with Liquibase for schema management. Each schema is deployed independently with its own `databasechangelog` tracking table.

## Schemas

| Schema | Purpose |
|--------|---------|
| `CORE_ADMIN` | Logging infrastructure (`LOG_PROC_DETAIL` table, `CORE_INS_LOG_PROC` procedure) |
| `REFDATA` | Reference data (`APP`, `INDICATOR`, `SIGNAL_TYPE`, `CONJUNCTION`, `DATA_COLUMN`, `APP_METRIC`, etc.) + `SP_GET_ENUM` procedure for cache loading |
| `BT` | Backtest results (`STRATEGY`, `RESULT`, `API_REQUEST`, `API_REQUEST_PAYLOAD`) + insert procedures |
| `TRADE` | Live trading tables (`DEPLOYMENT`, `LOG`, `TRANSACTION`) — procedures deferred |
| `INST` | Instrument / product master (`PRODUCT`, `PRODUCT_XREF`, `PRODUCT_GRP`, `PRODUCT_GRP_MEMBER`) — `REFDATA.TICKER_MAPPING` has been dropped |

## Conventions

!!! danger "No Direct DML"
    All writes from Python/FastAPI must call stored procedures via `CALL schema.procedure(...)`. Raw `INSERT`, `UPDATE`, or `DELETE` statements in application code are **forbidden**. Liquibase seed changesets are the only exception. `SELECT` queries are unrestricted.

- **REFDATA reads** — `RefDataCache` loads all REFDATA tables at startup via `CALL REFDATA.SP_GET_ENUM(table_name, ...)`. Never query REFDATA tables directly from application code.
- If a required write procedure does not exist yet, create it first.

### Column Naming

| Pattern | Example | Usage |
|---------|---------|-------|
| `<TABLE>_ID` | `STRATEGY_ID` | Primary key |
| `<TABLE>_VID` | `STRATEGY_VID` | Soft-version ID |
| `<TABLE>_NM` | `STRATEGY_NM` | Name column |
| `USER_ID` | — | Audit: who created |
| `CREATED_AT` | — | Audit: when created (`TIMESTAMPTZ`) |
| `IS_CURRENT_IND` | — | Soft-versioning flag (`CHAR(1)` Y/N) |

### INTERNAL_CUSIP Convention

`INST.PRODUCT.INTERNAL_CUSIP` is the stable, human-readable product identifier used across the entire pipeline. Format: **`symbol.exchange`**, always **lowercase**.

| Asset Class | Exchange Portion | Example | Notes |
|---|---|---|---|
| Crypto spot | `crypto` | `btc-usd.crypto` | Venue-agnostic — same asset across exchanges |
| Crypto derivatives | Actual exchange | `btc-perp.binance` | Exchange-specific (different margin/settlement) |
| Listed equity | Listing exchange | `aapl.nyse` | Unambiguous listing venue |
| OTC / fixed income | Clearing house | `ust10y.dtcc` | Clearing venue is the stable identifier |
| Index | Provider | `spx.cboe` | Index publisher is the authority |

Vendor-specific symbols (exact case, format) live in `INST.PRODUCT_XREF.VENDOR_SYMBOL` — one row per `(PRODUCT_ID, APP_ID)` pair.

Current operating model:

- `PRODUCT_XREF` is the authoritative vendor-symbol mapping table.
- The target design is semi-automatic vendor import with approval before insert.
- Until the approval workflow is built, admin/bootstrap population may be done directly in the database.

### INST Versioning

| Table | Versioned? | Rationale |
|---|---|---|
| `PRODUCT` | **Yes** — `PRODUCT_VID` + `IS_CURRENT_IND` | Product attributes (CCY, description, asset type) can change |
| `PRODUCT_XREF` | **Yes** — `PRODUCT_XREF_VID` + `TRANSACT_FROM_TS` / `TRANSACT_TO_TS` | Vendor symbols can change; current row is the open-ended transaction-time record |
| `PRODUCT_GRP` | **No** — uses `UPDATED_AT` | Hierarchy versioning is impractical; rare admin-only edits |
| `PRODUCT_GRP_MEMBER` | **No** — add/remove only | Junction table; `CREATED_AT` audit is sufficient |

## Deployment

```bash
# Source credentials
source .env

# Phase 0: create schemas + extensions
cd db/liquidbase && liquibase --defaults-file=liquibase.properties update

# Per-schema deployment (each has its own liquibase.properties)
cd core_admin && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../refdata  && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../bt       && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../trade    && source ../../../.env && liquibase --defaults-file=liquibase.properties update
cd ../inst     && source ../../../.env && liquibase --defaults-file=liquibase.properties update
```

## Stored Procedures

| Procedure | Schema | Type |
|-----------|--------|------|
| `CORE_INS_LOG_PROC` | `CORE_ADMIN` | Central logging for all SPs |
| `SP_GET_ENUM` | `REFDATA` | Generic REFCURSOR select for any REFDATA table |
| `SP_INS_STRATEGY` | `BT` | Soft-versioning insert (auto-VID + IS_CURRENT_IND flip) |
| `SP_INS_RESULT` | `BT` | Append-only insert (references STRATEGY_VID) |
| `SP_INS_API_REQUEST` | `BT` | Soft-versioning insert |
| `SP_INS_API_REQUEST_PAYLOAD` | `BT` | Append-only into yearly-partitioned table |

## Directory Layout

```
db/
├── liquidbase/                    # Liquibase changelogs
│   ├── quantdb-changelog.xml     # Master — schema & extension creation
│   ├── liquibase.properties      # Master properties
│   ├── core_admin/               # CORE_ADMIN tables + procedures
│   ├── refdata/                  # REFDATA tables + seed data
│   ├── bt/                       # BT tables + procedures
│   ├── trade/                    # TRADE tables
│   └── inst/                     # INST tables (product master)
├── sql/                          # Standalone SQL scripts
└── syncddl/                      # Extracted live DDL (gitignored, for diff)
```
