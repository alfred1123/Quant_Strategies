# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator) and optimized via N-dimensional grid search over parameter space.

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

## What's Inside

| Component | Description |
|-----------|-------------|
| **Backtest Pipeline** | `data.py` → `strat.py` → `perf.py` → `param_opt.py` → `walk_forward.py`, orchestrated by `main.py` (CLI) and `api/services/backtest.py` (web) |
| **FastAPI Backend** | REST + SSE endpoints for optimization, performance, walk-forward, refdata, and instruments — cookie-based auth |
| **React Frontend** | MUI-based SPA with configurable factor cards, live progress bar, interactive charts |
| **PostgreSQL Database** | REFDATA (dropdowns), BT (backtest results), INST (products + xrefs), CORE_ADMIN (users), TRADE (planned) — managed via Liquibase |
| **CLI** | `argparse` interface for scripted single-symbol backtests and grid searches |

## Key Features

- **Multi-factor strategies** — combine indicators via AND, OR, or FILTER conjunction (web UI)
- **SSE-streamed optimization** — real-time progress bar with trial count and best Sharpe
- **Data Column selector** — backtest on Price or Volume per factor
- **Walk-forward test** — in-sample / out-of-sample overfitting detection
- **Paper trading** — connect to Futu OpenD for HK/US equity order execution (Python utility today)
- **REFDATA-driven UI** — all dropdowns sourced from PostgreSQL, zero hardcoded lists
- **Authenticated** — JWT cookie session; user accounts managed by admin

## Quick Links

- [Getting Started](getting-started.md) — setup in 3 commands
- [New User Guide (Website)](guides/new-user-website.md) — run your first backtest in the SPA
- [CLI Backtest](guides/cli-backtest.md) — all flags and examples
- [Pipeline Architecture](architecture/pipeline.md) — data flow diagram
- [API Reference](architecture/api.md) — endpoints and schemas
- [Frontend Code Audit](design/frontend-audit.md) — known frontend issues + remediation directions
- [Decisions Log](decisions.md) — all agreed design decisions
