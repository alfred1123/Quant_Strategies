# Long-term fixes: B1 combiner, window bounds, data columns, repeated trials (2026-09-29)

**Doc type:** design items for decision. No engine change in this PR.
**Checked against:** `main` at `2d53b6f7ddd7052aaa065d22902217b99bb65e9c` (PR #73 merge, 2026-09-29 05:35 HKT). Line numbers below are from that commit.
**Follows:** [AlgoDaemon bug report (2026-09-27)](2026-09-27-algodaemon-bug-report.md) (B1), [Bug verification, rounds 3–4](2026-09-27-bug-verification-round3-4.md) (B23 items 2–3, B26 item 7). Reviews PRs #74, #75 (closed), #76 (draft) and #71 (open, going back to draft).

How each point was checked:

| Mark | Meaning |
|---|---|
| Ran | Reproduced on synthetic data with the engine code from `2d53b6f7d`. No production call. |
| Read | Read in the source at `2d53b6f7d`. |
| Raw | From stored job rows, as recorded in the round 3–4 review. Not re-read today. |
| Reported | A number another agent gave. Not re-run here. |

## The rules every fix here must meet

1. The fix lives in the class or module that owns the behaviour. No new cross-module coupling. No duplicated logic.
2. No backward compatibility: no shims, aliases, deprecated parameters or fallbacks. Replace the interface and update every caller in the same change.
3. No hard-coded values. Persist in the DB and read it; config only where the design suits.
4. A test that fails on `main` and passes with the fix, edge cases, full suite plus ruff plus mypy clean, and a before/after backtest when results change.
5. Built to last. Each item says which future changes the fix survives (new strategy type, new indicator, new coin, hourly bars, a DB schema change, a new entry point such as API, worker or CLI) and what a smaller fix would fail on.

## Summary

| Item | Bug | Verdict | Recommended fix | Size (real code) |
|---|---|---|---|---|
| [A](#a-b1-and-and-filter-act-like-or) | B1: AND and FILTER (3+) act like OR | **#76 is the root-cause fix for the combiner.** The design work is around it: stored results, live deployments, promotion comparisons, and how conjunction modes are represented | Merge #76 (after rebase). Then, as separate follow-ups: a result flag with an engine stamp, a decision on live AND deployments before #76 ships, and later a combiner registry read from `REFDATA.CONJUNCTION` | #76: 16 lines. Flagging: ~120–200 incl. SQL and UI. Registry: ~60–90 |
| [B](#b-window-and-signal-range-bounds) | B23: `RangeParam` has no bounds | **Design item.** A schema-only fix breaks the live path and hard-codes the minimum | A per-indicator window floor on `REFDATA.INDICATOR`, checked by one strategy builder that every entry point calls. Shape invariants stay in the schema | ~120–180 plus ~100 test lines |
| [C](#c-b26-data_column-is-not-validated) | B26: `data_column` is a free string | **Design item, but smaller than it looks.** The valid list is already in the DB (`REFDATA.DATA_COLUMN`) and nothing in the backend reads it | Validate against `REFDATA.DATA_COLUMN` in the same builder. One factor-series resolver replaces the two copies in `Performance` and `Objective` and the one-factor fallbacks. Remove the `"v"` defaults | ~60–100 |
| [D](#d-repeated-cells-in-top10-and-the-trial-budget) | Repeated cells in `top10` | **Design item.** #71 hides the symptom. The cause is that a repeated cell uses up a trial | The search counts distinct cells. A repeat is not re-scored and does not use the budget. Budget, seed and over-budget mode move to a CONFIG row. The result stores search type, grid size and distinct cells | ~60–90 plus SQL, schema and UI (~40) |

B, C and part of A share one owner: a **strategy builder** that turns a request into a `StrategyConfig` plus a parameter grid, using ref data. Today that is a set of free functions in `quant/strategy/backtest_service.py` (`build_config` line 285, `_build_param_ranges` line 333) and `quant/strategy/signals.py` (`resolve_signal_func` line 312). Each item below says what it adds to that builder. See [Shared owner](#shared-owner-the-strategy-builder).

## A. B1: AND and FILTER act like OR

### Verified problem

- `combine_positions` (`quant/strategy/signals.py` line 185) sends AND to `_combine_and` (line 154) and FILTER to `_combine_filter` (line 131).
- In `_combine_and`, with strengths, `disagree = ~all_positive & ~all_negative & has_signal & ~nan_mask`. A `{+1, 0}` row is not unanimous and has a signal, so it is a "disagreement". `_strongest_sign` (line 122) masks flat factors to `-inf` and returns the only non-flat sign. The row becomes +1.
- `_combine_filter` with three or more factors has its own copy of the same mask for the direction factors. Two-factor FILTER passes the signal through and is correct.
- Without strengths, AND is correct (`test_and_one_flat_gives_flat`). But every production path passes strengths: `Performance._compute_multi_factor_outputs` (`quant/strategy/performance.py` line 227) and `MultiFactorObjective.__call__` (`quant/strategy/objective.py` line 163).

**Ran.** With `a = [1, 1, 0, 1, 1]`, `b = [0, 1, 0, -1, 0]` and strengths, AND returns `[1, 1, 0, 1, 1]`, the same as OR. A three-factor FILTER with the gate on returns the same.

### Is combination re-implemented anywhere else?

**No. Read.** Only `signals.py` combines positions.

- `Performance` and `MultiFactorObjective` both call `combine_positions`.
- The live path (`quant/strategy/live_service.py`) builds a `StrategyConfig` and reads the position through `Performance.compute_latest_position` (`performance.py` line 156). It does not combine on its own.
- `WalkForward` uses `ParametersOptimization` and `Performance`.

So a fix inside `_combine_and` reaches the backtest, the search, walk-forward and live trading in one place.

### PR #76, assessed

**What it does (Read, diff).** A strength conflict is a row with both +1 and −1 and no flat factor. A flat factor vetoes, including beside opposite signs. FILTER with 3+ factors calls `_combine_and` for its direction factors, which removes the duplicate mask. `{+1, −1}` with no flat factor still goes to the stronger reading. 16 real-code lines in `signals.py`. No caller changes. No compatibility path kept.

**Evidence (Reported by Quick Fix Bot, not re-run here).** Ruff and mypy show no new findings on the touched files. Full unit suite 1,681 passed, 8 skipped (the PR body also reports unit plus integration at 1,733 passed, 24 skipped). The failing-on-main test is `{+1, 0}` with strengths: `main` gives 1.0, 0.0 is expected. Before/after on the repo's ETH daily test data (not a platform run on the finalists): on `main`, AND equals OR (Sharpe −0.23, 25 trades, 97 bars long). With the fix, AND gives Sharpe −1.09, 27 trades, 56 bars long. OR is unchanged.

**Verdict: #76 is the root-cause fix for the combiner.** The fault is one wrong mask, in the one function that owns AND, plus a copy of it that #76 removes. A bigger model change is not needed to fix the behaviour.

- **No tri-state type needed.** Positions are already {−1, 0, +1, NaN}. NaN means no data (warm-up), and the row goes NaN. 0 means flat. Whether flat vetoes or abstains depends on the mode: AND vetoes, OR abstains, the FILTER gate treats 0 as closed. After #76 each combiner says that in its own code. A separate "no opinion" value would have no producer: no signal function emits one.
- **Rules check.** Owner: yes. No shims: yes. No hard-coded values: the conflict rule is logic, not a tunable number. Tests: see the gaps below.
- **Housekeeping.** #76 is based on `31bec52af` and GitHub shows it as behind `main`. It needs a rebase onto `2d53b6f7d`. Its doc edits say B1 is "fixed on main", which is only true once it merges.

**Test gaps to close in #76 before merge:**

- 3-factor AND `{+1, +1, 0}` stays 0.
- A row that is all 0 with strengths stays 0. A NaN in any factor, with strengths, stays NaN.
- Parity: `Performance` and `MultiFactorObjective` give the same Sharpe for one long-only AND configuration. They share the combiner, and the test keeps it that way.
- Live: `Performance.compute_latest_position` on a long-only AND pair returns 0 on a bar where one factor is flat.

### What would break in a month even with #76 merged

The combiner is fixed. These are the parts around it.

1. **Stored results cannot be told apart.** `BT.RESULT` (`db/liquidbase/bt/tables/RESULT.sql`) has no engine or logic version. The only way to find pre-fix AND results is `CREATED_AT` compared with a deploy time nobody records. A worker that was mid-job during the deploy blurs the cut.
2. **Promotion compares across the change.** `quant/promotion/evaluate.py` (line 124) compares a new result's metrics with the current best VID's stored result. A post-fix AND run for a lineage is compared with a pre-fix, OR-like result for the same lineage. The gate then reads the fix as a regression, or an OR-like number as the bar to beat.
3. **Live deployments change on the next apply.** A deployed AND strategy (or FILTER with 3+ factors) was chosen on OR-like numbers. The first apply after #76 deploys computes the AND position, which is long on fewer bars (97 → 56 on the reported ETH data). Nothing re-validates it first. This is a trading change, not only a research change.
4. **A new conjunction mode repeats the pattern.** Modes are a free string. `combine_positions` checks a hard-coded tuple (`("AND", "OR", "FILTER")`, line 210), while `REFDATA.CONJUNCTION` already lists the same three rows for the drawer. `StrategyConfig.conjunction` defaults to `"AND"` (line 52), and `build_config` defaults `req.conjunction or "AND"` (line 328). A new mode, for example the averaged ensemble in [Fractional sizing](2026-09-26-fractional-sizing-stateful-exits.md), means editing an `if` chain, the tuple, the DB row and the drawer, with no contract test on what 0 means in that mode.

### Options

| Option | What | Pros | Cons against the rules |
|---|---|---|---|
| A1. #76 alone | Fix the mask, remove the FILTER copy | Root cause of the behaviour. Small. Right owner | Leaves stored-result identity, promotion and live deployments to chance (points 1–3) |
| A2. #76 plus a result flag and engine stamp | Merge #76. Follow-up adds `BT.RESULT_FLAG` and an engine stamp on each result | Stored AND results found by a query, not a guessed date. Reused for every later engine change (B2 restart, B22, fill delay) | Needs a Liquibase release, a stored procedure and a UI chip |
| A3. A2 plus a combiner registry | One `Combiner` class per mode, registered by name, mapped from `REFDATA.CONJUNCTION` like `SIGNAL_TYPE` maps to `FUNC_NAME_*`. The builder validates the mode against ref data | New modes are a class plus a row. Each mode carries its own flat/veto contract test. Removes the hard-coded tuple and the `"AND"` defaults | Larger. Not needed to fix B1 |

### Recommended fix

1. **Now: merge #76** after the rebase and the test gaps above. It is the root-cause fix for B1.
2. **Before #76 ships to production: decide on live AND deployments.** List the deployments whose strategy `CONFIG_JSON` has `conjunction = 'AND'` with 2+ factors, or `'FILTER'` with 3+. Either pause them until they are re-run, or accept the change with a note on each. Read-only query; no data change in this PR.
3. **Follow-up (already planned by Alfred): flag, do not re-run.**
   - Add `BT.RESULT_FLAG (RESULT_ID, FLAG_CD, NOTE, USER_ID, CREATED_AT)` and a catalog `REFDATA.RESULT_FLAG_TYPE` with a row such as `B1_AND_AS_OR`. A table rather than a column keeps one result able to carry several flags as later engine fixes land.
   - Stamp each new result with the build that produced it: `BT.RESULT.ENGINE_BUILD`, filled by the worker from the image's git SHA passed in at build time. No constant in code. The flag job for B1 then matches on the strategy's conjunction and factor count plus "built before the #76 merge SHA", instead of a date.
   - Promotion: `evaluate.py` refuses to compare a new result with a flagged one and says so in the promotion row. The jobs table and promotion view show the flag.
4. **Later: combiner registry (A3)**, done together with the strategy builder in B, since the builder is where the mode is validated against `REFDATA.CONJUNCTION`.

**Survives:** new coin, hourly bars, new indicator (the combiner only sees positions). With A2, any later engine change that shifts results. With A3, a new conjunction mode and a new entry point (the builder validates the mode everywhere). **A1 alone fails on:** the next promotion run for any AND lineage, the next live apply of an AND deployment, and the next engine change that also needs its old results found.

**Data and migration:** none for #76. Follow-up: one BT release (`RESULT_FLAG`, `ENGINE_BUILD`), one REFDATA release (`RESULT_FLAG_TYPE` rows), a Docker build argument for the SHA.

**Tests:** #76 as above. Flag follow-up: the flag query marks a pre-fix AND result and a pre-fix 3-factor FILTER result, and leaves OR and 2-factor FILTER alone. Promotion refuses a flagged comparison. The worker stamps `ENGINE_BUILD`.

**Size:** #76 16 lines. Flag follow-up ~120–200 including SQL and UI. Registry ~60–90.

**Decision needed from Alfred:** (1) Merge #76 once rebased and the four extra tests are in? (2) Before it ships, pause live AND / 3+-factor FILTER deployments, or let them change on the next apply? (3) For the flag follow-up: `BT.RESULT_FLAG` table plus an `ENGINE_BUILD` stamp from the image SHA, or a date cut only? (4) For a strict `{+1, −1}` conflict with no flat factor, keep the strength tie-break, or make AND go flat? #76 keeps the tie-break. Long-only pairs never hit this row.

## B. Window and signal range bounds

### Verified problem

- `RangeParam` (`quant/schemas/backtest.py` line 5) is `min`, `max`, `step` floats with no checks. It is used for both `window_range` and `signal_range`.
- `to_values(as_int=True)` (line 10) is `range(int(min), int(max) + 1, int(step))`. A window step of 0.5 truncates to 0 and `range` raises, so "step > 0" is not enough for windows. The window range has to be integers.
- **Ran**, per indicator, 200 synthetic bars:

| Window | SMA | EMA | RSI | Bollinger | Stochastic |
|---|---|---|---|---|---|
| 0 | all NaN | **raises** (`span >= 1`) | all NaN | all NaN | all NaN |
| 1 | the raw series | the raw series | 0 or 100 only | **all NaN** (std of one value) | valid only when high ≠ low |
| 2 | valid | valid | valid | valid | valid |

  So the true minimum differs by indicator. Alfred approved 2. That is right for every indicator seeded today, and a future indicator (a MACD pair, ATR, a Donchian channel) may need a different floor.
- `REFDATA.INDICATOR.WIN_MIN` (`db/liquidbase/refdata/tables/INDICATOR.sql`) is the drawer's grid default, not a minimum (decisions #67 and #85). Seeded 5 or 10. Nothing in the DB holds a minimum today.
- **Entry points (Read).**
  - Sync API: `quant/api/routers/backtest.py` → `run_optimize` / `run_performance` / `run_walk_forward` → `build_config`.
  - Queue: `JobsService.enqueue` (`quant/api/services/jobs.py` line 112) stores `config_json` as a plain dict (`quant/api/schemas/jobs.py` line 26) through `sp_ins_strategy` (line 119) with no validation. The worker validates later (`quant/queue/worker.py` line 124), after the strategy version exists.
  - Live: `live_service._resolve_config_and_params` runs `OptimizeRequest.model_validate` on the **stored** `CONFIG_JSON` (line 53), then `build_config`.
  - CLI: `quant/cli.py` has its own `INDICATORS` / `STRATEGIES` dicts (lines 66–76) and builds windows straight from `--win-min` (lines 211, 247). No schema, no ref data.

### PR #75, assessed

Closed. It added `step > 0` and `max >= min` to `RangeParam`, and a floor of 2 on `FactorConfig.window_range` in the schema (14 lines). It cites "decision #91", which is not in `docs/decisions.md` on `main` (the last entry is #90).

- The 2 is a literal in the schema (rule 3).
- **It would break live trading.** Live re-validates the stored `CONFIG_JSON` with `OptimizeRequest`. The B23 jobs (for example `63dac35d`, Raw) searched windows 0–160. Any deployed strategy saved with a range starting below 2 would fail to load on its next apply, although the window it trades is valid. Rewriting stored `CONFIG_JSON` would go against decision #67.
- It does not reach the CLI, and it does not stop the enqueue path from creating a version before the worker rejects the job.

### Where validation belongs

- **Shape invariants stay in the schema.** `step > 0`, `max >= min`, and integer windows need no ref data and hold for every indicator forever. Split `RangeParam` into `WindowRange` (int fields) and `SignalRange` (float fields). Pydantic rejects 2.5 for an int field and still accepts 2.0.
- **Ref-data bounds go in the strategy builder.** The minimum window depends on the indicator. The builder already reads `REFDATA.INDICATOR` to resolve the signal function, so reading the floor there adds no coupling. The schema layer stays free of any DB handle.
- **Search bounds and chosen parameters are different checks.** A search entry point (sync optimize, walk-forward, enqueue, worker) checks the grid against the floor. Performance and live check only the windows actually used. Live never re-checks a stored grid, so old strategies keep loading while every new grid is held to the floor.

### Options

| Option | What | Fails on |
|---|---|---|
| B1. Schema literal (#75) | `ge=2` on `window_range` | Rule 3. Breaks live loads of stored configs. Misses CLI and enqueue. A new indicator needing 3 needs a code change |
| B2. Global CONFIG row | One `MIN_WINDOW = 2` row, a `RedisRefData` getter, checks at each entry point (the 45–70 line estimate) | One number for all indicators. Checks repeated at each entry point unless one owner does them |
| B3. Per-indicator floor, one builder (recommended) | `REFDATA.INDICATOR.WIN_FLOOR`, read by the strategy builder, which every entry point calls | Larger. Needs the CLI to read ref data or be retired |

### Recommended fix

- **Data:** REFDATA Liquibase release adding `WIN_FLOOR INTEGER NOT NULL` to `REFDATA.INDICATOR`, seeded 2 for all five indicators (Alfred's number). It lives on the indicator row because it is a fact about the indicator's math, next to `IS_BOUNDED_IND`. The floor counts bars, so it does not scale with interval. Decision #67 scales the grid defaults (`WIN_*`), not the floor.
- **Ref data read:** `RedisRefData.get_indicator_defaults` (`quant/refdata/reader.py` line 97) is replaced by `get_indicator_specs` returning a typed `IndicatorSpec` (method name, bounded flag, floor, grid defaults). Callers updated. No second getter kept.
- **Owner:** the [strategy builder](#shared-owner-the-strategy-builder). `build_grid(req)` rejects any window below the indicator's `WIN_FLOOR`, with a 422 that names the indicator and the floor. `validate_params(windows, signals)` does the same for chosen parameters.
- **Entry points, all updated in the same change:** sync routes and worker through `run_*`; `JobsService.enqueue` validates `config_json` as an `OptimizeRequest` and runs `build_grid` **before** `sp_ins_strategy`, so a bad range never becomes a version; live calls `validate_params` only; the drawer reads `win_floor` from `/api/v1/refdata/indicator` for the input minimum and drops its `?? 5` literal (`ConfigDrawer.tsx` line 158); the CLI either builds through the builder with `RedisRefData`, or is retired (decision below).
- **Optional, same column pattern:** `SIG_FLOOR` / `SIG_CEIL` for bounded indicators (RSI and stochastic thresholds only make sense between 50 and 100, because the lower band is `100 - signal`). Only if Alfred wants it now.
- **B23 sampling** belongs with item D (the search), not here. The grid size is known once `build_grid` has run, so D's CONFIG limit is checked in the same builder call.

**Survives:** a new indicator (one row with its own floor), hourly bars (floor in bars), a new coin (independent), a new entry point (it calls the builder), a DB change to the floor (no deploy). **B1 and B2 fail on:** a new indicator with a different floor, every live strategy with an old range (B1), and the CLI.

**Tests:**

- Fails on `main`: a Bollinger `window_range` 1–10 is accepted by `build_grid` today. With the fix it is a 422 naming `WIN_FLOOR = 2`.
- Edge cases: window step 0.5 rejected by the schema; `max < min`; negative window; a floor of 3 set on one indicator only is enforced for that indicator only; a stored `CONFIG_JSON` with range 0–160 still loads in live when its chosen window is valid; enqueue with a bad range creates no strategy row; CLI path.
- Suite plus ruff plus mypy. No before/after backtest: valid grids score the same.

**Size:** ~120–180 real lines (builder checks ~50–80, schema split ~15, reader ~15, enqueue ~15, CLI ~20, drawer ~10), ~20 SQL, ~100 test lines.

**Decision needed from Alfred:** (1) Per-indicator `WIN_FLOOR` on `REFDATA.INDICATOR` (all 2 today), or one global CONFIG number? (2) The CLI: route it through the builder with ref data, or retire it? (3) Add `SIG_FLOOR` / `SIG_CEIL` now or later?

## C. B26: data_column is not validated

### Verified problem

- `FactorConfig.data_column: str = "price"` (`quant/schemas/backtest.py` line 32) is a free string.
- One-factor same-coin runs skip the lookup when the name is not a column: `Performance._compute_single_factor_outputs` (`performance.py` line 196) and `SingleFactorObjective.__init__` (`objective.py` line 127) both test `sub.data_column in source.columns`. On a miss they keep the pre-filled `factor` column, which is the close.
- Multi-factor and cross-coin runs index `sub_df[sub.data_column]` (`performance.py` line 174, `objective.py` line 101) and raise `KeyError`, which the sync routes turn into a 400 with body `'volume'`.
- **Ran:** one-factor SMA with `data_column = "volume"` on a frame with `Volume` gives an indicator equal to the SMA of the close. Two factors with `"volume"` raise `KeyError: 'volume'`.
- **Duplicated logic:** `_factor_series_for_sub` and `_validate_factor_coverage` exist in both `Performance` (lines 168, 251) and `Objective` (lines 95, 103), with the same 80% rule.
- **The valid list is already in the DB. Read.** `REFDATA.DATA_COLUMN` has `price_close → price` and `volume → Volume`. The publisher copies every REFDATA table to Redis, and the drawer's `FactorCard` offers exactly those `COLUMN_NAME` values. The backend never reads the table. So the web app is safe, and any API or queue caller can send anything.
- **Defaults that only work because of the silent skip:** `SubStrategy.data_column = "v"` (`signals.py` line 34), `StrategyConfig.single(..., data_column="v")` (line 57), `strategy_to_json` writes `"v"` (line 355), `config_from_json` defaults to `"v"` (line 399), and `get_substrategies` makes up `"factor"` (line 92). No frame has a `v` column. Every one of those configs scores the close by accident today.

### PRs and proposals, assessed

- **#74 (closed, 18 lines).** Makes both `_factor_series_for_sub` reject an unknown name and removes the one-factor skip. Right direction. It keeps both copies of the lookup, checks only against the loaded frame (after the fetch, and after enqueue has already made a version), and leaves `StrategyConfig.single` defaulting to `"v"`, which now errors, with callers patched to pass `"price"`.
- **`SubStrategy.series()` (22 lines, proposed by the Coordinator, not in any PR).** Puts the lookup on the data model and removes the one-factor branches. Better ownership than #74. It still validates against `frame.columns` only, so a request is accepted and fails later, and the web app and the backend keep separate ideas of what a valid column is.

**Root cause:** there is no single owner that turns a factor's `data_column` into a series. Two classes each do it, with a fallback. The request is never checked against the catalog the DB already has.

### Recommended fix

- **Request time, in the [strategy builder](#shared-owner-the-strategy-builder):** `data_column` must equal a `REFDATA.DATA_COLUMN.COLUMN_NAME`. Otherwise 422 listing the valid names. No case folding, which would be a fallback. No migration: the table and its rows exist.
- **Run time, one resolver:** a `FactorInput` class in `quant/strategy` (or `SubStrategy.series(frames, main_index)`, if Alfred prefers it on the data model) owns: pick the factor's frame by cusip, check coverage (the 80% rule, once), check the column is on that frame, and return the aligned series. A catalog column can still be missing from a given source (a provider without volume), so the run-time check stays, and it raises. `Performance` and `Objective` both call it. Their two `_factor_series_for_sub` and `_validate_factor_coverage` copies and the one-factor `in source.columns` branches are deleted.
- **Remove the `"v"`/`"factor"` defaults.** `data_column` becomes required on `SubStrategy` and `StrategyConfig.single`. Every caller and test passes a real column.
- **The legacy strategy-JSON path.** `live_service` still accepts a stored `CONFIG_JSON` without `factors` through `config_from_json` (line 67), and those configs say `"v"`. Before this change, run a read-only count of `BT.STRATEGY` rows without `factors`. If zero, delete `config_from_json`, `strategy_to_json` and `params_from_strategy_json` in the same change. If not zero, Alfred decides whether to migrate those rows once.

**B26's wider limit (volume as one raw column).** OBV, VWAP, dollar volume and volume z-scores need derived series. The resolver is the place they plug in. Later, `REFDATA.DATA_COLUMN` gains a kind (`RAW` or `DERIVED`) and a method name, and `FactorInput` computes a derived series from the factor's own frame. Callers do not change. The same resolver can hand an indicator the factor's own High/Low/Close, which is the fix direction for B3/B4 (stochastic reads the traded coin's columns). Not built in this item.

**Survives:** a new data column or data source (a row, plus the loader producing the column), a new coin or cross-coin factor (one resolver), hourly bars (independent), a new entry point (the builder validates), derived series later (the resolver). **#74 alone fails on:** the next API caller who sends a typo (it is accepted and fails in the worker after a version exists), and on keeping two lookups in step. **`frame.columns` only fails on:** the web app and the backend disagreeing on valid names.

**Tests:**

- Fails on `main`: one-factor same-coin `data_column = "volume"` scores the close. With the fix it is a 422 naming `price` and `Volume`.
- Edge cases: multi-factor bad name gives the same 422, not `KeyError`; a catalog column missing from the source frame raises at run time with the source named; cross-coin coverage below 80% raises once, from the resolver; `price` and `Volume` score the same as today; `StrategyConfig.single` without `data_column` fails type checking.
- Before/after on one valid single-factor and one valid multi-factor config: identical Sharpe. Only runs that sent a bad name change, from scoring the close to a 422.

**Size:** ~60–100 real lines, plus tests. No migration unless legacy strategy-JSON rows exist.

**Decision needed from Alfred:** (1) Validate against `REFDATA.DATA_COLUMN` in the builder (recommended), or check the frame only? (2) The resolver as a `FactorInput` class, or as `SubStrategy.series()`? (3) If the count finds legacy `CONFIG_JSON` rows without `factors`: migrate them once, or retire them?

## D. Repeated cells in top10 and the trial budget

### Verified problem

- `run_optimize` calls `opt.run(window_list, signal_list)` with no `n_trials` (`backtest_service.py` line 565).
- `_select_search` (`quant/strategy/optimizer.py` line 320) sets `n_trials = min(total, OPTUNA_MAX_TRIALS)` (10,000, line 28). Any grid above that goes to `BayesianSearch`.
- `BayesianSearch.search` (line 247) runs `study.optimize(..., n_trials=n_trials)` with `TPESampler(seed=OPTUNA_SEED)` (42, line 29). `suggest_and_evaluate` (line 260) calls `trial.suggest_categorical(k, space.mapping[k])` per axis and scores whatever comes back.
- Nothing checks whether that exact cell was already scored. TPE samples each axis from what scored well, so once it has a good cell it proposes it again. Each repeat is scored again (the objective is deterministic, so the Sharpe is identical), counts toward `n_trials`, and becomes its own row in `_rows_from_study` (line 327). `grid`, `n_valid` and `total_trials` (`backtest_service.py` line 591) all count repeats. `top10` in `_build_result` (line 339) can be the same cell ten times.
- **No rounding. Read.** Parameters are categorical choices from the exact grid lists (`SearchSpace.single` / `multi`, lines 126–146). TPE returns one of those values as is, never a value snapped to a step. Signal values do carry float noise from `np.arange` (`RangeParam.to_values`), for example `0.052000000000000005`, but a repeat returns the identical list element, so the noise does not cause repeats.
- **Ran** with seed 42 on 500 synthetic bars, one Bollinger factor:
  - 25-cell grid with a 20-trial budget: **14 distinct cells** for 20 trials, and **6 distinct cells** in `top10`.
  - 150,300-cell grid with a 3,000-trial budget: **2,954 distinct cells**, 8 distinct in `top10`.
- **Raw** (round 3–4 review, stored job `63dac35d`, not re-read today): 10,000 trials covered 9,655 distinct cells, and `top10` was one cell ten times.
- Walk-forward's in-sample search uses the same `ParametersOptimization`, so it has the same repeats.
- The drawer keeps its own copy of the budget (`ConfigDrawer.tsx` line 241, `OPTUNA_MAX_TRIALS = 10_000`).

### PR #71, assessed

It removes repeated cells in `_build_result` before the top-10 cut (3 lines). `grid` and `n_valid` still count repeats. The budget is still spent on repeats: in the 25-cell run, 6 of 20 trials bought nothing. Its test gives one cell two different Sharpes, which the deterministic objective cannot produce. Alfred rejected it as symptom-only. Once the search stops producing repeats, this dedupe has nothing to remove and would be leftover fallback code (rule 2). It should not merge.

### Options

| Option | What | Pros | Cons |
|---|---|---|---|
| D1. Dedupe the output (#71) | Drop repeats in `_build_result` | 3 lines | Budget still wasted. Counts still wrong. Symptom only |
| D2. Distinct budget in the search (recommended) | Replace `study.optimize` with an ask/tell loop. Key each proposal by its parameter tuple. A repeat is told its stored value (TPE's model sees the real score, as it does today) but is not re-scored, not counted, and not a row. Stop at N distinct cells, or when an attempt cap is reached, or when the grid is used up | Fixes the cause. The budget buys N distinct cells. `top10`, `grid` and `n_valid` are right with no dedupe. Also saves the compute spent on repeats | Needs an attempt cap so a converged TPE cannot loop forever |
| D3. Change the sampler | Seeded uniform sample of N distinct cells, drawn without replacement from the grid index (optuna has no non-repeating categorical sampler; `BruteForceSampler` is exhaustive) | No repeats by construction. The sample is unbiased and easy to explain ("N random cells of M") | Loses TPE's focus on good regions. Research may prefer it, since a focused search overfits more |
| D4. Label only | Store `search`, `grid_size`, `distinct_cells` on the result (B23 item 2) | Honest reporting | Does not stop the waste. Needed anyway alongside D2 or D3 |

### Recommended fix

D2 plus D4, with the numbers in the DB.

- **Owner:** `quant/strategy/optimizer.py`. `BayesianSearch.search` becomes the ask/tell loop over distinct cells. `SearchStrategy` returns the study plus a `SearchReport` (`search`, `grid_size`, `distinct_cells`, `attempts`). `_rows_from_study` emits one row per distinct cell, taken from the completed trials not tagged as a repeat. `_build_result` stays as it is on `main`, with no dedupe.
- **No hard-coded values:** a CONFIG Liquibase release with a `CONFIG.BACKTEST_SEARCH` policy row: `TRIAL_BUDGET` (10,000), `SEED` (42), `MAX_ATTEMPTS_FACTOR` (for example 3 × budget), `OVER_BUDGET_MODE` (`TPE_DISTINCT`, `RANDOM_DISTINCT` or `REJECT`). Read through a `RedisRefData` getter and passed into `ParametersOptimization` by the caller. `OPTUNA_MAX_TRIALS` and `OPTUNA_SEED` are deleted. The drawer reads the same row through `/api/v1/config/backtest_search` and drops its constant.
- **Result and stored job:** `OptimizeResponse` gains `search`, `grid_size`, `distinct_cells`. `total_trials` is replaced by `distinct_cells` (no alias), and the frontend is updated in the same change. The results chip reads "9,655 of 131,769 cells, TPE sample" instead of "valid trials". The grid-size check runs in the [strategy builder](#shared-owner-the-strategy-builder) before any data fetch, so `REJECT` is a 422 before a version exists.
- **Grid values:** generate signal values from integer indices (`min + i * step`, rounded to the step's decimals) so a cell key is exact and stored parameters read cleanly. This goes with B's `SignalRange`.

**Survives:** larger grids and more factors (the budget buys distinct cells), hourly bars and more windows (same), a policy change to budget, seed or mode (a DB row, no deploy), a sampler change later (`OVER_BUDGET_MODE` picks the `SearchStrategy`), a new entry point (the policy is read in one place). **D1 fails on:** every sampled run still wasting budget, and `n_valid`, `grid` and the stored job still counting repeats as tested cells.

**Tests:**

- Fails on `main`: 25-cell grid, budget 20, seed 42. Assert 20 distinct cells and 20 objective calls. `main` gives 14 distinct (Ran).
- Edge cases: budget ≥ grid stays exhaustive; budget = grid − 1 stops at the budget; the attempt cap is hit and the report says `distinct_cells < budget`; multi-factor keys; same seed, same result; `top10` distinct with no dedupe code; `grid` and `n_valid` count distinct cells; `REJECT` mode gives a 422 at the builder; walk-forward in-sample uses the same loop.
- Before/after: one stored-size grid (for example 33 × 11 × 33 × 11) before and after. Best may change, because the budget now covers more cells. Record both.

**Size:** ~60–90 real lines in `optimizer.py`, ~20 SQL, ~10 reader, ~15 schema, ~20 frontend, plus tests.

**Decision needed from Alfred:** (1) Over-budget grids: TPE over distinct cells, a seeded random sample of distinct cells, or refuse the grid? (2) Move budget, seed and attempt cap to a `CONFIG.BACKTEST_SEARCH` row? (3) Close #71 rather than merge it?

### Shipped (decision #91)

D2 plus D4 are in `quant/strategy/optimizer.py`. The seeded mode is `TPE_DISTINCT`. `RANDOM_DISTINCT` and `REJECT` are the other values of `OVER_BUDGET_MODE`, so switching is a row change. `OPTUNA_MAX_TRIALS`, `OPTUNA_SEED`, the `n_trials` argument, and `total_trials` are gone. The drawer reads `GET /api/v1/config/backtest_search`. The results chip reads `{distinct_cells} of {grid_size} cells, {search}`.

Checked against current `main` before the change: seed 42, 500 bars, windows `(5, 10, 15, 20, 25)`, signals `(0.5, 1.0, 1.5, 2.0, 2.5)`, `n_trials=20` wrote **20 rows, 15 distinct cells, 20 objective calls**, and **7 distinct cells in `top10`**. The "14" in the Ran note above was a different series. The test asserts 20 distinct cells and 20 objective calls.

Not built, because the code has no owner for them and this change does not add one:

- `StrategyBuilder`. `REJECT` is raised by the search after the series is loaded, and `backtest_service` maps it to HTTP 422. Enqueue still creates a strategy version.
- Signal values generated from integer indices. That belongs with item B's `SignalRange`.
- Items A, B, and C.

## Shared owner: the strategy builder

Items A (conjunction), B (window floor), C (data column) and D (grid size) all ask one question: is this request a valid strategy, according to ref data? Today the answer is spread across `build_config`, `_build_param_ranges`, `resolve_signal_func`, a hard-coded tuple in `combine_positions`, and nothing at all at enqueue or in the CLI.

Proposal: one `StrategyBuilder` in `quant/strategy`, built from a `RedisRefData`, that replaces those free functions (no wrappers left behind):

- `build(req) -> BuiltStrategy(config, grid)`: resolves signal functions from `REFDATA.INDICATOR` and `REFDATA.SIGNAL_TYPE`, checks the conjunction against `REFDATA.CONJUNCTION`, checks `data_column` against `REFDATA.DATA_COLUMN`, checks windows against `WIN_FLOOR`, and checks the grid size against `CONFIG.BACKTEST_SEARCH`.
- `validate_params(config, windows, signals)`: for performance and live, which trade chosen parameters rather than a grid.

Callers updated in the same change: `run_optimize`, `run_performance`, `run_walk_forward`, `JobsService.enqueue` (before `sp_ins_strategy`), the worker, `live_service`, and the CLI (or its retirement). The API layer already depends on `quant/strategy`, and `build_config` already takes the ref-data cache, so this adds no new coupling. Request schemas keep shape rules only.

Order: #76 (A) can merge first on its own. The builder then lands with C (smallest), and B and D add their checks to it.

**Decision needed from Alfred:** adopt one `StrategyBuilder` as the owner of ref-data validation for every entry point, or keep the per-item fixes separate?

## Not checked

- Production data: how many stored AND results, live AND deployments, or legacy `CONFIG_JSON` rows exist. Each needs a read-only query first.
- #76's reported test counts and ETH before/after were not re-run here.
- The 9,655 distinct cells figure for `63dac35d` is from the round 3–4 review's stored rows, not re-read today.
