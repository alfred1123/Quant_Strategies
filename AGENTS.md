# Agent instructions — Quant Strategies

This repository contains Python tooling for **backtesting**, **technical analysis**, **parameter optimization**, and **crypto/equity data** (e.g. Futu, Glassnode). Goals and scope are summarized in `README.md`.

## Layout

| Path | Role |
|------|------|
| `scripts/backtest/` | Pipeline: `data.py` (sources), `ta.py` (indicators), `strat.py`, `perf.py`, `param_opt.py`, `main.py` (orchestration) |
| `scripts/` | Top-level utilities |
| `backup/deco/` | Decommissioned scripts (Bybit live trading — kept for reference) |
| `notebooks/` | Exploratory analysis and requirements discovery |

Run backtest-style code from `scripts/backtest/` (imports are relative to that package, e.g. `from data import ...` in `main.py`).

## Conventions

- Prefer **pandas/numpy** idioms already used in existing modules; match style of neighboring code (naming, plotting libs).
- Keep changes **focused**: extend existing functions/classes rather than duplicating logic.
- **Secrets**: API keys and env live in `scripts/.env` (gitignored). Never commit credentials or paste them into source files.

## Safety

- Scripts may touch **live trading** or exchange APIs. Treat order placement and production paths as **high risk**; confirm intent before suggesting automated execution or destructive operations.

## Environment

- A local `env/` may exist for Jupyter and dependencies; do not assume it is committed. Prefer whatever dependency mechanism the project uses (requirements/pip) when adding packages.
