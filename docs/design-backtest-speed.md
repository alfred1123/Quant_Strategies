# Design: Backtest Speed Optimization

**Status:** Draft  
**Date:** 2026-04-15  
**Scope:** `src/param_opt.py`, `src/perf.py`, `src/strat.py`

## 1. Problem

Parameter optimization (grid search / Bayesian) is the slowest user-facing operation. A 200-trial Bollinger grid takes ~0.8 s today; a 10 000-trial multi-factor search can take minutes. The bottleneck is **per-trial overhead**, not algorithmic complexity.

## 2. Profiling Results

Measured on 2 500-row dataset (≈10 years daily), Bollinger band indicator, 500 iterations each:

| Component | Time / trial | % of total |
|-----------|-------------|------------|
| `df.copy()` | 0.01 ms | <1% |
| `TechnicalAnalysis.__init__` | 0.01 ms | <1% |
| Indicator (`get_bollinger_band`) | 0.25 ms | 6% |
| Signal function | 0.01 ms | <1% |
| `_compute_pnl_columns` (pandas) | ~3.1 ms | **74%** |
| `get_sharpe_ratio` (pandas `.loc`) | ~0.3 ms | 7% |
| Other (pct_change, object init) | ~0.5 ms | 12% |
| **Full trial** | **4.2 ms** | 100% |

### Numpy-only alternative (same math, no DataFrame writes):

| Approach | Time / trial | Speedup vs current |
|----------|-------------|-------------------|
| Numpy PnL + Sharpe only | 0.024 ms | **149×** |
| Cached indicator + numpy PnL + Sharpe | 0.029 ms | **120×** |

The 120× speedup is achievable because:
1. `_compute_pnl_columns` writes 7 pandas DataFrame columns per trial — but the optimizer only needs the Sharpe ratio scalar.
2. Indicators are recomputed from scratch every trial, even when the window hasn't changed (many `(window, signal)` pairs share the same window).
3. `pct_change()` is recomputed every trial — it depends only on price data, not on window/signal.

## 3. Proposed Optimizations

### O-1: Fast Sharpe objective (numpy-only path in `param_opt.py`)

**Impact: ~100× for single-factor optimization**

Add a numpy-only Sharpe computation directly in the `objective()` closure, bypassing `Performance` + `_compute_pnl_columns` entirely during optimization.

```
# Pre-compute once outside the trial loop:
chg = data['price'].pct_change().values
tc  = fee_bps / 10_000

# Per trial (numpy only):
indicator_vals = indicator_func(window)       # pandas → .values
position = signal_func(indicator_vals, signal) # already returns ndarray
pos_x1 = np.empty_like(position)
pos_x1[0] = np.nan; pos_x1[1:] = position[:-1]
trade = np.abs(position - pos_x1)
pnl = pos_x1 * chg - trade * tc
sl = pnl[max_window:]
mask = ~np.isnan(sl)
sharpe = np.mean(sl[mask]) / np.std(sl[mask], ddof=1) * np.sqrt(trading_period)
```

**Trade-off:** The optimizer no longer builds full `Performance` DataFrames. The final best-params result still uses the full `Performance` path (for all metrics + visualization).

**Risk:** Low — same math, just avoids pandas column assignment overhead. Must validate numerical equivalence in tests.

### O-2: Indicator cache by window (`param_opt.py`)

**Impact: ~5–10× fewer indicator computations**

For single-factor optimization, many trials share the same window (varying only signal). Pre-compute all indicators for all unique windows once, then look up per trial.

```python
# Before study.optimize():
ta = TechnicalAnalysis(data)
indicator_func = getattr(ta, config.indicator_name)
indicator_cache = {}
for w in window_values:
    indicator_cache[w] = indicator_func(w).values  # compute once

# In objective():
ind_arr = indicator_cache[window]  # O(1) lookup
```

For multi-factor, extend to per-factor caches:
```python
factor_caches = []  # list of {window: ndarray}
for i, sub in enumerate(subs):
    ta_i = TechnicalAnalysis(sub_data_i)
    func_i = getattr(ta_i, sub.indicator_name)
    factor_caches.append({w: func_i(w).values for w in window_ranges[i]})
```

