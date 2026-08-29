# Agent instructions — Quant Strategies

This repository contains Python tooling for **backtesting**, **technical analysis**, **parameter optimization**, and **crypto/equity data** (e.g. Futu, Glassnode). Goals and scope are summarized in `README.md`.

## Layout

| Path | Role |
|------|------|
| `quant/` | Backtesting pipeline + FastAPI backend — `shared/` (config, logging, db), `schemas/`, `data/`, `refdata/`, `strategy/`, `queue/`, `trade/`, `cli.py`, and `api/` (HTTP routers) |
| `frontend/` | React/TypeScript SPA (replaced Streamlit) |
| `docs/` | MkDocs Material wiki — architecture, guides, design docs, decisions log. Serve locally with `mkdocs serve`. |

Run backtest-style code via `python -m quant.cli` or import from the `quant` package (e.g. `from quant.data.sources import ...`).

## Conventions

- Prefer **pandas/numpy** idioms already used in existing modules; match style of neighboring code (naming, plotting libs).
- Keep changes **focused**: extend existing functions/classes rather than duplicating logic.
- Do **not** consider backward compatibility for any code change. Completely remove old dependencies, imports, shims, and re-export wrappers — update all call sites directly.

### Code Quality — Avoid These Mistakes

Recurring pitfalls to self-check before finishing a change:

- **Don't add layers just to cut lines.** A new helper that only wraps an existing one (e.g. a SQL-string builder on top of `_call_get`/`_call_write`) adds indirection without value. Only abstract when it removes real duplication or clarifies intent. Reducing line count is not a goal.
- **Deduplicate via composition, not copy-paste.** If two repos call the same stored procedure, the SP wrapper lives in ONE owning repo; others inject and call it. Never paste the same `CALL ...` string into multiple classes. (e.g. `bt.sp_get_strategy` lives only on `BtQueueRepo`; `PromotionRepo`/`TradeRepo` take a `BtQueueRepo`.)
- **Name things by what they do or mean, not by category label.** Echoing a config enum value (`_check_hard`, `_compare_soft`) says nothing. Prefer names that carry domain meaning: HARD = requirements that **must pass**, SOFT = ranking **by priority**.
- **Separate layers; don't mix them in one function.** Keep higher-level policy (HARD/SOFT semantics) distinct from lower-level mechanics (threshold check, value compare). Lower helpers stay policy-agnostic; higher functions compose them, then a single entry point merges the result.
- **Put logic where it belongs.** Domain logic (e.g. promotion) goes in its own module/repo, not dumped into an orchestrator like the worker. Analyse ownership before placing code.
- **After a rename, grep for stale references.** A dispatch map once pointed at a function name that no longer existed after a rename — a latent bug. Search all call sites and run the suite after any rename.

### Timing Inside Stored Procedures

Measure elapsed time with **`clock_timestamp()`**, never `CURRENT_TIMESTAMP`. The latter is the transaction start and does not advance, so a duration computed from it is always exactly `0` — the bug that left all 109,985 `LOG_PROC_DETAIL.DURATION` rows at zero. `statement_timestamp()` is equally frozen inside a `CALL`. A procedure that logs declares `V_LOG_START TIMESTAMPTZ := clock_timestamp();` and passes it to `CORE_INS_LOG_PROC`.

Keep `V_START_TS TIMESTAMPTZ := CURRENT_TIMESTAMP;` for `TRANSACT_FROM_TS` / `TRANSACT_TO_TS`: every row a transaction versions must share one instant so the window has no gap. Procedures doing both declare both variables.

### Database Column Naming

- Version columns: `<TABLE>_VID INTEGER` (e.g. `STRATEGY_VID`)
- Name columns: `<TABLE>_NM TEXT` (e.g. `STRATEGY_NM`)
- Audit: every table gets `USER_ID TEXT`, `CREATED_AT TIMESTAMPTZ`. Add `UPDATED_AT TIMESTAMPTZ` **only** on genuinely mutable tables (e.g. REFDATA lookups). Do **not** add `UPDATED_AT` for `IS_CURRENT_IND` flips — soft-versioning inserts a new row instead of updating.

