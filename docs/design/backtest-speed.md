# Design: Backtest Speed

**Status:** Implemented (2026-09-06)
**Dates:** 2026-04-15 (first analysis) · 2026-09-05 (re-profiled) · 2026-09-06 (landed)
**Scope:** `quant/strategy/optimizer.py`, `quant/strategy/objective.py`, `tests/unit/test_objective.py`, `tests/unit/test_param_opt.py`
**Out of scope:** `quant/strategy/performance.py` (unchanged — still the report engine)

See [OOP Strategy Framework](../architecture/oop-framework.md) for the class conventions
and [Pipeline](../architecture/pipeline.md) for where the optimizer sits.

---

## 1. Problem

A queued backtest spends its time in `ParametersOptimization.run()` → one evaluation per
`(window, signal)` set. Two costs stacked:

1. **The objective did report-grade work for one scalar.** `Performance.enrich_performance()`
   writes ten DataFrame columns so `get_sharpe_ratio()` can read one of them. Indicators and
   `pct_change()` were recomputed every trial.
2. **`optuna.samplers.GridSampler` is O(n²).** Before every trial it walks every prior trial
   (`_get_unvisited_grid_ids`). At 420 trials this already cost ~4× the objective; at
   `OPTUNA_MAX_TRIALS = 10_000` it extrapolated to ~0.8 s/trial — past the worker's
   100-minute deadline.

---

## 2. What landed

Strict OOP. No closures capturing `self`, no `GridSampler`, no leftover Cartesian comment
block. Public `ParametersOptimization.optimize` / `optimize_multi` / `run` signatures are
unchanged, so `backtest_service.py` and `walk_forward.py` did not move.

| Class | Module | Role |
|---|---|---|
| `ParametersOptimization` | `optimizer.py` | Build `SearchSpace` + `Objective`, pick the search, shape `OptimizeResult` |
| `SearchSpace` | `optimizer.py` | Named axes, product size, param ↔ `(windows, signals)` |
| `SearchStrategy` (ABC) | `optimizer.py` | `log_start` + `search` — no `isinstance` in the orchestrator |
| `ExhaustiveSearch` | `optimizer.py` | `itertools.product` + `study.add_trial` (restores [decision #7](../decisions.md)) |
| `BayesianSearch` | `optimizer.py` | `TPESampler`; `suggest_and_evaluate` is a method, not a closure |
| `Objective` (ABC) | `objective.py` | Precompute `chg` / fee / period; numpy Sharpe including `MIN_METRIC_OBS` (#63) |
| `SingleFactorObjective` | `objective.py` | One `IndicatorCache`, `config.signal_func` |
| `MultiFactorObjective` | `objective.py` | One cache per `SubStrategy`; `combine_positions` with strengths |
| `IndicatorCache` | `objective.py` | `{window: ndarray}` via `TechnicalAnalysis`, `reindex`-aligned (RSI is short) |

`Performance` is still the engine for best-trial metrics, equity curves, walk-forward
IS/OOS evaluation, and live `compute_latest_position`. The objective is tested against it,
never allowed to call it.

**Coverage fail-fast.** A cross-product factor below 80 % date coverage used to fail every
trial (`-inf`) and finish as an empty `COMPLETED` job. The check now runs once in the
`Objective` constructor and raises `ValueError`, so the worker writes `FAILED` with the
cause. See [decision #64](../decisions.md).

---

## 3. Profiling (2026-09-05, before the change)

2 500-row synthetic daily series, Bollinger, `momentum_band_signal`, fee 5 bps, period 365.
Python 3.12.3 / optuna 4.8.0 / pandas 3.0.3 / numpy 2.4.6. `time.perf_counter()`, 200 reps.

| Component | ms / trial |
|---|---|
| `Performance.__init__` | 0.04 |
| `_trade_enrich_positions` | 1.70 |
| `_compute_pnl_columns` | 2.69 |
| `get_sharpe_ratio` | 0.17 |
| **Full objective** | **4.60** |
| numpy Sharpe on a cached indicator | **0.054** (bit-identical on that data) |

`GridSampler` overhead, constant objective: 2.2 / 18.3 / 59.4 / 160 ms per trial at
100 / 420 / 1 000 / 2 000 trials. `TPESampler` at 10 000 trials: 37 ms/trial.
`study.add_trial` + `best_value`: 0.16 ms/trial at 420, 0.98 ms at 10 000.

End-to-end `optimize` on a 20×21 grid: **10.88 s (25.9 ms/trial)** — ~80 % sampler.

Do not call `study.trials` or `study.get_trials()` (default `deepcopy=True`) inside the
trial loop; both scan-and-copy the whole study.

---

## 4. Math contract with `Performance`

| `Performance` | `Objective` |
|---|---|
| `price.pct_change()` per trial | once, via the same pandas call |
| same-cusip single factor: indicator on the loaded `factor` column (`data_column` ignored) | same |
| other-cusip / multi: `sub.data_column`, 80 % coverage check | once, at construction |
| `indicator_func(w).reindex(index)` | cached after the same `reindex` |
| `FinalPosition.shift(1)` → trade → pnl | ndarray slice / `abs` / multiply |
| `iloc[max(windows):]`, skipna `std(ddof=1)`, zero-std → NaN | `finite.size < MIN_METRIC_OBS` → NaN, then the same std guard |
| per-trial exception → `-inf` | constructor errors propagate; per-trial exceptions still `-inf` |

---

## 5. Tests

- Existing `tests/unit/test_param_opt.py` / `test_walk_forward.py` — result shape, TPE log
  token, callbacks, dispatch.
- `TestObjectiveEquivalence` — every `TechnicalAnalysis` indicator × every
  `SignalDirection` function × 10 random pairs; multi-factor AND/OR/FILTER; cross-product;
  flat series; window ≥ row count; fee_bps. Tolerance `1e-12`, NaN ↔ NaN.
- `TestIndicatorCache`, `TestSearchSelection`, `TestExhaustiveSearch`, `TestCoverageFailFast`.

---

## 6. What did not change

- `Performance` methods, `TechnicalAnalysis`, `SignalDirection`, `combine_positions`.
- `OptimizeResult` (``best_params`` / ``params_from_best``), `OPTUNA_MAX_TRIALS`, `OPTUNA_SEED`.
- SSE `init` / `progress` / `result` and the callback signature (`trial.number`,
  `study.best_value`).
- Anything in the database.

Bayesian (TPE) jobs remain TPE-bound (~37 ms/trial at 10 000). That path is only taken
when the space exceeds `OPTUNA_MAX_TRIALS`. Measure before changing the sampler.

---

## 7. Rejected alternatives

| Alternative | Why not |
|---|---|
| Subclass `GridSampler` and cache unvisited ids | Private optuna internals; the exhaustive case does not need a sampler |
| Drop optuna | `extract_plots()` and TPE need it — keep it as recorder + Bayesian |
| Speed up `Performance` itself | Its cost *is* its output (ten report columns) |
| Multiprocessing inside one job | `MAX_CONCURRENT_WORKERS` is the parallelism knob; it does not remove O(n²) |
| Procedural closures that "just precompute" | Rejected: new code follows the OOP framework |
