# Agent instructions — Quant Strategies

This repository contains Python tooling for **backtesting**, **technical analysis**, **parameter optimization**, and **crypto/equity data** (e.g. Futu, Glassnode). Goals and scope are summarized in `README.md`.

## Layout

| Path | Role |
|------|------|
| `src/` | Pipeline: `data.py` (sources), `strat.py` (indicators + strategies + signals), `perf.py`, `param_opt.py`, `main.py` (orchestration) |
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

## Logging

- Every module uses `import logging` and `logger = logging.getLogger(__name__)` at the top.
- Logging format and level are configured **once** in `src/log_config.py` (`setup_logging()`). Do **not** call `logging.basicConfig()` anywhere else.
- **Entry points only** (`main.py`, `app.py`) call `from log_config import setup_logging; setup_logging()`.
- Library modules **never** call `setup_logging` — they only emit via `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`.
- Do **not** use `print()` for status output — use the logger at the appropriate level.

## Safety

- Scripts may touch **live trading** or exchange APIs. Treat order placement and production paths as **high risk**; confirm intent before suggesting automated execution or destructive operations.

## Environment

- A local `env/` may exist for Jupyter and dependencies; do not assume it is committed. Prefer whatever dependency mechanism the project uses (requirements/pip) when adding packages.
