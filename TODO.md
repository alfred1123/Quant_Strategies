# TODO

## Phase 1 — COMPLETED: Merge ta.py + signal.py → strat.py

**Done.** `strat.py` now contains `TechnicalAnalysis`, `Strategy`, and `StrategyConfig`.
- `ta.py` and `signal.py` reduced to backward-compat re-export shims.
- `perf.py` broken `Strategy` class removed; fixed `enrich_performance()` bugs (`self.` prefix, called in `__init__`).
- All imports updated across `main.py`, `app.py`, `walk_forward.py`, `test_ta.py`.
- 204 tests pass.

---

## User Plan vs Copilot Plan — Conflict Table

| # | Topic | User Plan | Copilot Plan | Conflict | Decision |
|---|-------|-----------|--------------|----------|----------|
| 1 | **StrategyConfig fields** | Fat config with deployment metadata | Lean 3-field frozen dataclass | Mixing concerns | **AGREED**: Split `StrategyConfig` (backtest) + `DeploymentConfig` (trading), mapped by `strategy_id` FK. Backtest results stored with strategy for review. See `docs/design-trade-api.md`. |
| 2 | **Relation syntax** | `"(1 AND 2) OR 3"` string parser | Flat AND/OR enum | Parser complexity | **AGREED**: Start with flat AND/OR for 2 substrategies. Most feasible scope for now. |
| 3 | **Substrategy structure** | Numeric-keyed dict | Ordered tuple of dataclasses | Serialization | **AGREED**: Ordered tuple of `SubStrategy` dataclasses with `id` field. Max 2 substrategies initially. |
| 4 | **param_opt_config** | Embedded in substrategy | Runtime args to `optimize()` | Coupling | **AGREED**: Separate `OptimizationConfig` linked via DB relation. |
| 5 | **Strategy naming** | Auto-generated names | No naming | DB needs names | **AGREED**: Optional `name` field, auto-generated from indicator+strategy. |
| 6 | **Multi-factor perf** | AND/OR wrapper functions | Tuple overloading in `__init__` | API design | **AGREED**: Clean `combine_positions()` function, no tuple overloading. Data array mismatch not a concern — same time interval source assumed. |
| 7 | **Grid search** | Scikit-learn | Cartesian product | Efficiency | **AGREED**: Cartesian product as baseline (backtest speed acceptable, not used in trading). Bayesian opt (optuna) as opt-in alternative. User must be aware which optimizer is active — large step sizes in Bayesian can miss good params on random-walk data. |
| 8 | **Visualization** | N-dim different viz | 2D heatmap with dropdown | Underspecified | **AGREED**: 1-factor heatmap, 2-factor slice heatmaps, 3+ parallel coordinates. |
| 9 | **JSON API / DB** | Strategy JSON → trade API | CLI `--factors` flag | Scope gap | **AGREED**: Full Trade API design doc created — see `docs/design-trade-api.md`. JSON schema defined. DB schema designed (strategies, substrategies, backtest_results, deployments, trade_log). |
| 10 | **TypeScript UI** | Replace Streamlit with TS | Not addressed | Effort vs growth | **AGREED**: Do it now. FastAPI backend (reuses Trade API) + React/TS frontend. Less pain now than later. |

---

## Remaining Phases

### Phase 2 — Strategy JSON + SubStrategy dataclass

Define `SubStrategy` (indicator + signal + window per factor) and a JSON-serializable strategy dict.

