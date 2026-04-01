# Project Guidelines — Quant Strategies

## Architecture

| Path | Role |
|------|------|
| `scripts/bt/` | Pipeline: `data.py` → `ta.py` → `strat.py` → `perf.py` → `param_opt.py`, orchestrated by `main.py` |
| `scripts/` | Top-level utilities |
| `backup/deco/` | Decommissioned scripts (kept for reference) |
| `tests/unit/` | Unit tests per module |
| `tests/integration/` | End-to-end pipeline tests |
| `notebooks/` | Exploratory analysis |
| `db/` | SQLite schema and migrations (planned) |

## Code Style

- Python 3.12+, pandas/numpy idioms matching existing modules.
- Imports in `scripts/bt/` are **relative** to that package (e.g. `from data import Glassnode`).
- Run tests with `python -m pytest tests/ -v` from project root.

## Logging

- Every module uses `import logging` and `logger = logging.getLogger(__name__)` at the top.
- Logging format and level are configured **once** in `scripts/bt/log_config.py`. Do **not** call `logging.basicConfig()` anywhere else.
- **Entry points only** (`main.py`, `app.py`) call `setup_logging()` from `log_config`:
  ```python
  from log_config import setup_logging
  setup_logging()            # INFO level
  setup_logging(debug=True)  # DEBUG level
  ```
- Library modules (`data.py`, `ta.py`, `perf.py`, `strat.py`, `param_opt.py`) **never** call `basicConfig` or `setup_logging` — they only use `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`.
- Do **not** use `print()` for status output — use the logger at the appropriate level.

## Build and Test

```bash
./setup.sh                        # Create venv, install deps
source env/bin/activate
python -m pytest tests/ -v        # Run all tests
cd scripts/bt && python main.py  # Run backtest
```

## Conventions

- Keep changes **focused** — extend existing functions/classes rather than duplicating logic.
- **Secrets**: API keys live in `scripts/.env` (gitignored). Never commit credentials.
- `env/` is gitignored — always recreate via `setup.sh` or `requirements.txt`.
- New dependencies go in `requirements.txt`.
- **README**: After any change that affects usage, setup, CLI options, directory structure, data sources, or dependencies, review and update `README.md` to keep it accurate.

## Safety

- Scripts may touch **live trading** or exchange APIs. Treat order placement and production paths as **high risk**; confirm intent before suggesting automated execution or destructive operations.
