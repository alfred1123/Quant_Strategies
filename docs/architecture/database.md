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
    Writes from Python/FastAPI normally go through **`CALL schema.procedure(...)`** (including **`BT.SP_INS_RESULT`** for **`BT.RESULT`**). Exceptions: **`BT.QUEUE`** mutations use **`BT.SP_INS_QUEUE`** only (**`IN_ACTION`** discriminates enqueue / claim / terminal / cancel). Liquibase seed changesets may use **`INSERT`** once per deploy.

    - **REFDATA reads** — application code reads REFDATA via the Redis-backed `RedisRefData` reader (`quant/refdata/reader.py`). Postgres is hit only by the publisher (`quant/refdata/publisher.py`) at startup and on `POST /api/v1/refdata/refresh`, which runs `CALL REFDATA.SP_GET_ENUM(table_name, ...)` per table. Never query REFDATA tables directly from application code.
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

### Automated (production)

**App deploy does not run Liquibase.** GitHub Actions only updates Docker containers on EC2. Database schema changes are applied manually when you add a forward release file and run:

```bash
# On EC2 (or locally with tunnel to prod)
cd /opt/quant && APP_ENV=prod USE_SSM=1 ./scripts/liquibase-deploy.sh
```

Active changelogs have **no baseline includes** — prod data is not touched until you explicitly add a new `releases/X.Y.Z-*.xml` and `<include>` it.

**RDS CloudFormation** (`aws/cfn/02-database.yml`) deploys only when that template or relevant `aws/params/prod.json` keys change — not on every app push. Use workflow_dispatch `deploy_database=true` only when intentionally changing Aurora infrastructure.

### Manual (local)

```bash
source .env
./scripts/liquibase-deploy.sh
```

Or run schemas individually:

```bash
source .env
cd db/liquidbase && liquibase --defaults-file=liquibase.properties update
cd core_admin && liquibase --defaults-file=liquibase.properties update
# ... refdata, bt, trade, inst — then core_admin again for GRANTS refresh
```

### Release-based changelogs

Each schema root (`*-changelog.xml`) includes **forward-only** release files under `releases/`. **Baseline DDL is not included** — prod already has data and `DATABASECHANGELOG` tracks applied history.

Active changelogs are empty manifests — see XML comments in each `db/liquidbase/*/*-changelog.xml`. Archive baselines live under `releases/archive/baseline-1.0.0.xml` (reference only, never included on prod).

## Stored Procedures

| Procedure | Schema | Type |
|-----------|--------|------|
| `CORE_INS_LOG_PROC` | `CORE_ADMIN` | Central logging for all SPs |
| `SP_GET_ENUM` | `REFDATA` | Generic REFCURSOR select for any REFDATA table |
| `SP_INS_STRATEGY` | `BT` | Soft-versioning insert (auto-VID + IS_CURRENT_IND flip) |
| `SP_INS_QUEUE` | `BT` | **Unified queue state machine**: `IN_ACTION` = **`ENQUEUE`**, **`CLAIM_NEXT`**, **`TERMINAL`**, **`CANCEL`** — all **`BT.QUEUE`** transitions |
| `SP_GET_QUEUE` | `BT` | Flexible queue reader (REFCURSOR); coordinator `queryQueue` |
| `SP_GET_QUEUE_FOR_TERMINAL` | `BT` | Active rows + strategy metadata (REFCURSOR) |
| `FN_GET_QUEUE_FOR_TERMINAL` | `BT` | **Function** — coordinator `claimNext` / `queryTerminal` (`RETURNS TABLE`) |
| `SP_GET_QUEUE_LATEST` | `BT` | **Queue worker**: active row for one **`QUEUE_ID`** + frozen **`CONFIG_JSON`** (`QUEUE` ⋈ **`STRATEGY`** on **`STRATEGY_VID`**) |
| `SP_INS_RESULT` | `BT` | Inserts **`BT.RESULT`**; **`IN_RESULT_ID`** is caller-supplied UUID; OUT row is status triplet only (same shape as **`SP_INS_QUEUE`**) |
| `SP_INS_API_REQUEST` | `BT` | Soft-versioning insert — combined header + JSONB payload in a single call (writes both `API_REQUEST` and the partitioned `API_REQUEST_PAYLOAD`) |

## Directory Layout

```
db/
├── liquidbase/                    # Liquibase changelogs
│   ├── quantdb-changelog.xml     # Master manifest (comments only until new release)
│   ├── releases/                 # TEMPLATE.xml + archive/ (baseline reference)
│   ├── liquibase.properties      # Master properties
│   ├── core_admin/               # *-changelog.xml + releases/archive/
│   ├── refdata/                  # REFDATA + releases/
│   ├── bt/                       # BT + releases/
│   ├── trade/                    # TRADE + releases/
│   └── inst/                     # INST + releases/
├── sql/                          # Standalone SQL scripts
└── syncddl/                      # Extracted live DDL (gitignored, for diff)
```
