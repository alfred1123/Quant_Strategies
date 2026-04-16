# Agent instructions — Quant Strategies

This repository contains Python tooling for **backtesting**, **technical analysis**, **parameter optimization**, and **crypto/equity data** (e.g. Futu, Glassnode). Goals and scope are summarized in `README.md`.

## Layout

| Path | Role |
|------|------|
| `src/` | Pipeline: `data.py` (sources), `strat.py` (indicators + strategies + signals), `perf.py`, `param_opt.py`, `main.py` (orchestration) |
| `src/app.py` | **[DECO:STREAMLIT]** Streamlit UI — kept until TypeScript frontend reaches parity (Phase 8, migration M-6). Remove together with `streamlit` pip dep and all hardcoded registries. See `docs/design/ts-migration.md` §7 (M-6) |
| `api/` | FastAPI backend (Phase 7+8) — serves backtest + trade endpoints; imports `src/` modules directly |
| `frontend/` | React/TypeScript SPA (Phase 8) — replaces Streamlit |
| `docs/` | MkDocs Material wiki — architecture, guides, design docs, decisions log. Serve locally with `mkdocs serve`. |
| `backup/deco/` | Decommissioned scripts (Bybit live trading — kept for reference) |

Run backtest-style code from `src/` (imports are relative to that package, e.g. `from data import ...` in `main.py`).

## Conventions

- Prefer **pandas/numpy** idioms already used in existing modules; match style of neighboring code (naming, plotting libs).
- Keep changes **focused**: extend existing functions/classes rather than duplicating logic.
- Do **not** consider backward compatibility for any code change. Completely remove old dependencies, imports, shims, and re-export wrappers — update all call sites directly.

### Database Column Naming

- Version columns: `<TABLE>_VID INTEGER` (e.g. `STRATEGY_VID`)
- Name columns: `<TABLE>_NM TEXT` (e.g. `STRATEGY_NM`)
- Audit: every table gets `USER_ID TEXT`, `CREATED_AT TIMESTAMPTZ`. Add `UPDATED_AT TIMESTAMPTZ` **only** on genuinely mutable tables (e.g. REFDATA lookups). Do **not** add `UPDATED_AT` for `IS_CURRENT_IND` flips — soft-versioning inserts a new row instead of updating.

### Testing: After any change to `src/`, review and update the corresponding unit tests in `tests/unit/` and integration tests in `tests/integration/`. New functions or classes must have unit tests. Run `python -m pytest tests/ -v` and confirm all tests pass before considering the change complete.
- **Secrets**: API keys and env live in `.env` (gitignored) at the project root. Never commit credentials or paste them into source files.
- **README**: After any change that affects usage, setup, CLI options, directory structure, data sources, or dependencies, review and update `README.md` to keep it accurate.
- **Wiki**: After any change that affects architecture, API endpoints, database schema, indicators, strategies, or design decisions, review and update the relevant page in `docs/` (MkDocs wiki). Run `mkdocs serve` to preview.

## Logging

- Every module uses `import logging` and `logger = logging.getLogger(__name__)` at the top.
- Logging format and level are configured **once** in `src/log_config.py` (`setup_logging()`). Do **not** call `logging.basicConfig()` anywhere else.
- **Entry points only** (`main.py`, `app.py`) call `from log_config import setup_logging; setup_logging()`.
- Library modules **never** call `setup_logging` — they only emit via `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`.
- Do **not** use `print()` for status output — use the logger at the appropriate level.

## Safety

- Scripts may touch **live trading** or exchange APIs. Treat order placement and production paths as **high risk**; confirm intent before suggesting automated execution or destructive operations.

### No Direct DML — Use Stored Procedures

**Never** write raw `INSERT`, `UPDATE`, or `DELETE` statements against application tables in Python, API services, or migration seed scripts. All data mutations must go through the schema's stored procedures (e.g. `BT.SP_INS_STRATEGY`, `BT.SP_INS_RESULT`, `BT.SP_INS_API_REQUEST`, `BT.SP_INS_API_REQUEST_PAYLOAD`).

- Python/FastAPI code must call procedures via `CALL <schema>.<procedure>(...)`.
- Seed data (Liquibase `<sql>` changesets) is the only exception — it runs once at deploy time and is acceptable as direct `INSERT` within a changelog file.
- If a required procedure does not exist yet, create it first (following the db-ddl skill conventions) before writing the calling code.
- `SELECT` queries (reads) are fine directly — this rule applies to writes only.

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

The `INDICATOR_DEFAULTS` dict in `src/strat.py` is a **legacy fallback** — once the FastAPI backend is live, it will be replaced by `RefDataCache.get_indicator_defaults()`.

### REFDATA Caching

- Backend loads all REFDATA tables into an in-process `RefDataCache` (Python dict) at startup.
- No TTL — REFDATA changes are rare, admin-only. Refresh via `POST /api/v1/refdata/refresh`.
- Frontend fetches REFDATA via `GET /api/v1/refdata/{table_name}` and caches client-side with TanStack Query (stale-while-revalidate).
- DB connection: `localhost:5433` via AWS SSM port-forward.
- If DB is unreachable at startup, the backend fails fast — REFDATA is required.

### Streamlit Decommission Tag: `[DECO:STREAMLIT]`

`src/app.py` and its unique dependencies (`streamlit` pip package, hardcoded registries) are tagged `[DECO:STREAMLIT]`. They stay in the repo until Phase 8 migration M-6 is verified, then are removed in one go. See `docs/design/ts-migration.md` §7 (M-6) for the full removal checklist.

### No Backward Compatibility for Decommissioned Code

When removing `[DECO:STREAMLIT]` artefacts, do not add shims, re-exports, or deprecation warnings. Delete completely and update all references.

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
