# Quant Strategies

Backtesting and trading framework for crypto and equity markets. Strategies are built around technical indicators (SMA, EMA, RSI, Bollinger Z-score, Stochastic Oscillator) and optimized via N-dimensional grid search over parameter space.

**Target:** strategies with Sharpe > 1.5 and strong Calmar ratios.

## What's Inside

| Component | Description |
|-----------|-------------|
| **Backtest Pipeline** | `data.py` → `strat.py` → `perf.py` → `param_opt.py` → `walk_forward.py` |
| **FastAPI Backend** | REST + SSE endpoints for optimization, performance, walk-forward |
| **React Frontend** | MUI-based SPA with configurable factor cards, live progress bar, interactive charts |
| **PostgreSQL Database** | REFDATA (dropdowns), BT (backtest results), TRADE (live trading) — managed via Liquibase |
| **CLI** | Full `argparse` interface for scripted backtests and grid searches |

## Key Features

- **Multi-factor strategies** — combine indicators via AND, OR, or FILTER conjunction
- **SSE-streamed optimization** — real-time progress bar with trial count and best Sharpe
- **Data Column selector** — backtest on Price or Volume per factor
- **Walk-forward test** — in-sample / out-of-sample overfitting detection
- **Paper trading** — connect to Futu OpenD for HK/US equity order execution
- **REFDATA-driven UI** — all dropdowns sourced from PostgreSQL, zero hardcoded lists

## Quick Links

- [Getting Started](getting-started.md) — setup in 3 commands
- [CLI Backtest](guides/cli-backtest.md) — all flags and examples
- [Pipeline Architecture](architecture/pipeline.md) — data flow diagram
- [API Reference](architecture/api.md) — endpoints and schemas
- [Decisions Log](decisions.md) — all agreed design decisions