### Testing: After any change to `quant/`, review and update the corresponding unit tests in `tests/unit/` and integration tests in `tests/integration/`. New functions or classes must have unit tests. Run `python -m pytest tests/ -v` and confirm all tests pass before considering the change complete.
- **Secrets**: API keys and env live in `.env` (gitignored) at the project root. Never commit credentials or paste them into source files.
- **README**: After any change that affects usage, setup, CLI options, directory structure, data sources, or dependencies, review and update `README.md` to keep it accurate.
- **Wiki**: After any change that affects architecture, API endpoints, database schema, indicators, strategies, or design decisions, review and update the relevant page in `docs/` (MkDocs wiki). Run `mkdocs serve` to preview. `mkdocs build --strict` must stay at zero warnings — the docs workflow fails the publish on any broken link or anchor (see `.cursor/rules/docs-first.mdc` for the link-hygiene rules).

## Logging

- Every module uses `import logging` and `logger = logging.getLogger(__name__)` at the top.
- Logging format and level are configured **once** in `quant/shared/logging.py` (`setup_logging()`). Do **not** call `logging.basicConfig()` anywhere else.
- **Entry points only** (`quant/cli.py`, `quant/shared/config.py` via `load_config()`) call `setup_logging()`.
- Library modules **never** call `setup_logging` — they only emit via `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`.
- Do **not** use `print()` for status output — use the logger at the appropriate level.

## Safety

- Scripts may touch **live trading** or exchange APIs. Treat order placement and production paths as **high risk**; confirm intent before suggesting automated execution or destructive operations.

### Never Default a Changeset to `prod-deploy`

A push to `main` queues the `migrate` job, which runs Liquibase against production Aurora with `--context-filter=prod-deploy` before any container restarts. That job lives in the `production-db` environment behind a required reviewer, so it waits for approval — but `context` still decides whether a changeset is in the batch:

| `context=` | Push to `main` | Manual `database.yml` |
|---|---|---|
| `"bt"` (schema only) | skipped — **write this** | applied |
| `"bt,prod-deploy"` | queued for `migrate`, applied on approval | applied |
| omitted | **queued too** — no context matches *every* filter | applied |

Write the schema context alone, then tell the user the release is staged and ask before adding `prod-deploy`. Never omit `context` to hold something back — that does the opposite. A staged changeset is not stranded: the **database** workflow with `action=deploy` (type `deploy` to confirm) applies everything pending, context ignored. The reviewer gate is a backstop, not a substitute for asking — it shows a job name, not a diff.

**Editing a procedure body is itself a production migration.** 48 of the 49 files under `*/procedures/` and `*/functions/` are already covered by an active `runOnChange` changeset tagged `prod-deploy` — deliberate, so an edit redeploys instead of going quiet. A one-line change to a procedure therefore queues a production migration on the next push, with no new changeset involved. Flag it before editing.

When proposing a release, state the blast radius — which schemas, how many changesets, and whether any replace a procedure body. Sweeping "re-apply every procedure" releases are the dangerous shape; that is how the 2026-08-16 deploy died 15 changesets into `BT`.

### No Direct DML — Use Stored Procedures

**Never** write raw `INSERT`, `UPDATE`, or `DELETE` statements against application tables in Python, API services, or migration seed scripts, **except**:

- **`BT.RESULT`** (queued backtest completion payloads): use **`CALL BT.SP_INS_RESULT(...)`** with a **client-generated** **`RESULT_ID`** (UUID) — no raw **`INSERT`** into **`BT.RESULT`** from Python/API. Procedure OUT row matches **`BT.SP_INS_QUEUE`**: status triplet only.
- **`BT.QUEUE`** row transitions — use **`CALL BT.SP_INS_QUEUE(...)` only** with `IN_ACTION` ∈ `ENQUEUE` | `CLAIM_NEXT` | `TERMINAL` | `CANCEL` — no standalone `BT.SP_CLAIM_*` / `SP_CANCEL_*`.

All other mutations use schema stored procedures (e.g. `BT.SP_INS_STRATEGY`, `BT.SP_INS_API_REQUEST`, `BT.SP_INS_API_REQUEST_PAYLOAD`).

- Python/FastAPI code normally calls procedures via `CALL <schema>.<procedure>(...)`.
- Seed data (Liquibase `<sql>` changesets) is the only broad exception — direct `INSERT` within a changelog at deploy time.
- If a required procedure does not exist yet, create it first (following the db-ddl skill conventions) before writing the calling code.
- **`SELECT` queries (reads)** must also go through stored procedures (`SP_GET_*`) or functions — no direct `SELECT` in Python application code. The only exception is `information_schema` catalog queries (e.g. REFDATA table discovery).