### O-3: Pre-compute `pct_change()` once

**Impact: Minor (~0.1 ms/trial saved)**

Currently `_enrich_single_factor()` calls `self.data['price'].pct_change()` inside every trial. Move it outside the loop:

```python
chg = self.data['price'].pct_change().values  # once
```

This is subsumed by O-1 (which pre-computes `chg` outside the loop), but is also a standalone micro-optimization if O-1 is deferred.

### O-4: Multi-factor numpy fast path

**Impact: ~50–100× for multi-factor optimization**

Same principle as O-1 but for `optimize_multi()`. Pre-compute per-factor indicator caches (O-2), then in each trial:

1. Look up cached indicator arrays per factor
2. Apply signal functions (already numpy)
3. Combine positions with `combine_positions()` (already numpy-based)
4. Compute Sharpe via numpy

Requires `combine_positions` to accept raw numpy arrays (it already does via `np.where`).

## 4. What Does NOT Change

- **`Performance` class** — unchanged. `enrich_performance()` / `_compute_pnl_columns()` remain the canonical path for single-run backtests, result visualization, and CSV export.
- **`get_sharpe_ratio()` and other metric methods** — unchanged. Only the optimization objective uses the fast numpy path.
- **Signal functions** — unchanged (already return numpy arrays).
- **`TechnicalAnalysis` indicator methods** — unchanged (called once per window, cached).
- **`main.py` / `app.py` / API single-backtest** — unchanged. Speed optimization only applies to `param_opt.py` optimization loops.

## 5. Implementation Plan

| Phase | Change | Files | Est. Speedup |
|-------|--------|-------|-------------|
| 1 | O-1 + O-2 + O-3: Fast single-factor objective | `param_opt.py` | ~100× |
| 2 | O-4: Fast multi-factor objective | `param_opt.py` | ~50–100× |
| 3 | Numerical equivalence tests | `tests/unit/test_param_opt.py` | — |

### Phase 1 detail

In `ParametersOptimization.optimize()`:
1. Pre-compute `chg = self.data['price'].pct_change().values`
2. Build `indicator_cache = {w: indicator_func(w).values for w in window_values}`
3. Replace `objective()` body with numpy-only Sharpe (O-1), using cached indicators (O-2)
4. After `study.optimize()`, reconstruct full `Performance` only for the best trial (for the `OptimizeResult` metrics/plots)

### Phase 2 detail

In `ParametersOptimization.optimize_multi()`:
1. Pre-compute per-factor `chg` arrays and indicator caches
2. Replace multi-factor `objective()` with numpy-only path using `combine_positions` on raw arrays
3. Same post-optimization full-Performance reconstruction

## 6. Testing

- **Numerical equivalence**: For each indicator × signal type, run 10 random (window, signal) pairs through both the pandas `Performance` path and the numpy fast path. Assert Sharpe ratios match within `1e-10`.
- **Edge cases**: NaN-heavy data, zero-std positions, single-row data, all-flat positions.
- **Regression**: Existing 342 tests must pass unchanged.
- **Benchmark**: Before/after timing on 200-trial and 2000-trial grids, logged to stdout (not committed).

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Numerical drift between pandas and numpy paths | Equivalence tests with tight tolerance |
| Indicator cache memory for large window ranges | Cache is `O(n_windows × n_rows)` — at 100 windows × 10k rows × 8 bytes = 8 MB, negligible |
| Multi-factor `combine_positions` assumes numpy input | Already uses `np.where` / `np.searchsorted` — verify with unit tests |
| Breaking the SSE progress callback | Callbacks still fire per-trial in `study.optimize()` — no change to callback mechanism |

## 8. Expected Outcome

| Scenario | Current | After |
|----------|---------|-------|
| 200-trial single-factor (Bollinger) | ~0.8 s | ~0.06 s |
| 2 000-trial single-factor | ~8 s | ~0.6 s |
| 10 000-trial multi-factor (2 factors) | ~42 s | ~1–2 s |

These estimates assume 2 500-row datasets. Larger datasets scale linearly with row count for the numpy path.
