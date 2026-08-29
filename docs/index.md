# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator) and optimized via N-dimensional grid search over parameter space.

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

## What's Inside

| Component | Description |
|-----------|-------------|
| **Backtest Pipeline** | `quant/data/sources.py` (providers) or `MARKET_DATA.PRICE_BAR` (exchange venues) → `quant/strategy/{indicators,signals}.py` → `performance.py` → `optimizer.py` → `walk_forward.py`, orchestrated by `quant.cli` (CLI) and `quant/strategy/backtest_service.py` (web, via `quant/api/routers/backtest.py`) |
| **FastAPI Backend** | REST + SSE for backtest; trade deployments + credentials; REFDATA/instruments — cookie-based auth |
| **React Frontend** | MUI SPA — backtest config/results + Trade UI (accounts, deployments) |
| **PostgreSQL Database** | REFDATA, BT, INST, CORE_ADMIN (users + credentials), TRADE — Liquibase-managed |
| **CLI** | `argparse` interface for scripted single-symbol backtests and grid searches |

## Key Features

- **Multi-factor strategies** — combine indicators via AND, OR, or FILTER conjunction (web UI)
- **SSE-streamed optimization** — real-time progress bar with trial count and best Sharpe
- **Data Column selector** — backtest on Price or Volume per factor
- **Walk-forward test** — in-sample / out-of-sample overfitting detection
- **Exchange credentials** — save, rotate, and revoke broker API keys (Bybit, Binance, Futu) via Trade Config UI
- **REFDATA-driven UI** — all dropdowns sourced from PostgreSQL, zero hardcoded lists
- **Authenticated** — JWT cookie session; user accounts managed by admin

## Quick Links

- [Getting Started](getting-started.md) — setup, appctl, dbctl, Liquibase, Docker
- [New User Guide (Website)](guides/new-user-website.md) — run your first backtest in the SPA
- [CLI Backtest](guides/cli-backtest.md) — all flags and examples
- [System Overview](architecture/overview.md) — full stack diagram, schemas, phase status
- [Pipeline Architecture](architecture/pipeline.md) — backtest + worker data flow
- [API Reference](architecture/api.md) — endpoints and project structure
- [Frontend Code Audit](design/frontend-audit.md) — known frontend issues + remediation directions
- [Decisions Log](decisions.md) — all agreed design decisions