## Environment

- A local `env/` may exist for Jupyter and dependencies; do not assume it is committed. Prefer whatever dependency mechanism the project uses (requirements/pip) when adding packages.

## Decisions

### REFDATA as Single Source of Truth for UI Dropdowns

All UI dropdown, radio, and selectbox values must come from `REFDATA` tables in PostgreSQL (`localhost:5433`). Agents must **never** hardcode indicator lists, strategy names, asset types, conjunctions, or grid search defaults in UI or API code.

| Dropdown | REFDATA Table | Label Column | Value Column |
|----------|---------------|--------------|--------------|
| Indicator | `REFDATA.INDICATOR` | `DISPLAY_NAME` | `METHOD_NAME` |
| Strategy | `REFDATA.SIGNAL_TYPE` | `DISPLAY_NAME` | `FUNC_NAME` |
| Asset type | `REFDATA.ASSET_TYPE` | `DISPLAY_NAME` | `TRADING_PERIOD` |
| Data column | `REFDATA.DATA_COLUMN` | `DISPLAY_NAME` | `COLUMN_NAME` |
| Conjunction | `REFDATA.CONJUNCTION` | `DISPLAY_NAME` | `NAME` |
| Grid defaults | `REFDATA.INDICATOR` | — | `WIN_MIN`, `WIN_MAX`, `WIN_STEP`, `SIG_MIN`, `SIG_MAX`, `SIG_STEP` (same table) |
| Promotion state | `REFDATA.PROMOTION_STATE` | `DISPLAY_NAME` | `NAME` |
| Promotion rules (gates + soft metrics) | `REFDATA.PROMOTION_METRIC` | `DISPLAY_NAME` | `NAME` (also `METRIC_KEY`, `REQUIREMENT_TYPE`, `PRIORITY`, `THRESHOLD`) |

The `INDICATOR_DEFAULTS` dict in `quant/strategy/signals.py` is a **legacy fallback** — grid defaults should come from `REFDATA.INDICATOR` via `RedisRefData.get_indicator_defaults()`.

### REFDATA Caching

- **`RefDataPublisher`** (`quant/refdata/publisher.py`) loads REFDATA from Postgres via `REFDATA.SP_GET_ENUM` and writes JSON snapshots to Redis (`refdata:<table>` keys). Invoked at FastAPI startup and on `POST /api/v1/refdata/refresh`.
- **`RedisRefData`** (`quant/refdata/reader.py`) is the read-only accessor for API handlers and the worker. Checks `refdata:version` on every `get()` and rebuilds its local snapshot when bumped.
- No TTL — REFDATA changes are rare, admin-only. Refresh via `POST /api/v1/refdata/refresh`.
- Frontend fetches REFDATA via `GET /api/v1/refdata/{table_name}` and caches client-side with TanStack Query (stale-while-revalidate).
- DB connection: `localhost:5433` via AWS SSM port-forward.
- If DB is unreachable at startup, the backend fails fast — REFDATA is required.

### Checking Schema Discrepancies (DB vs Source DDL)

Before proposing DDL changes, verify the live DB state matches the source files. Use the `extractddl` skill:

```bash
# 1. Extract live DDL into db/syncddl/ (mirrors db/liquidbase/ layout)
source .env
bash .github/skills/extractddl/extract_ddl.sh

# 2. Diff a specific table against its source DDL
diff db/syncddl/refdata/tables/APP.sql db/liquidbase/refdata/tables/APP.sql

# 3. Diff all tables in a schema at once
for f in db/liquidbase/refdata/tables/*.sql; do
  name=$(basename "$f")
  live="db/syncddl/refdata/tables/${name}"
  [[ -f "$live" ]] && diff "$live" "$f" && echo "OK: $name" || echo "DIFF: $name"
done
```

`db/syncddl/` is regenerated on demand — never commit it. It is gitignored. The canonical source of truth is `db/liquidbase/`.

Remaining known formatting differences (cosmetic only, not schema drift):
- Source uses **inline** `PRIMARY KEY` / `UNIQUE` on the column; extracted output uses **table-level** constraint syntax — this is a Postgres catalog normalization, not a real discrepancy.