- Add `SubStrategy` dataclass to `strat.py`: `indicator_name`, `strategy_func_name`, `window`, `signal`.
- Add optional `name: str` to `StrategyConfig`.
- Define JSON schema for strategy_dict (see conflict table #1: split `StrategyConfig` from `DeploymentConfig`).
- Serialize via `dataclasses.asdict()`. Defer DB storage until schema stabilizes.
- Keep `param_opt_config` in a separate `OptimizationConfig`, not embedded in strategy (conflict #4).
- Start with flat AND/OR `conjunction` enum, not string expression parser (conflict #2).

### Phase 3 — Multi-factor Performance engine

- Add `combine_positions(positions, conjunction)` to `strat.py` — AND/OR logic.
- Refactor `Performance.enrich_performance()` to loop over substrategies, compute per-factor positions, then combine.
- AND/OR wrapper functions (user's idea of future proportional weighting noted for later).
- Unit tests for `combine_positions` (unanimous, disagree, single-factor, empty).

### Phase 4 — Multi-factor grid search

- Extend `ParametersOptimization.optimize()` for N-dimensional parameter space.
- Use `optuna` for Bayesian optimization on large grids (conflict #7: scikit-learn adds no value here).
- Keep Cartesian product as baseline for small grids.
- Guard against >10k combinations.

### Phase 5 — Visualization + Streamlit UI

- 1-factor: existing 2D heatmap.
- 2-factor: slice heatmaps (fix one factor at best, sweep the other).
- 3+ factors: parallel coordinates (Plotly).
- Add factor row builder in Streamlit sidebar ("Add/Remove Factor" buttons).
- Conjunction selector (AND/OR radio).

### Phase 6 — DB schema + persistence

- Design SQLite schema: `strategies`, `substrategies`, `optimization_runs`, `backtest_results`.
- Store strategy JSON blob alongside normalized columns for querying.
- Migrations in `db/sql/migrations/`.

### Phase 7 — Trade API service (design doc: `docs/design-trade-api.md`)

- FastAPI service in `trade_api/` — separate from backtest pipeline.
- `TradeAdapter` interface: `FutuAdapter` (wraps existing `FutuTrader`), future `BybitAdapter`.
- Signal execution loop: fetch data → compute indicators → combine → risk checks → execute.
- Endpoints: strategies CRUD, deployments CRUD, execution log, backtest results storage.
- Risk checks: kill switch, paper-first default, max position, stop loss, cash check, signal validation.
- One-click deploy flow: serialize strategy + backtest results → POST to Trade API → user fills deployment config → deploy.

### Phase 8 — TypeScript UI (do now, not later)

- FastAPI backend (shared with Trade API from Phase 7).
- React/TS frontend replacing Streamlit.
- Deploy button wired to Trade API `/deployments` endpoint.
- Strategy review dashboard: backtest results, live performance, trade log.

---

## Overall (non-phase items)

1. CI/CD to deploy to production
2. Hard coded options in main.py should be stored in the object script originated.
3. Logging: all modules now follow log_config.py pattern. ✓

---

## Multi-Factor Conjunction Strategy (from Copilot — reference)

Combine multiple indicators (e.g. price-based Bollinger + volume-based SMA) into a single backtest where a position is taken only when **all** (AND) or **any** (OR) factors agree on direction.

### Problem Statement

Currently each grid-search row runs **independently** — row 1 computes Sharpe from price alone, row 2 from volume alone. There is no mechanism to:
- Combine factor positions into a joint signal before computing PnL.
- Search over the combined parameter space (window₀ × signal₀ × window₁ × signal₁).
- Visualize and optimize across the joint space.

### Design Principles

1. **Separate concerns** — factor-combining logic belongs in `strat.py`, not scattered across `perf.py`/`param_opt.py`.
2. **Backward compatible** — single-factor backtests must continue to work unchanged with no new required fields.
3. **Testable first** — write unit tests for every new function/class before wiring into the Streamlit UI.
4. **Incremental** — implement in small, verifiable steps; each step must leave all existing tests passing.

### Phase 1 — Core Logic (strat.py + tests)

Goal: add factor-combining primitives with full test coverage.

1. **`FactorConfig` dataclass** (`strat.py`)
   - Fields: `indicator_name: str`, `strategy_func: Callable`, `data_column: str` (e.g. `"v"`, `"volume"`).
   - Frozen, like `StrategyConfig`.
   - Represents one factor's identity (indicator + strategy + which DataFrame column to use).

2. **`combine_positions()` function** (`strat.py`)
   - Signature: `combine_positions(positions: list[np.ndarray], conjunction: str = "AND") -> np.ndarray`
   - `"AND"`: take position only when **all** factors agree (element-wise min of absolute values, preserving sign when unanimous).
   - `"OR"`: take position when **any** factor signals (element-wise max of absolute values).
   - Returns `np.ndarray` of `{-1, 0, 1}`.
   - Edge cases: single-factor list returns that array unchanged; empty list raises `ValueError`.

3. **Extend `StrategyConfig`** (`strat.py`)
   - Add optional field `factors: tuple[FactorConfig, ...] = ()`.
   - Add optional field `conjunction: str = "AND"`.
   - Add helper `get_factors() -> list[FactorConfig]`: if `factors` is non-empty return it; otherwise synthesize a single-factor list from `indicator_name` + `strategy_func` + default column `"factor"` (backward compat).
   - **Do not remove** `indicator_name` / `strategy_func` — single-factor callers still use them directly.

4. **Unit tests** (`tests/unit/test_strat.py`)
   - `test_combine_positions_and_unanimous` — all agree → combined signal matches.
   - `test_combine_positions_and_disagree` — factors disagree → position = 0.
   - `test_combine_positions_or` — any factor signals → combined follows.
   - `test_combine_positions_single_factor` — passthrough.
   - `test_combine_positions_empty_raises` — ValueError.
   - `test_factor_config_creation` — frozen, correct fields.
   - `test_strategy_config_get_factors_legacy` — no `factors` set → infers single factor.
   - `test_strategy_config_get_factors_explicit` — `factors` set → returns them.

### Phase 2 — Performance Engine (perf.py + tests)

Goal: make `Performance` compute PnL from combined multi-factor positions.

1. **Multi-factor `Performance.__init__`** (`perf.py`)
   - Accept `window` and `signal` as **tuples** when multi-factor: `window=(20, 14)`, `signal=(1.5, 30)`.
   - For each factor in `config.get_factors()`:
     - Copy data, set `data['factor'] = data[factor.data_column]`.
     - Create `TechnicalAnalysis`, call the factor's indicator with corresponding window.
     - Compute position via the factor's strategy func with corresponding signal.
   - Call `combine_positions(all_positions, config.conjunction)` → final position.
   - Compute PnL/cumulative/drawdown from the **combined** position (single PnL stream).
   - **Backward compat**: when `config.get_factors()` returns one factor, behavior is identical to current code.

2. **Set `self.data['indicator']`** — for multi-factor, store the first factor's indicator (for plotting). Document that this is approximate.

3. **Unit tests** (`tests/unit/test_perf.py`)
   - `test_performance_single_factor_unchanged` — verify existing single-factor tests still pass.
   - `test_performance_multi_factor_and` — two factors, AND conjunction, verify combined position and PnL.
   - `test_performance_multi_factor_or` — two factors, OR conjunction.
   - `test_performance_multi_factor_window_signal_tuples` — verify tuple unpacking per factor.

### Phase 3 — Grid Search (param_opt.py + tests)

Goal: search over the combined N-dimensional parameter space.

1. **Extend `optimize()` or add `optimize_multi()`** (`param_opt.py`)
   - Accept per-factor ranges: `window_tuples=[(10,50,5), (5,30,5)]`, `signal_tuples=[(0.5,2.5,0.5), (20,80,10)]`.
   - Build Cartesian product across all factor window × signal combinations.
   - For each combo, call `Performance(data.copy(), config, window=(w0,w1), signal=(s0,s1))`.
   - Yield per-combo metrics: `dict(window_0=w0, signal_0=s0, window_1=w1, signal_1=s1, sharpe=...)`.
   - **Warn** when total grid size > 10,000 combinations.
   - **Backward compat**: when only one factor, accept flat `window_tuple`, `signal_tuple` and yield `(window, signal, sharpe)`.

2. **Unit tests** (`tests/unit/test_param_opt.py`)
   - `test_optimize_multi_factor_grid_shape` — verify correct number of combinations yielded.
   - `test_optimize_multi_factor_best_sharpe` — verify best combo selection.
   - `test_optimize_single_factor_backward_compat` — existing tests still pass.

### Phase 4 — Walk-Forward (walk_forward.py + tests)

Goal: multi-factor walk-forward overfitting detection.

1. **Extend `WalkForward.run()`** (`walk_forward.py`)
   - Accept per-factor parameter ranges (same signature as param_opt).
   - In-sample: run multi-factor grid search → best combo.
   - Out-of-sample: evaluate best combo → metrics.
   - Overfitting ratio logic unchanged.

2. **Unit tests** (`tests/unit/test_walk_forward.py`)
   - `test_walk_forward_multi_factor` — end-to-end with two factors.

### Phase 5 — Streamlit UI (app.py + integration tests)

Goal: expose multi-factor configuration in the dashboard.

1. **Factor row builder** (`app.py`)
   - Dynamic "Add Factor" button in sidebar.
   - Each row: data column selector, indicator dropdown, strategy dropdown, window/signal range sliders.
   - Conjunction selector: AND / OR radio button.
   - Minimum 1 factor row; maximum 4 (prevent grid explosion).

2. **Grid Search tab** — call multi-factor `optimize()`, build heatmap:
   - For 2 factors: 2D heatmap with `window_0` vs `window_1` (fixed signals at best), or use a dropdown to select which two axes to plot.
   - For 1 factor: existing heatmap unchanged.

3. **Full Analysis tab** — run multi-factor `Performance`, display combined PnL chart.

4. **Walk-Forward tab** — pass multi-factor ranges to `WalkForward.run()`.

5. **Integration tests** (`tests/integration/test_backtest_pipeline.py`)
   - `test_multi_factor_pipeline_end_to_end` — data → ta → multi-factor perf → grid search → walk-forward.

### Phase 6 — main.py CLI

1. **CLI args**: `--factors` (JSON or repeated `--factor` flags) for multi-factor from command line.
2. Print combined metrics and best multi-factor params.

### Open Questions

- Should each factor have its own `trading_period`, or share one from `StrategyConfig`?
- Should the heatmap for N>2 factors use parallel coordinates or marginal slices?
- How to handle factors with different data column requirements (e.g. one needs OHLC, another needs just `v`)?
- Should `combine_positions` support weighted averaging (e.g. 60% price, 40% volume) in addition to AND/OR?

### Lessons from Previous Attempt

The earlier multi-factor implementation was reverted because:
1. **No tests for new code** — `combine_positions`, `FactorConfig`, and multi-factor `Performance` paths had zero test coverage.
2. **`indicator` column missing** — multi-factor path didn't set `self.data['indicator']`, breaking plotting.
3. **`self.signal` type inconsistency** — stored scalar for single-factor, tuple for multi-factor, causing downstream bugs.
4. **walk_forward.py / main.py not wired** — only partial integration.
5. **No AND/OR selector in UI** — always defaulted to AND.
6. **Strategy func from first row only** — all factors shared one strategy function.
7. **Grid explosion** — no warning when N-factor product creates millions of combinations.
8. **Config override incompatible** — `config.indicator_name` override in single-factor path clashed with multi-factor.
9. **Design spread too thin** — changes touched 4 files simultaneously without incremental validation.

---

## ~~Walk-Forward Overfitting Test~~ ✅ Done

Split historical data into **in-sample** (training) and **out-of-sample** (validation) periods to detect parameter overfitting.

**Implemented:** `src/walk_forward.py`, CLI flags (`--walk-forward`, `--split`), Streamlit "Walk-Forward Test" tab, unit tests (`tests/unit/test_walk_forward.py`), integration tests.

### Concept

```
|◄──────── 10 years of data ────────►|
|◄── in-sample (5y) ──►|◄── out-of-sample (5y) ──►|
   grid search here          test best params here
```

1. **In-sample**: run `ParametersOptimization.optimize()` on the training window → best `(window, signal)` by Sharpe.
2. **Out-of-sample**: run `Performance` with those fixed params on the held-out window → measure Sharpe, return, drawdown.
3. **Overfitting ratio**: compare in-sample Sharpe vs out-of-sample Sharpe. A large drop signals overfitting.

### Implementation Plan

1. **`src/walk_forward.py`** — new module with a `WalkForward` class:
   - `__init__(data, split_ratio, trading_period, indicator_func, strategy_func, *, fee_bps=None)`
   - `split_ratio` (float, e.g. `0.5`) controls where to cut the data.
   - `run(window_tuple, signal_tuple)` → runs grid search on in-sample, evaluates best params on out-of-sample.
   - Returns a result object / dict with:
     - Best `(window, signal)` from in-sample
     - In-sample metrics: Sharpe, return, max drawdown, Calmar
     - Out-of-sample metrics: same set
     - Overfitting ratio: `1 - (oos_sharpe / is_sharpe)` — closer to 0 is better, >0.5 is suspicious
   - Optional: **rolling walk-forward** — slide the train/test window forward in steps (e.g. train on years 1–5, test on 6; then 2–6, test on 7; etc.) and average the overfitting ratio across folds.

2. **`src/main.py`** — add CLI flags:
   - `--walk-forward` (flag) — enable walk-forward test instead of plain grid search.
   - `--split` (float, default `0.5`) — train/test split ratio.
   - Output: print in-sample vs out-of-sample metrics side by side + overfitting ratio.
   - Save walk-forward results to `results/wf_<symbol>_<indicator>.csv`.

3. **`src/app.py`** — add a **Walk-Forward Test** tab in the Streamlit dashboard:
   - Slider for split ratio (0.2–0.8).
   - Reuse grid search bounds from sidebar.
   - Display in-sample vs out-of-sample metrics table.
   - Plot cumulative return for both periods (vertical line at split point).
   - Show overfitting ratio with colour coding (green < 0.3, yellow 0.3–0.5, red > 0.5).

4. **Tests**:
   - `tests/unit/test_walk_forward.py` — split correctness, metric computation, edge cases (split too small).
   - `tests/integration/test_backtest_pipeline.py` — full walk-forward pipeline with synthetic data.

### Metrics to report

| Metric | In-Sample | Out-of-Sample |
|--------|-----------|---------------|
| Best window | from grid search | (same, fixed) |
| Best signal | from grid search | (same, fixed) |
| Total Return | ✓ | ✓ |
| Annualized Return | ✓ | ✓ |
| Sharpe Ratio | ✓ | ✓ |
| Max Drawdown | ✓ | ✓ |
| Calmar Ratio | ✓ | ✓ |
| **Overfitting Ratio** | — | `1 - (oos_sharpe / is_sharpe)` |


## SQLite (database: TradeBros)

1. Store datasource metadata and **requirements** for what to persist; minimize repeat API queries. Each stored requirement should point at the dataset it produced.

    REFDATA.APP

    | APP_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    |--------|------|-------------|---------|--------------|
    | 1 | Futu API | Futu Trade API | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | Alphavantage | Alphavantage | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.TM_INTERVAL

    | TM_INTERVAL_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    |----------------|------|-------------|---------|--------------|
    | 1 | Daily | Daily Closing Price | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.ORDER_STATE

    | ORDER_STATE_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    | --- | --- | --- | --- | --- |
    | 1 | NEW | Order has been created but not yet sent | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | PENDING | Order submitted, awaiting processing | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 3 | PARTIALLY_FILLED | Order partially executed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 4 | FILLED | Order fully executed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 5 | CANCELLED | Order cancelled before execution | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 6 | REJECTED | Order rejected by system or exchange | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.TRANS_STATE

    | TRANS_STATE_ID | NAME | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    | --- | --- | --- | --- | --- |
    | 1 | PENDING | Transaction created, not yet processed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | COMPLETED | Transaction successfully completed | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 3 | FAILED | Transaction failed due to error | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    REFDATA.API_LIMIT — record rate limits and quotas per data source so the pipeline can throttle automatically.

    | API_LIMIT_ID | APP_ID | LIMIT_TYPE | MAX_VALUE | TIME_WINDOW_SEC | DESCRIPTION | USER_ID | UPDATE_DB_TS |
    |--------------|--------|------------|-----------|-----------------|-------------|---------|--------------|
    | 1 | 2 | RATE | 1 | 1 | 1 request per second (free tier) | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 2 | 2 | DAILY_QUOTA | 25 | 86400 | 25 requests per day (free tier) | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |
    | 3 | 2 | OUTPUT_SIZE | 100 | NULL | Compact mode returns ~100 most recent trading days only | alfcheun | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    BACKTEST.API_REQUEST

    | API_REQ_ID | API_REQ_VID | APP_ID | TM_INTERVAL_ID | SYMBOL | IS_CURRENT_IND | RANGE_START_TS | RANGE_END_TS | STORAGE_PATH | API_REQ_PAYLOAD | USER_ID | CREATED_AT |
    |------------|-------------|--------|----------------|--------|----------------|----------------|--------------|--------------|-----------------|--------|------------|
    | UUID | 1 | 2 | 1 | BTCUSDT | Y | 2010-01-01T00:00:00Z | 2026-01-01T00:00:00Z | /data/raw/alphavantage | `{"filter1":"xxx","filter2":"xxx","filterdate":{"from":"...","to":"..."}}` | alfcheun | 2026-03-30T12:00:00Z |

    BACKTEST.API_REQUEST_PAYLOAD — normalized storage for large/split responses. `API_REQ_PAYLOAD` on `API_REQUEST` holds inline or summary JSON; use this child table when the payload is large or versioned separately.

    | API_REQ_ID | API_REQ_VID | PAYLOAD | CREATED_AT |
    |------------|-------------|---------|------------|
    | UUID | 1 | {...data...} | CURRENT TIMESTAMP - CURRENT TIMEZONE |

    TRADE.TRANSACTION — `ORDER_STATE_ID` is denormalized here for convenience; consider a dedicated `ORDERS` table if order lifecycle grows.

    | TRANS_ID | APP_ID | ORDER_STATE_ID | TRANS_STATE_ID | SYMBOL | BUY_SELL_CD | TRANS_CCY_CD | QUANTITY | PRICE | NOTIONAL_AMT | FEE_AMT | CREATED_AT |
    |----------|--------|----------------|----------------|--------|-------------|--------------|---------|-------|--------------|---------|------------|
    | UUID | 1 | 2 | 3 | BTCUSDT | B | USDT | 0.015 | 97234.50 | 1458.52 | 0.87 | 2026-03-30T14:22:01Z |
    | UUID | 1 | 2 | 3 | BTCUSDT | S | USDT | 0.010 | 97100.00 | 971.00 | 0.58 | 2026-03-30T15:05:33Z |
    | UUID | 2 | 1 | 1 | ETHUSDT | B | USDT | 0.50 | 1820.75 | 910.38 | 0.55 | 2026-03-30T16:41:12Z |


## Agent

1. Prefer backtests anchored on **daily closing prices** (align rules with that bar).

## Trade

1. Redesign trading repository: strategies as objects, loadable from the src package (shared definitions with live trading).

```
Quant_Strategies/
├── src/                     # Backtesting pipeline
│   ├── data.py              # Data retrieval (YahooFinance, AlphaVantage, Glassnode, FutuOpenD)
│   ├── ta.py                # Technical analysis indicators
│   ├── strat.py             # Signal generation strategies
│   ├── perf.py              # Performance metrics & PnL engine
│   ├── param_opt.py         # Grid-search parameter optimization
│   ├── log_config.py        # Centralised logging configuration
│   ├── main.py              # CLI entry point — configurable via argparse
│   └── app.py               # Streamlit web dashboard
│
├── .env                     # API keys (gitignored)
├── backup/
│   └── deco/                # Decommissioned Bybit scripts (kept for reference)
├── results/                 # Output CSVs and heatmap PNGs
└── tests/                   # Unit, integration, and e2e tests
```

1. Plug in Futu API trade (optional Alphavantage / Glassnode).
2. Start with a crypto pricing strategy.

---

## Code Quality & Robustness

### Error Handling
1. Add try/except around all API calls in `data.py` (Glassnode, Futu) — currently any network failure crashes silently or propagates unhandled.
2. Guard against division-by-zero in `perf.py` (Sharpe denominator, annualized return).
3. Add error handling for future live trading scripts.
4. Validate DataFrame columns exist before accessing (`ta.py` assumes `'factor'`, `'Close'`, `'High'`, `'Low'` without checks).

### Configuration
1. Extract hardcoded parameters from source into a config file (YAML or JSON):
   - Symbol, date range, interval (`main.py`)
   - Indicator window, signal threshold (`main.py`)
   - Trading period constant (`365 * 24 * 6`)
   - Transaction cost (`0.0005` in `perf.py`)
   - Bet size, polling interval (future live trading scripts)
2. Support CLI arguments for `main.py` (e.g. `python main.py --symbol BTC --start 2020-01-01 --end 2025-01-01`).

### Logging
1. Replace all `print()` calls with Python `logging` module — especially in live trading scripts.
2. Add persistent log files for trade execution audit trail (future live trading scripts).
3. Add timestamps and log levels for debugging.

### Code Duplication
1. `perf.py`: Strategy and buy-and-hold metrics are near-identical — refactor into a shared `_compute_metrics(returns)` method.
2. Inline z-score logic in decommissioned trade scripts should be reused from `ta.py` in future live trading.
3. Fix typo: `get_buy_hold_get_annualized_return()` → `get_buy_hold_annualized_return()`.

---

## Architecture & Design

### Data Layer
1. Add a common interface (base class or protocol) for all data sources (`FutuOpenD`, `Glassnode`) so they return a consistent DataFrame schema.
2. Fix `@lru_cache` on instance methods in `data.py` — either use `functools.cached_property` or move to module-level caching.
3. Add input validation on symbols, date ranges, intervals at the data layer boundary.

### Strategy Abstraction
1. Convert `Strategy` static methods to a proper strategy interface (base class with `generate_signal(data, params) -> Series`).
2. Future live trading should import and use the same strategy definitions as backtesting.
3. Add position sizing support beyond fixed `{-1, 0, 1}`.

### Live Trading Reliability
1. When building new live trading integration, use SQLite or an in-memory queue instead of CSV as shared state (lesson from decommissioned Bybit scripts — see `backup/deco/`).
2. Add graceful shutdown (signal handling for SIGINT/SIGTERM) to any live trading loops.
3. Add position reconciliation — check actual exchange position vs. expected before placing orders.
4. Persist trade fills to database (not just stdout).

### Directory Restructure
1. Decommissioned Bybit scripts moved to `backup/deco/` — reuse signal/strategy logic for future integrations.
2. Clean up dead/commented-out code in `main.py` and `ta.py` (commented MACD method, placeholder data merge).

---

## Testing & CI/CD

### Unit Tests
1. Test indicator calculations in `ta.py` against known values (e.g. SMA of `[1,2,3,4,5]` with window 3).
2. Test `perf.py` metrics: Sharpe, max drawdown, Calmar on synthetic return series.
3. Test strategy signals: verify `{-1, 0, 1}` output for known inputs.
4. Test data source classes with mocked API responses.

### Integration Tests
1. End-to-end backtest run with sample data (no live API calls).
2. Validate parameter optimization returns expected grid shape.

### CI/CD Pipeline
1. GitHub Actions workflow: lint (`ruff`/`flake8`), test (`pytest`), on push/PR.
2. Add `pyproject.toml` for standardized project metadata and tool config.
3. Pre-commit hooks for formatting and linting.

---

## Documentation

1. Add inline comments for non-obvious algorithm details (RSI smoothing, Bollinger Z formula).
2. Add a troubleshooting section to README (Futu OpenD connection, API rate limits, common errors).
3. Add type hints to function signatures across all modules.
4. Document the database schema relationships and query patterns (when SQLite is implemented).
