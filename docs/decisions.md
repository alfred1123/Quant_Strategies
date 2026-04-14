# Decisions Log

All agreed design decisions in one place.

| # | Topic | Decision | Ref |
|---|-------|----------|-----|
| 1 | **Config split** | `StrategyConfig` (backtest identity) + `DeploymentConfig` (trading target), linked by `strategy_id` FK. Backtest results stored with strategy for review. | design doc §1 |
| 2 | **Conjunction syntax** | Flat `"AND"` / `"OR"` / `"FILTER"` enum on `StrategyConfig.conjunction`. No string expression parser. Max 2 substrategies initially. | strat.py |
| 3 | **Substrategy structure** | Ordered tuple of frozen `SubStrategy` dataclasses with sequential `id`. | strat.py |
| 4 | **Optimization config** | Separate `OptimizationConfig`, not embedded in substrategy. Runtime args to `optimize()`. | Phase 4 |
| 5 | **Strategy naming** | Optional `name` field. Auto-generated as `{ticker}_strategy_{id_prefix}` if empty. | strat.py |
| 6 | **Multi-factor positions** | Clean `combine_positions()` function in `strat.py`. AND/OR use percentile-rank strength tiebreak. FILTER uses factor 1 as gate, factor 2 for direction. | Phase 3 |
| 7 | **Grid search engine** | Cartesian product as baseline. Bayesian opt via `optuna` as opt-in alternative. Warn on >10k combos. | Phase 4 |
| 8 | **Visualization** | 1-factor: 2D heatmap. 2-factor: slice heatmaps. 3+: parallel coordinates (Plotly). | Phase 5 |
| 9 | **JSON API / DB** | Full Trade API design doc. Shared DB for backtest + trade. JSON schema for strategy + deployment + backtest results. | design doc |
| 10 | **TypeScript UI** | FastAPI backend (shared with Trade API) + React/TS frontend. Replaces Streamlit. | Phase 8 |
| 11 | **UUID version** | UUID v7 (time-ordered) via `uuid_extensions` package. Switch to stdlib `uuid.uuid7()` when Python 3.14 stable (Oct 2026). | strat.py |
| 12 | **DB naming convention** | `SCHEMA.TABLE` format. Schemas: `CORE_ADMIN.`, `BT.`, `TRADE.`, `REFDATA.`. Columns UPPER_CASE. PKs: `<TABLE>_ID`. Audit: `USER_ID`, `CREATED_AT`/`UPDATED_AT`. Flags: `CHAR(1)`, no default, no CHECK. Soft versioning: `IS_CURRENT_IND`. DB name: `quantdb`. No CHECK constraints — validation at app layer. Procedure params: `IN_XXX`/`OUT_XXX`. | data-sql instructions |
| 13 | **DB tables** | `BT.STRATEGY`, `BT.RESULT`, `TRADE.DEPLOYMENT`, `TRADE.LOG`, `REFDATA.TICKER_MAPPING`. | design doc §7 |
| 14 | **Ticker mapping** | `REFDATA.TICKER_MAPPING` maps data-source symbols to broker-specific symbols (e.g. `"US.AAPL"` for Futu). | design doc §7 |
| 15 | **Broker adapter pattern** | `TradeAdapter` abstract interface. `FutuAdapter` wraps `FutuTrader`. `DeploymentConfig.broker` enum selects adapter. | design doc §5 |
| 16 | **AWS infrastructure** | EC2 t4g.small (Graviton ARM, ~$7/mo). RDS PostgreSQL Serverless v2 (~$5-15/mo). | design doc §11 |
| 17 | **Local dev DB** | SQLite or Docker Postgres locally. Switch via `DB_URL` env var. | design doc §11 |
| 18 | **Risk checks** | Kill switch, paper-first default, max position, stop loss, cash check, signal validation, duplicate guard. | design doc §4 |
| 19 | **No direct DML** | All writes via stored procedures (`CALL schema.procedure(...)`). Liquibase seed changesets are the only exception. | AGENTS.md |
