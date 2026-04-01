# Project Guidelines — Quant Strategies

## Architecture

| Path | Role |
|------|------|
| `scripts/backtest/` | Pipeline: `data.py` → `ta.py` → `strat.py` → `perf.py` → `param_opt.py`, orchestrated by `main.py` |
| `scripts/` | Top-level utilities |
| `backup/deco/` | Decommissioned scripts (kept for reference) |
| `tests/unit/` | Unit tests per module |
| `tests/integration/` | End-to-end pipeline tests |
| `notebooks/` | Exploratory analysis |
| `db/` | SQLite schema and migrations (planned) |

## Code Style

- Python 3.12+, pandas/numpy idioms matching existing modules.
- Imports in `scripts/backtest/` are **relative** to that package (e.g. `from data import Glassnode`).
- Run tests with `python -m pytest tests/ -v` from project root.

## Build and Test

```bash
./setup.sh                        # Create venv, install deps
source env/bin/activate
python -m pytest tests/ -v        # Run all tests
cd scripts/backtest && python main.py  # Run backtest
```

## Conventions

- Keep changes **focused** — extend existing functions/classes rather than duplicating logic.
- **Secrets**: API keys live in `scripts/.env` (gitignored). Never commit credentials.
- `env/` is gitignored — always recreate via `setup.sh` or `requirements.txt`.
- New dependencies go in `requirements.txt`.

## Safety

- Scripts may touch **live trading** or exchange APIs. Treat order placement and production paths as **high risk**; confirm intent before suggesting automated execution or destructive operations.
