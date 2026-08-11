# Database

The project uses **PostgreSQL 17** with Liquibase for schema management. Each schema is deployed independently with its own `databasechangelog` tracking table.

See [System Overview](overview.md) for schema relationships and [Dev vs Prod](dev-vs-prod.md) for connection topology.

## Schemas

| Schema | Purpose |
|--------|---------|
| `CORE_ADMIN` | App users (`APP_USER`), proc audit log (`LOG_PROC_DETAIL`), exchange API credentials (`API_CREDENTIAL`) |
| `REFDATA` | Reference data (`APP`, `INDICATOR`, `SIGNAL_TYPE`, `CONJUNCTION`, `DATA_COLUMN`, `APP_METRIC`, `PROMOTION_METRIC`, …) + `SP_GET_ENUM` procedure for cache loading. `REFDATA.APP` includes **`IS_EXCHANGE_IND`** (`Y` = broker/exchange, `N` = data provider) and seeds for Futu, Bybit, Binance, Yahoo, Glassnode, Nasdaq Data Link. `REFDATA.PROMOTION_METRIC` stores auto-promote rules (HARD gates + SOFT comparison metrics). |
| `BT` | Backtest results (`STRATEGY`, `QUEUE`, `RESULT`, `PROMOTION`, `API_REQUEST`, `API_REQUEST_PAYLOAD`) + insert/get procedures |
| `TRADE` | Live trading: `DEPLOYMENT`, `EXECUTION_EVENT`, `TRANSACTION` + SPs (no `INTENT` — decision #38) |
| `MARKET_DATA` | Normalized price bars for live apply: `PRICE_BAR` (OHLCV rows) — see [Scheduler & Price Bars](../design/scheduler-price-bars.md) |
| `INST` | Instrument / product master (`PRODUCT`, `PRODUCT_XREF`, `PRODUCT_GRP`, `PRODUCT_GRP_MEMBER`) — `REFDATA.TICKER_MAPPING` has been dropped |

## Conventions

!!! danger "No Direct SQL in Application Code"
    **All** database access from Python/FastAPI goes through **`CALL schema.procedure(...)`** — both reads (`SP_GET_*`) and writes (`SP_INS_*`, `SP_UPD_*`). No raw `SELECT`, `INSERT`, `UPDATE`, or `DELETE` in Python code. Exceptions: **`BT.QUEUE`** mutations use **`BT.SP_INS_QUEUE`** only (**`IN_ACTION`** discriminates enqueue / claim / terminal / cancel). Liquibase seed changesets may use direct SQL. `information_schema` catalog queries (e.g. REFDATA table discovery) are permitted.

    - **REFDATA reads** — application code reads REFDATA via the Redis-backed `RedisRefData` reader (`quant/refdata/reader.py`). Postgres is hit only by the publisher (`quant/refdata/publisher.py`) at startup and on `POST /api/v1/refdata/refresh`, which runs `CALL REFDATA.SP_GET_ENUM(table_name, ...)` per table. Never query REFDATA tables directly from application code.
    - If a required procedure does not exist yet, create it first.

### Column Naming

| Pattern | Example | Usage |
|---------|---------|-------|
| `<TABLE>_ID` | `STRATEGY_ID` | Primary key |
| `<TABLE>_VID` | `STRATEGY_VID` | Soft-version ID |
| `<TABLE>_NM` | `STRATEGY_NM` | Name column |
| `USER_ID` | — | Audit: who created |
| `CREATED_AT` | — | Audit: when created (`TIMESTAMPTZ`) |
| `IS_CURRENT_IND` | — | Soft-versioning flag (`CHAR(1)` Y/N) — **deprecated** in `BT.STRATEGY`, replaced by `TRANSACT_FROM_TS` / `TRANSACT_TO_TS` |
| `TRANSACT_FROM_TS` / `TRANSACT_TO_TS` | — | Transaction-time window (`TIMESTAMPTZ`). Active row: `TRANSACT_TO_TS = '9999-12-31'` |
| `IS_BEST_IND` | — | Best-performing version flag (`CHAR(1)` Y/N, no DEFAULT). Used on `BT.STRATEGY`. |

### INTERNAL_CUSIP Convention

`INST.PRODUCT.INTERNAL_CUSIP` is the stable, human-readable product identifier used across the entire pipeline. Format: **`{symbol}.{suffix}`**, always **lowercase**.

| Asset class | Suffix / venue portion | Example | Notes |
|---|---|---|---|
| Crypto spot | `.crypto` | `btcusdt.crypto` | **One product per traded pair** — not per broker. Bybit and Binance share this row; xref supplies `BTCUSDT` (or each venue's ccxt id). Symbol encodes quote currency (`btcusdt`, not `btc-usd`). |
| Crypto derivatives | actual exchange | `btc-perp.binance` | Exchange-specific when margin/settlement differs |
| Listed equity | listing exchange | `aapl.nyse` | Unambiguous listing venue |
| OTC / fixed income | clearing house | `ust10y.dtcc` | Clearing venue is the stable identifier |
| Index | provider | `spx.cboe` | Index publisher is the authority |

#### Multi-broker crypto spot (Bybit + Binance)

Brokers are **not** part of the cusip. Enabling a second ccxt venue does **not** create a second `INST.PRODUCT` row.

```
INST.PRODUCT          INTERNAL_CUSIP = btcusdt.crypto   (one row)
INST.PRODUCT_XREF     app_id=34 (bybit)   → BTCUSDT
INST.PRODUCT_XREF     app_id=35 (binance) → BTCUSDT
INST.PRODUCT_XREF     app_id=1  (yahoo)   → BTC-USD   (research proxy)
INST.PRODUCT_XREF     app_id=2  (glassnode) → BTC
```

`TRADE.DEPLOYMENT` stores `internal_cusip` + `app_id` (which broker). Live apply resolves xref for that pair, fetches bars from that venue, and places orders there. A deployment moved from Bybit to Binance keeps the same cusip — only `app_id` and xref change.

**Anti-patterns**

| Pattern | Why it breaks |
|---|---|
| `btcusdt.bybit` / `btcusdt.binance` | Duplicates one instrument; splits cache, price bars, and strategies |
| `btc-usd.crypto` when trading USDT on exchanges | Cusip says USD; venues quote USDT — silent mismatch at apply |
| `EXCHANGE = 'bybit'` on a `.crypto` row | Broker belongs in xref + deployment, not product identity |

Vendor-specific symbols (exact case, ccxt format) live in `INST.PRODUCT_XREF.VENDOR_SYMBOL` — one current row per `(PRODUCT_ID, APP_ID)` pair.

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

### CORE_ADMIN — exchange API credentials (Phase 1.1)

`CORE_ADMIN.API_CREDENTIAL` stores **per-user exchange API keys** (encrypted at rest). Broker is identified by **`APP_ID`** (`REFDATA.APP`), not a free-text exchange column.

| Column | Notes |
|--------|--------|
| `API_CREDENTIAL_ID` | `INTEGER` — assigned in `SP_INS_API_CREDENTIAL` (`MAX+1`), **not** `GENERATED AS IDENTITY` |
| `API_CREDENTIAL_VID` | Soft-version; bump on key rotation |
| `APP_USER_ID` | Owner |
| `APP_ID` | Broker / venue app (e.g. Bybit row in `REFDATA.APP`) |
| `LABEL` | User-facing account name |
| `API_KEY_CIPHERTEXT` / `API_SECRET_CIPHERTEXT` | Fernet blobs — encrypt in Python before SP |
| `IS_ACTIVE_IND` / `IS_CURRENT_IND` | Revoke / current version |
| `CREATED_AT` | Per version row — **no `UPDATED_AT`** |

PK: `(API_CREDENTIAL_ID, API_CREDENTIAL_VID)`. Multiple rows per `(APP_USER_ID, APP_ID)` allowed (multiple accounts on same broker).

**No `TRADE.CONNECTION` table** — runtime broker sessions are ephemeral. Trade audit = `TRADE.EXECUTION_EVENT` + `TRADE.TRANSACTION`. `TRADE.DEPLOYMENT` (Phase 1.2) references `API_CREDENTIAL_ID` only. **No `TRADE.INTENT`** — current signal lives in the worker for one tick; see decision #38.

### TRADE — live execution (Phase 1.2)

| Table | Role |
|-------|------|
| `DEPLOYMENT` | Apply target: pinned strategy, credential, product, qty (soft-versioned via `DEPLOYMENT_VID` + `TRANSACT_FROM/TO`) |
| `EXECUTION_EVENT` | Append-only submit / error diary; `TRANSACT_AT` = tick time, `CREATED_AT` = audit insert |
| `TRANSACTION` | Append-only broker-confirmed fills |

**Not stored:** current signal / target position between ticks (`TRADE.INTENT` rejected — decision #38).

| Procedure | Purpose |
|-----------|---------|
| `SP_INS_DEPLOYMENT` | Create or version deployment |
| `SP_GET_DEPLOYMENT` | Read current or historical deployment (owner-scoped, REFCURSOR) |
| `SP_GET_DEPLOYMENT_CHECK` | Validation read by deployment_id — no owner filter (caller checks) |
| `SP_INS_EXECUTION_EVENT` | Append execution event |
| `SP_INS_TRANSACTION` | Append fill row |

Validation: Python `TradeRepo` before SP calls. See [Plan to Profit §1.2](../design/plan-to-profit.md#phase-12--trade-schema--apply-api).

| Procedure | Purpose |
|-----------|---------|
| `SP_INS_API_CREDENTIAL` | New account (assign id) or rotate keys (new VID) |
| `SP_GET_API_CREDENTIAL` | List/get for owner; returns ciphertext |
| `SP_GET_CREDENTIAL_CHECK` | Validation read by credential_id — no owner filter (caller checks ownership + active status) |
| `SP_UPD_API_CREDENTIAL_REVOKE` | Soft-version revoke |

See [Plan to Profit §1.1](../design/plan-to-profit.md#phase-11--user-secrets) and decision #36.

**Application code:** `ApiCredentialRepo` extends `DbGateway` (same as `AuthRepo`); routes use `require_user`; Fernet key separate from `JWT_SECRET` — see [Login §6.4](../design/login.md#64-reuse-from-login--jwt-credential-api--phase-11).

**SP OUT parameter order:** All write procedures called via `DbGateway._call_write` must return the status triplet `(OUT_SQLSTATE, OUT_SQLMSG, OUT_SQLERRMC)` **first**, then any business OUT params. Credential SPs were corrected in release `1.1.1-credential-sp-out-order` (applied to prod; archived in `releases/`).

### BT — strategy catalog (Phase 1.6 + 1.7)

`BT.STRATEGY` uses **temporal versioning** (`TRANSACT_FROM_TS` / `TRANSACT_TO_TS`, active = `9999-12-31`) instead of `IS_CURRENT_IND` (dropped). **`IS_BEST_IND`** (`CHAR(1)`, no DEFAULT) marks the best-performing VID per `STRATEGY_ID` — at most one `'Y'` row per strategy. See [Best-VID Promotion](../design/best-vid-promotion.md).

| Procedure | Status | Purpose |
|-----------|--------|---------|
| `SP_GET_STRATEGY` | **live** | **Get-one only:** `IN_STRATEGY_ID` required; optional `IN_STRATEGY_VID`; `IN_IS_BEST_IND='Y'` fetches best VID; else active row (`TRANSACT_TO_TS = 9999-12-31`). |
| `SP_GET_STRATEGY_LIST` | **live (1.12.0+)** | **List catalog** for Trade picker — `IN_USER_ID` required; `IN_IS_BEST_IND='Y'` for best VID only, `NULL` for all VIDs. Joins current shredded metrics from `BT.RESULT` (`IS_CURRENT_IND='Y'`) on `(STRATEGY_ID, STRATEGY_VID)` (release `1.13.0` keys + `1.15.0` versioning). |
| `SP_UPD_PROMOTE_STRATEGY` | **live** | Demote current best + promote target VID. `IN_STRATEGY_VID = NULL` = demote-only. |

Persisted strategies (`BT.STRATEGY`) are created when backtest jobs complete — distinct from REFDATA `SIGNAL_TYPE`. Jobs store owner as `USER_ID = str(app_user_id)` (UUID text).

### REFDATA — promotion metrics

`REFDATA.PROMOTION_METRIC` stores configurable auto-promote rules. Two types:

- **HARD** — threshold gates (e.g. Sharpe GT 0, Max DD LTE 40%). Must all pass to be eligible.
- **SOFT** — comparison metrics evaluated in priority order against the current best VID.

Loaded at runtime via `RedisRefData.get_promotion_metrics()`. See [Best-VID Promotion §2](../design/best-vid-promotion.md#2-promotion-metric-configuration--refdata-driven).

## Deployment

### Automated (production)

The deploy workflow runs Liquibase on EC2 when a push to `main` touches `db/liquidbase/**`, but only for changesets whose `context` includes **`prod-deploy`**:

```bash
APP_ENV=prod USE_SSM=1 LIQUIBASE_CONTEXTS=prod-deploy bash scripts/liquibase-deploy.sh
```

It runs **before** the containers restart, so a release that the incoming app version depends on is in place by the time that version starts serving. The reverse order would leave the old image talking to the new schema.

To read the result, look at the end of the **deploy to EC2** step for a per-schema recap:

```text
── MIGRATION SUMMARY (contexts: prod-deploy) ──
  MASTER (schemas)                     2 applied
  TRADE                               12 applied
  TOTAL                               22 applied
```

The workflow prints only the tail of the remote output, and the image pull and container startup that follow a migration are long enough to push it out of view — so `liquibase-deploy.sh` also writes this block to a file that the workflow re-prints last. A migration that fails aborts the deploy before the containers restart, and the Liquibase error is then the final thing in the log.

Tag a changeset `context="<schema>,prod-deploy"` when it must ship with the app that needs it. Leave the tag off and the changeset stays pending until someone runs a migration by hand — either the manually gated **database** workflow (verify / deploy, with a typed confirmation) or:

```bash
# On EC2 (or locally with tunnel to prod) — no filter, applies everything pending
cd /opt/quant && APP_ENV=prod USE_SSM=1 ./scripts/liquibase-deploy.sh
```

Active changelogs have **no baseline includes** — prod data is not touched until you explicitly add a new `releases/X.Y.Z-*.xml` and `<include>` it.

**RDS CloudFormation** (`aws/cfn/02-database.yml`) deploys only when that template or relevant `aws/params/prod.json` keys change — not on every app push. Use workflow_dispatch `deploy_database=true` only when intentionally changing Aurora infrastructure.

### Manual (local)

```bash
source .env
./scripts/liquibase-deploy.sh

# Dry-run — no DDL applied
./scripts/liquibase-verify.sh --offline   # validate + render prod-deploy SQL, no DB
./scripts/liquibase-verify.sh             # status + update-sql preview (needs DB)
```

### Pre-merge checks

Every pull request runs two independent gates, both of which fail the build:

| Gate | Runs | Catches |
|------|------|---------|
| `liquibase (offline validate)` in **tests** | `liquibase-verify.sh --offline` against `url=offline:postgresql` | Malformed XML, an `<include>` or `<sqlFile>` that does not resolve, duplicate changeset ids, and any changeset whose SQL fails to render under `--context-filter=prod-deploy` |
| `pytest` | `tests/unit/test_liquibase_changelogs.py` | A changeset with no `context` (which would join *every* filtered run, including the automated prod deploy), `prod-deploy` used without its schema context, and a procedure missing `splitStatements="false"` |

The split is not arbitrary. Liquibase validates structure but has no view on convention — its policy engine (`liquibase checks`) is Pro-only — so the conventions this repo depends on are asserted in pytest instead.

An offline run records what it applied in a `databasechangelog.csv`. The script points each run at a throwaway copy; a stale one left beside a changelog would make later runs report nothing pending and quietly pass.

Or run schemas individually:

```bash
source .env
cd db/liquidbase && liquibase --defaults-file=liquibase.properties update   # schemas (MARKET_DATA)
cd db/liquidbase/core_admin && liquibase --defaults-file=liquibase.properties update
cd db/liquidbase/refdata && liquibase --defaults-file=liquibase.properties update
cd db/liquidbase/bt && liquibase --defaults-file=liquibase.properties update
cd db/liquidbase/trade && liquibase --defaults-file=liquibase.properties update
cd db/liquidbase/market_data && liquibase --defaults-file=liquibase.properties update
cd db/liquidbase/inst && liquibase --defaults-file=liquibase.properties update
cd db/liquidbase/core_admin && liquibase --defaults-file=liquibase.properties update   # GRANTS refresh
```

**Developer copy of prod data:** see [Database dump & restore](../guides/database-dump-restore.md) (`./scripts/dbctl.sh`).

### Release-based changelogs

Each schema root (`*-changelog.xml`) includes **forward-only** release files under `releases/`. **Baseline DDL is not included** — prod already has data and `DATABASECHANGELOG` tracks applied history.

Active changelogs are empty manifests — see XML comments in each `db/liquidbase/*/*-changelog.xml`. Archive baselines live under `releases/archive/baseline-1.0.0.xml` (reference only, never included on prod).

**Release lifecycle:** After a forward release is applied to prod, its `<include>` is removed from the active changelog (release SQL files remain under `releases/` for history). Recent examples applied and archived: `core_admin` 1.1.0–1.1.1 (credentials SPs), `refdata` 1.2.0–1.2.1 (`IS_EXCHANGE_IND`, Binance seed).

## Stored Procedures

### Timing a procedure: `clock_timestamp()`, never `CURRENT_TIMESTAMP`

A procedure that logs itself declares `V_LOG_START TIMESTAMPTZ := clock_timestamp();` and passes it to `CORE_INS_LOG_PROC` as the start instant. `CORE_INS_LOG_PROC` closes the interval with `clock_timestamp()` when the caller passes `NULL` for the end.

`CURRENT_TIMESTAMP` (and its aliases `now()` and `transaction_timestamp()`) is the *transaction* start. It does not move for the life of the transaction, so subtracting two readings always yields exactly `0` — which is what every one of the 109,985 `LOG_PROC_DETAIL.DURATION` rows written before 2026-08-11 contained. `statement_timestamp()` does not help either: a `CALL` is a single top-level statement and the whole body runs inside it. Timezone is unrelated — `now() AT TIME ZONE 'UTC'` only reformats the same frozen instant.

`V_START_TS` remains `CURRENT_TIMESTAMP` in the seven procedures that also stamp `TRANSACT_FROM_TS` / `TRANSACT_TO_TS`. Transaction time is correct there: the closed row's end and the new row's start must be the same instant, leaving no gap in the version window. Those procedures declare both variables. `tests/unit/test_proc_log_timing.py` enforces the split.

| Procedure | Schema | Type |
|-----------|--------|------|
| `CORE_INS_LOG_PROC` | `CORE_ADMIN` | Central logging for all SPs — measures with `clock_timestamp()` |
| `SP_GET_ENUM` | `REFDATA` | Generic REFCURSOR select for any REFDATA table |
| `SP_INS_STRATEGY` | `BT` | Resolves `STRATEGY_ID` from `(USER_ID, STRATEGY_NM)`; bumps VID; returns `OUT_STRATEGY_ID` + `OUT_STRATEGY_VID`. Advisory lock per identity. See [strategy-vid-versioning.md](../design/strategy-vid-versioning.md). |
| `SP_INS_QUEUE` | `BT` | **Unified queue state machine**: `IN_ACTION` = **`ENQUEUE`**, **`CLAIM_NEXT`**, **`TERMINAL`**, **`CANCEL`** — all **`BT.QUEUE`** transitions |
| `SP_GET_QUEUE` | `BT` | Flexible queue reader (REFCURSOR); FastAPI jobs list/detail |
| `SP_GET_QUEUE_FOR_TERMINAL` | `BT` | Active rows + strategy metadata (REFCURSOR) |
| `FN_GET_QUEUE_FOR_TERMINAL` | `BT` | **Function** — UI terminal lookup (`RETURNS TABLE`); worker uses `SP_GET_QUEUE_LATEST` |
| `SP_GET_QUEUE_LATEST` | `BT` | **Queue worker**: active row for one **`QUEUE_ID`** + frozen **`CONFIG_JSON`** (`QUEUE` ⋈ **`STRATEGY`** on **`STRATEGY_VID`**) |
| `SP_INS_RESULT` | `BT` | Inserts **`BT.RESULT`** with shredded metrics from `PAYLOAD_JSON` + denormalized `STRATEGY_ID`/`STRATEGY_VID` from `BT.QUEUE`; bumps `RESULT_VID` and flips prior rows' `IS_CURRENT_IND` within the same strategy VID; **`IN_RESULT_ID`** is caller-supplied UUID; OUT row is status triplet only |
| `SP_GET_RESULT` | `BT` | Fetch result row for a `QUEUE_ID` (REFCURSOR); includes `RESULT_VID`, `IS_CURRENT_IND` |
| `SP_INS_API_REQUEST` | `BT` | Soft-versioning insert — combined header + JSONB payload in a single call (writes both `API_REQUEST` and the partitioned `API_REQUEST_PAYLOAD`) |
| `SP_INS_API_CREDENTIAL` | `CORE_ADMIN` | New exchange credential or rotate keys (soft-version); status triplet OUT first |
| `SP_GET_API_CREDENTIAL` | `CORE_ADMIN` | List/get credentials for `APP_USER_ID` (REFCURSOR) |
| `SP_GET_CREDENTIAL_CHECK` | `CORE_ADMIN` | Validation read by `API_CREDENTIAL_ID` — no owner filter; caller checks ownership + active status |
| `SP_UPD_API_CREDENTIAL_REVOKE` | `CORE_ADMIN` | Soft-version revoke; status triplet OUT first |
| `SP_UPD_PROMOTE_STRATEGY` | `BT` | Flip `IS_BEST_IND`: demote current best + promote target VID. `IN_STRATEGY_VID = NULL` = demote-only (no replacement) |
| `SP_INS_PROMOTION` | `BT` | Persist auto-promote decision (outcome, gate results, decisive metric) — one row per completed backtest |
| `SP_GET_STRATEGY` | `BT` | Get-one by id/vid; **list by `IN_USER_ID`** when `IN_STRATEGY_ID` is NULL (Phase 1.6). `IN_IS_BEST_IND = 'Y'` fetches the best VID directly. |
| `SP_INS_DEPLOYMENT` | `TRADE` | Create or version deployment (includes schedule fields) |
| `SP_GET_DEPLOYMENT` | `TRADE` | Read deployment rows (REFCURSOR) |
| `SP_GET_MISSED_DUE_DEPLOYMENTS` | `TRADE` | Apply-now rows for `IN_TM_INTERVAL_ID` (poller); includes `NEXT_SCHEDULED_TS` |
| `SP_GET_NEXT_DUE_DEPLOYMENTS` | `TRADE` | Not-yet-due preview (UI / ops, optional) |
| `SP_INS_DEPLOYMENT_SCHEDULE_STATUS` | `TRADE` | Append schedule version (poller advance after apply) |
| `SP_GET_DEPLOYMENT_CHECK` | `TRADE` | Validation read by `DEPLOYMENT_ID` — no owner filter; caller checks ownership |
| `SP_INS_EXECUTION_EVENT` | `TRADE` | Append event; diary only, no scheduler side effects |
| `SP_INS_TRANSACTION` | `TRADE` | Append fill row |
| `SP_INS_PRICE_BAR` | `MARKET_DATA` | Insert one OHLCV bar (one row per call) |
| `SP_GET_PRICE_BAR` | `MARKET_DATA` | Range read by `(INTERNAL_CUSIP, TM_INTERVAL_ID, start, end)` |
| `SP_GET_PRICE_BAR_COVERAGE` | `MARKET_DATA` | `MIN`/`MAX` timestamps via index `LIMIT 1` probes |

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
│   ├── market_data/              # MARKET_DATA price bars + releases/
│   └── inst/                     # INST + releases/
├── sql/                          # Standalone SQL scripts
└── syncddl/                      # Extracted live DDL (gitignored, for diff)
```
