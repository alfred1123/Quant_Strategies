# AlgoDaemon bug report — 2026-09-27

**Doc type:** platform review. Documentation of bugs found by black-box API testing. This page does not change the engine.
**Status:** open findings, checked against `main` at `9c1af3619` (2026-09-26).
**Source dossier:** compiled 2026-09-27 00:10 HKT from API runs plus a code snapshot dated 2026-09-25. Evidence files it cites (`raw/`, `round2/`, `backfill/`, `round3/raw/`) live on another machine and were not re-read here. Live `algodaemon.com` was not called again.

Bar times below are UTC. Clock times from the dossier are HKT.

How a row was checked:

| Mark | Meaning |
|---|---|
| Ran | Reproduced on synthetic data with the current engine. The production job ids and their stored numbers are still the dossier's. |
| Read | The cause is in the current source. Line numbers are `main` at `9c1af3619`. |
| Git | The named commit is an ancestor of this `main`, and the diff matches the claim. |
| Dossier | Reported by the research agent. Not re-measured here. |

Where [Backtest review (2026-09-25)](2026-09-25-backtest-review.md) (PR #58) or [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md) (PR #59) already analyses an item, this page links there and keeps the repro, the current lines, and the status.

## Summary

Twenty-one items, B1–B21. Six are high severity. Of those, B7 is fixed on `main`. B2's split label and B6's refusal of a new short sample are fixed; the walk-forward restart and the stored Best row are not. B1, B3, B4, and B5 are open. B1 is the one that rewrites research conclusions: with the strengths the performance and optimize paths always pass, a long-only AND is an OR, and a FILTER of three or more factors has the same hole in its direction factors.

Two status calls differ from the dossier. B14's six `queue_pos: 1` responses match an idle worker claiming each job before the next enqueue; the ranking code on `main` does order two jobs that are still queued. B11's Best flag on a running VID 1 is the insert [Best-VID promotion](best-vid-promotion.md) already specifies; what is open is the label, as with B10.

## Status

| B# | Title | Severity | Status | Verified |
|---|---|---|---|---|
| [B1](#b1-two-factor-and-behaves-like-or-for-long-only-factors) | Two-factor AND behaves like OR for long-only factors; FILTER with 3+ factors has the same flaw | High | Open | Ran |
| [B2](#b2-walk-forward-oos-restarts-the-indicator) | Walk-forward OOS restarts the indicator; the split date was reported one warmup late | High | Label fixed on main. OOS restart open. Covered by PR #58 items 1 and 7 | Ran (restart). Git (label) |
| [B3](#b3-stochastic-in-a-multi-factor-run-fails-on-high) | Stochastic in any multi-factor run fails with HTTP 400 `'High'` | High | Open | Ran |
| [B4](#b4-cross-coin-stochastic-uses-the-traded-coins-hlc) | Cross-coin stochastic uses the traded coin's own High/Low/Close | High | Open. Same root noted in PR #58 item 2 | Ran |
| [B5](#b5-promotion-compares-sharpe-across-different-date-ranges) | Promotion compares Sharpe across versions with different date ranges | High | Open. PR #59 records the range as a version attribute and proposes no comparison rule | Read. Live rows: dossier |
| [B6](#b6-a-short-sample-volume-filter-is-still-best) | Volume-filter job: windows up to 2330 on 2354 bars, 24 scored bars, Sharpe 5.07 still Best | High | New runs fixed on main (decision #82). Stored row still Best. Covered by PR #59 | Ran (gate). Stored row: dossier |
| [B7](#b7-a-single-factor-volume-run-used-price) | Single-factor Volume run silently used price | High | Fixed on main. PR #58 item 2 | Ran (the fix). Old rows: dossier |
| [B8](#b8-stored-metrics-from-before-geometric-returns) | Stored metrics from before the geometric-return switch are stale | Medium | Covered by PR #59. Not an engine bug | Read. The re-run numbers: dossier |
| [B9](#b9-backfill-plan-never-completes-past-the-venues-first-bar) | Price-bar backfill plan never completes when the venue has no bars at the start of "wanted from" | Medium | Open | Ran |
| [B10](#b10-vid-1-is-logged-kept-with-no-comparison) | A new lineage's VID 1 is logged KEPT with no comparison, yet it is Best | Medium | Open as a label. The flag is by design (decision #63, PR #59) | Read. The three jobs: dossier |
| [B11](#b11-a-running-job-shows-vid-and-best) | A job shows its VID and Best = Y while still RUNNING | Medium | Open as a label. The insert is by design | Read. The running snapshot: dossier |
| [B12](#b12-my-jobs-listed-the-oldest-50) | `GET /backtest/jobs` returned the oldest 50 jobs | Medium | Fixed on main. The 50-row cap remains | Git + read. Live list: dossier |
| [B13](#b13-strategy-identity-includes-the-interval) | Strategy identity is keyed on the name, so another timeframe starts a new lineage | Medium | By design (decision #58). `RECIPE_KEY` in PR #59 is not adopted | Read |
| [B14](#b14-enqueue-reported-queue-position-1) | Every enqueue returned `queue_pos: 1`; `queue_vid` is not a position | Low | Ranking on main orders jobs that are still queued. The measured 1s were not shown to be wrong | Read + ran (ranking). The six responses: dossier |
| [B15](#b15-the-first-entry-is-not-charged-a-fee) | First entry (and re-entry after a NaN gap) is not charged a fee | Low | By design. PR #58 item 5 | Ran |
| [B16](#b16-smaema-momentum-on-raw-price-is-buy-and-hold) | SMA/EMA momentum on raw price is always long | Low | Open. Covered by PR #58 item 6 | Ran |
| [B17](#b17-hourly-rsi-grids-are-mostly-empty) | Hourly RSI grids are mostly empty (NaN Sharpe) | Low | Open | Ran (same grid, synthetic prices). BTC counts: dossier |
| [B18](#b18-a-signal-type-reached-the-database-before-the-worker) | A job failed because a new signal type reached the database before the code | Low | That method exists now. The deploy-order gap is open | Read. The failed job: dossier |
| [B19](#b19-api-docs-urls-serve-the-website) | `/docs`, `/redoc`, `/openapi.json` return the website | Low | Docs disabled in prod by design. The SPA 200 is the residual | Read. The GETs: dossier |
| [B20](#b20-backfill-is-capped-at-10000-bars) | Backfill capped at 10,000 bars per request | Low | By design | Read |
| [B21](#b21-synchronous-optimize-timed-out-at-the-edge) | Synchronous optimize of about 968 trials returned a Cloudflare 524 | Low | Open. No application limit on the sync route | Read. The 524: dossier |

## B1. Two-factor AND behaves like OR for long-only factors

**Status:** open. **Severity:** high. **Effort:** small.

Not in PR #58 or #59. `f9cb8468e` changed only how `_conviction` ranks bars. The disagree mask is unchanged.

**Repro (dossier).** `POST /api/v1/backtest/performance` on ETH (`ethusdt.crypto`), daily, 2021-07-01 to 2026-09-23, `fee_bps` 10, Bybit. Factor 1: BTC `get_bollinger_band` / `momentum_long`, window 85, signal 1.0. Factor 2: ETH `get_rsi` / `momentum_long`, window 14, signal 55. Repeated for AND, OR, and FILTER. Files: `round2/raw/performance_conjtest_{AND,OR,FILTER}_ETH_FULL_f10_*.json`.

**Expected.** AND is long only when both factors are long.

**Actual (dossier).** AND and OR match on every metric and every `FinalPosition`: Sharpe 0.7547, total return 2.3873, annual return 0.2762, MDD 0.4731, n_obs 1826. Of 1,827 bars, AND is long on all 184 bars where only factor 1 is long and all 323 where only factor 2 is long. Both long: 376 bars, which is the FILTER result (Sharpe 0.8453, MDD 0.2865). AND is long on 883 bars.

**Confirmed by running.** A 500-bar synthetic book, Bollinger `momentum_band_signal_long_only` against RSI `momentum_bounded_signal_long_only`, through `Performance` (the path that passes indicator strengths):

- AND and OR produced the same Sharpe (−0.1842) and the same positions.
- On 212 bars where exactly one factor was long, AND was long on all 212.
- Both long on 22 bars. FILTER was long on those 22 and nowhere else.
- The same positions combined with `strengths=None` were long on 22 bars. That is the AND the docstring describes. The performance and optimize paths do not use it.

FILTER with three factors, same series: on 15 bars the gate was on and exactly one of the two direction factors was long, the combined position was long on all 15. Two-factor FILTER does not do this. The drawer still stops at two factors (`frontend/src/components/ConfigDrawer.tsx` line 193), so three factors are reached through the API. `684e289e7` turned Add Factor back on and left that cap in place.

**Cause.** Confirmed in `quant/strategy/signals.py`.

- `_combine_and` (lines 154–166) treats any row that is not unanimous and has some signal as a disagreement. `{+1, 0}` qualifies.
- `_strongest_sign` (lines 122–128) masks flat factors to −inf and returns the sign of the only non-flat factor, so the row becomes +1.
- `_combine_filter` (lines 136–150) returns the second factor when there are exactly two. With three or more, lines 139–149 apply the same mask to the direction factors.
- `Performance._compute_multi_factor_outputs` (`quant/strategy/performance.py` lines 226–229) and `MultiFactorObjective.__call__` (`quant/strategy/objective.py` lines 163–165) always pass strengths.

`tests/unit/test_strat.py` `test_and_strength_ignores_flat_factors` (lines 545–555) asserts this outcome. The public text on `combine_positions` (lines 191–194) still says AND is a position only when all factors agree. The test and that sentence disagree. A fix has to change the test.

**Fix direction.** Treat a row as a conflict only when both +1 and −1 are present. A flat factor stays a veto for AND, and for a FILTER with three or more factors a flat direction factor stays flat. `{+1, −1}` can still go to the stronger reading. Recompute stored AND results that used long-only factors; they are OR results.

## B2. Walk-forward OOS restarts the indicator

**Status:** the split label is fixed on main. The out-of-sample restart is open. **Severity:** high. **Effort:** medium for the restart.

PR #58 [item 7](2026-09-25-backtest-review.md#7-the-walk-forward-chart-marks-the-split-one-warmup-late) is the label. [Item 1](2026-09-25-backtest-review.md#1-promotion-trades-the-full-sample-best-sharpe) already notes that the out-of-sample slice is cut with `iloc` and the indicator restarts.

**Repro (dossier).** Daily, 2021-07-01 to 2026-09-23, 1,911 bars.

| Run | Expected split | Reported split | Lag |
|---|---|---|---|
| Sync walk-forward, `split_ratio` 0.6, BTC and BNB, best window 90 | 2024-08-20 | 2024-11-18 | 90 bars |
| Same, ETH, best window 95 | 2024-08-20 | 2024-11-23 | 95 bars |
| Jobs `ad13d108`, `fa4c92dd`, `8acefd92`, window 85, `split_ratio` 0.5 | 2024-02-11 | 2024-05-06 | 85 bars |
| Jobs `e8632145`, `adb36235`, `fbd97675`, window 80 | 2024-02-11 | 2024-05-01 | 80 bars |

An OOS-only performance call with window 90 first scores on 2024-11-19 (n_obs 674). BTC MDD matches the walk-forward OOS exactly (0.3196). Files: `raw/optimize_wf_D_A_narrow_*.json`, `raw/performance_oos2_WFpick_*`. Round-3 jobs `63dac35d` and `666b8aa4` (enqueued 2026-09-26 22:33 HKT) report 2024-02-11, which is the label fix, seen live by the dossier and not re-checked here.

**Confirmed by running.** A 200-bar synthetic series, SMA window 30, `split_ratio` 0.6 (`split_idx` 120, split date 2020-04-30). The indicator on the full series is finite at the split. The out-of-sample `Performance` built the way `WalkForward._evaluate` builds it has 29 leading NaN indicator bars and its first finite value on 2020-05-29. Finite pnl bars from the split: 80 on the full series, 50 on the restarted slice.

**Cause.** `WalkForward.run` (`quant/strategy/walk_forward.py` lines 106–113) passes `df.iloc[self.split_idx:]` into `_evaluate` (lines 149–155), which constructs a new `Performance` on that slice. The rolling window has no in-sample history. The label is now `wf.data.index[wf.split_idx]` (`quant/strategy/backtest_service.py` lines 500–503), committed in `a64c6c07b` (2026-09-25 21:03 HKT). Stored split dates on jobs completed before that commit stay late.

**Fix direction.** Fit parameters on the in-sample slice, as now. Score the hold-out from indicators computed on the unsplit series, then keep pnl from `split_idx` onward. Rolling indicators look backward, so the bar at the split does not need future prices. The overfitting ratio and the hold-out gate in decision #83 both read this truncated sample today.

## B3. Stochastic in a multi-factor run fails on High

**Status:** open. **Severity:** high. **Effort:** small, and it is the same change as B4.

Not in PR #58 or #59.

**Repro (dossier).** BTC daily, 2021-07-01 to 2026-09-23, `fee_bps` 10, FILTER. Factor 1: `get_bollinger_band` / `momentum_long`, window 200, signal 0. Factor 2: `get_stochastic_oscillator` / `momentum_long`, windows 10–20 step 5, signals 60–80 step 10. Both `POST /backtest/optimize` and `POST /backtest/performance` (windows `[200, 10]`, signals `[0, 70]`) returned HTTP 400 `{"detail": "'High'"}`. Files: `raw/optimize_bugT2_stoch_multi_1496fffb0f_ERR.json`, `raw/performance_bugT2_stoch_multi_perf_47388dbbb5_ERR.json`. Single-factor stochastic returns 200 (B4).

**Confirmed by running.** A multi-factor `Performance` whose second factor is `get_stochastic_oscillator` raises `KeyError` whose string is `'High'`. `IndicatorCache`, which the optimizer builds before the per-trial `try`, raises the same `KeyError` on a frame that has only `factor`. The router maps any other exception to HTTP 400 with `detail=str(exc)` (`quant/api/routers/backtest.py` lines 29–32). AND and OR use that same cache and the same `_indicator_and_position`. The dossier measured FILTER only; the other two conjunctions fail in the same function.

**Cause.** `_indicator_and_position` (`quant/strategy/performance.py` lines 183–186) and `MultiFactorObjective` (`quant/strategy/objective.py` lines 151–154) build `DataFrame({"factor": factor_vals})`. `TechnicalAnalysis.get_stochastic_oscillator` (`quant/strategy/indicators.py` lines 54–63) reads `High`, `Low`, and `Close`.

**Fix direction.** Give the stochastic call the High, Low, and Close of the instrument the factor is actually on. Do that in the multi-factor frame and in the single-factor frame (B4), or the multi-factor case starts returning numbers that are still the wrong coin.

## B4. Cross-coin stochastic uses the traded coin's HLC

**Status:** open. **Severity:** high. **Effort:** medium, shared with B3.

PR #58 [item 2](2026-09-25-backtest-review.md#2-a-one-factor-volume-strategy-is-silently-a-price-strategy) notes that stochastic always uses High, Low, and Close. `c35ea23d2` fixed `data_column` for one-factor runs (B7). Stochastic still ignores `factor`.

**Repro (dossier).** `POST /backtest/performance`, trading ETH daily, 2021-07-01 to 2026-09-23, `fee_bps` 10. Single factor `get_stochastic_oscillator` / `momentum_long`, window 10, signal 70. (a) factor symbol `btcusdt.crypto`. (b) ETH's own data. Files: `raw/performance_bugT3_{btc_2bce20edc3,own_c584c8767f}.json`. A Bollinger control with the same shape does differ (`raw/performance_bugT3ctl_*.json`): BTC-factor Sharpe 0.528312 versus own 0.572435.

**Expected.** (a) uses BTC highs, lows, and closes.

**Actual (dossier).** (a) and (b) match: total return 0.875299, annual return 0.128964, Sharpe 0.531529, MDD 0.419201, n_obs 1892. `indicator1` matches bar by bar (13.306519 on 2021-07-19). `factor1` in (a) is the BTC price (30815.5 versus ETH 1818.25), so the request was honoured for the factor column and not for the oscillator.

**Confirmed by running.** On two synthetic coins, a one-factor stochastic whose `internal_cusip` is the other coin produced an indicator identical to the traded coin's own stochastic, while `factor1` differed. The Bollinger control on the same pair differed. There is no error.

**Cause.** `_compute_single_factor_outputs` (`quant/strategy/performance.py` lines 190–206) replaces `data["factor"]` and leaves the traded frame's `High`, `Low`, and `Close`. `get_stochastic_oscillator` reads those three columns and never `factor` or `data_column`. `SingleFactorObjective` (`quant/strategy/objective.py` lines 127–132) does the same replacement before `IndicatorCache`.

**Fix direction.** When the indicator needs a range, pass the factor instrument's High, Low, and Close, including the cross-coin case. A volume stochastic is the same bug in miniature: the review already notes it still scores the price range.

## B5. Promotion compares Sharpe across different date ranges

**Status:** open. **Severity:** high. **Effort:** large. This is a comparison rule, and it wants a decision before code.

PR #59 [How an id is chosen today](2026-09-25-backtest-data-hygiene-proposal.md#how-an-id-is-chosen-today) says `start` and `end` live on the version, so one lineage may mix ranges. It proposes no rule for comparing those versions. Decision #83 (`bb62d6a80`, 2026-09-26 13:40 HKT) adds an out-of-sample Sharpe gate, a Sharpe-versus-buy-and-hold gate, and raises `sharpe_gate` to 1. Release `1.26.0` is in `db/liquidbase/refdata/releases/1.26.0-promotion-holdout-gates.xml` with context `refdata,prod-deploy`. Whether Aurora has applied it was not checked. Those gates still read each version's own window.

**Repro (dossier).** Queued 2026-09-25 05:16 HKT. Sources: `raw/promotions_after_enqueue.json`, `results/queued_jobs_summary.csv`.

| Job | New version | Compared with | Outcome |
|---|---|---|---|
| `ad13d108` BTC, strategy `94910f42`, VID 2, 2021-07-01 to 2026-09-23 | Sharpe 1.0977, MDD 0.2711, n_obs 1826 | VID 1 `8252fe48`, Sharpe 1.4815, 2020-03-25 to 2026-09-12 | `KEPT`, `compared_vid` 1 |
| `8acefd92` BNB, strategy `bd596444`, VID 2 | Sharpe 1.1868 | VID 1 `1d4075eb`, Sharpe 1.2568, 2021-06-30 to 2026-09-12 | `KEPT`, `compared_vid` 1 |

Both cleared the hard gates then in force (`sharpe_gate` 0, `max_dd_gate` 0.4). VID 1 for BTC still carries the pre-cutover buy-and-hold MDD from B8 (1.224 versus VID 2's 0.767).

**Cause.** Confirmed in `quant/promotion/evaluate.py`. `_evaluate_soft` (lines 112–127) compares metric values in priority order. Nothing reads `start` or `end` from `CONFIG_JSON`. `_extract_metric` (lines 49–68) pulls full-sample metrics, and the hold-out and excess keys when those rows exist. A stronger Sharpe on a longer bull window still wins the soft rank.

**Fix direction.** Decide the rule first: compare on the overlapping window, refuse a soft rank when the ranges differ, or show the ranges beside the outcome and keep today's rank. The hold-out gate does not replace that choice. Two versions can have different full samples and different hold-outs.

## B6. A short-sample volume-filter is still Best

**Status:** new runs fail the gate. The stored row is still Best, per the dossier. **Severity:** high for that stored row. **Effort:** small for the leftover stochastic warmup; the stored-row cleanup is the one already written in PR #59.

Covered by PR #59 [Short samples](2026-09-25-backtest-data-hygiene-proposal.md#short-samples). Adopted as [decision #82](../decisions.md). Commit `b23e8d95f` (2026-09-25 20:01 HKT).

**Repro (dossier).** Job `3f6bf5f7-ddf5-4915-a19b-26a2e442a039`, strategy `06006832`, VID 1, created 2026-09-04 16:06 UTC. Both window grids 10–2400 step 20, 2020-03-25 to 2026-09-03, 2,354 daily bars. Best cell: window 2330 / signal 0.5 and window 50 / signal 1.0. 24 finite pnl bars, Sharpe 5.0709, MDD 0.0225, equity from 2026-08-11 to 2026-09-03. Still `is_best_ind: Y` on the dossier's 2026-09-27 GET. v2 (`52d64184`, Sharpe 1.2342) did not displace it. The round-1 text said about 60 bars; the stored result has 24, which matches PR #59.

**Confirmed by running.** `require_scoreable_sample` (`quant/strategy/backtest_service.py` lines 539–556) on 2,354 bars with `window_range.max` 2400 raises `BacktestError`: the grid needs at least 2,460 bars (window 2400 + 60). A stochastic window of 20 on 80 bars passes that gate (`80 >= 20 + 60`) and then scores 42 finite indicator bars, 41 finite pnl bars, and a NaN Sharpe. Decision #82 already leaves stochastic's extra warmup open. `%D` is a rolling mean of `%K` (`quant/strategy/indicators.py` lines 59–62), so the warmup is about two windows.

**Fix direction.** For the stored lineage, follow the PR #59 cleanup: a re-run under the floor stores a null Sharpe and leaves VID 1 as Best, so the row still needs `LOGICAL_DELETE_IND` if it should leave the picker. Extend the gate so a stochastic grid counts about `2W` warmup bars. The drawer warning in that same decision is still unbuilt.

## B7. A single-factor Volume run used price

**Status:** fixed on main. **Severity:** high while it was live. **Effort:** done.

PR #58 [item 2](2026-09-25-backtest-review.md#2-a-one-factor-volume-strategy-is-silently-a-price-strategy). Commit `c35ea23d2` (2026-09-25 20:25 HKT).

**Repro (dossier).** BTC daily, 2021-07-01 to 2026-09-23, `fee_bps` 10, `get_bollinger_band` / `momentum_long`, window 20, signal 1.0. `data_column` price and Volume were identical (total return 0.317579, Sharpe 0.331951, MDD 0.514942, n_obs 1891), and the Volume run's `factor1` held price. The two-factor Volume run did use volume. Files: `raw/performance_bugT1_*.json`.

**Confirmed by running.** On a synthetic frame, a one-factor Bollinger with `data_column="Volume"` now differs from `data_column="price"`, and `factor1` is the volume series. The read is `quant/strategy/performance.py` lines 196–197 and `quant/strategy/objective.py` lines 127–129. Rows stored before the fix still say Volume and score price. Stochastic is B4, not this fix.

## B8. Stored metrics from before geometric returns

**Status:** covered by PR #59. Not an engine bug on current `main`. **Severity:** medium. **Effort:** the replay in that proposal; not done.

PR #59 [Stale stored results](2026-09-25-backtest-data-hygiene-proposal.md#stale-stored-results). The switch is `d1ddb557b` (2026-09-22 17:55 HKT). Current compounding is `_compound` in `quant/strategy/performance.py` lines 57–72.

**Repro (dossier).** BTC v1 job `8252fe48-a90b-4cc3-a72c-f7a4af7915bc`, strategy `94910f42`, VID 1, completed 2026-09-13 23:38 HKT. Same parameters re-run in `raw/performance_repro_btc_d_b31adbe860.json`.

| | Stored | Re-run |
|---|---|---|
| Sharpe | 1.481489 | 1.481489 |
| Annual return | 0.3542 | 0.3855 |
| MDD | 0.2080 | 0.1939 |
| Total return | 2.2398 | 6.8609 |
| Buy-and-hold MDD | 1.2243 | 0.7668 |

n_obs 2308 both. Other pre-cutover rows with buy-and-hold MDD above 1: `64c467ef`, `ac4c4ab7` (1.259), `cc10cae1` (1.448), `669be3e3` (1.36). Those figures were not recomputed here. Sharpe is unchanged, so rank order among long samples is unchanged. The stale returns and drawdowns still feed the comparisons in B5.

**Fix direction.** The census SQL and the replay/flag in PR #59. There is still no engine-version column on the result.

## B9. Backfill plan never completes past the venue's first bar

**Status:** open. **Severity:** medium. **Effort:** medium.

Not in PR #58 or #59. It does not corrupt stored bars. A loop that runs until the plan is complete does not finish, and the UI keeps "1 pass remaining". A backtest that starts on the wanted date can still fail on the hole.

**Repro (dossier).** Hourly backfill, 2026-09-26 20:47–20:54 HKT, after the price-bar truncation in `67ad68d28`. Source: `backfill/fire_hourly_log.json`.

- BTC 1H pass 6 planned 2020-03-25T00:00–09:00Z (10 bars, `passes_remaining` 1), inserted 0, and the next plan offered the same range. First stored bar: 2020-03-25T10:00Z.
- BNB 1H pass 5 planned the 7 hours before 2021-06-29T07:00Z, inserted 0, and the plan repeated.
- ETH 1H completed.
- Jobs `e742e82a`, `81c8b639`, and `41704920` failed because BTC 1H coverage starts at 10:00Z.

**Confirmed by running.** `PriceBarService` with a first stored bar at 2020-03-25T10:00Z, target 2020-03-25T00:00Z, and a fetcher that returns no bars: the plan is 00:00–09:00Z, 10 bars, `passes_remaining` 1. `backfill` inserts 0 and reports 10 unfilled. The next plan is the same range. `plan_backfill` does not call `venue_depth`.

**Cause.** `plan_backfill` (`quant/market_data/service.py` lines 410–426) sets the pass end to `first_bar - period` whenever `first_bar > target`. `backfill` (lines 288–374) returns `unfilled` and does not move `target` or store a "no data before" mark. `venue_depth` (lines 446–474) already asks the venue for its earliest bar and is a separate call.

**Fix direction.** Stop planning earlier than the venue's earliest bar, or persist the unfilled head so the next plan treats it as reached. Report that the venue has no earlier bars, so the dialog can close.

## B10. VID 1 is logged KEPT with no comparison

**Status:** open as a label. The Best flag is by design. **Severity:** medium. **Effort:** small.

PR #59 and [decision #63](../decisions.md) say VID 1 is Best with no opponent. [Best-VID promotion](best-vid-promotion.md) draws that branch as KEEP. The outcome string reuses `KEPT`, which on a later version means "lost the comparison".

**Repro (dossier).** `raw/promotions_after_enqueue.json`, `round2/raw/promotions_after_r2.json`.

| Job | Strategy | Sharpe | Outcome |
|---|---|---|---|
| `fa4c92dd` ETH | `1de0c3b4` VID 1 | 1.0526 | `KEPT`, `compared_vid` null, Best |
| `adb36235` BNB | `5489c9bd` VID 1 | 1.0479 | `KEPT`, `compared_vid` null, still Best in the round-3 snapshot |
| `e8632145` ETH | `1f84c585` VID 1 | 1.1706 | `KEPT`, later superseded by `fbd97675` VID 2 (`PROMOTED`, Sharpe 1.2178) |

**Cause.** `evaluate_promotion` (`quant/promotion/evaluate.py` lines 161–166) returns `KEPT` with `compared_vid` left unset when the candidate is VID 1 and already the current best. The insert that makes it best is B11.

**Fix direction.** A distinct outcome, or the label the promotion panel already uses for a null `compared_vid` ("Baseline VID — no other version to compare"), on the job and the strategies list. Leave the Best flag as decision #63 wrote it.

## B11. A running job shows VID and Best

**Status:** open as a label. The insert is by design. **Severity:** medium. **Effort:** small.

The dossier has no saved RUNNING payload. The completed files show `queue_status` COMPLETED. The round-2 Slack post is the only observation of the running state. The cause is in the code and in [Best-VID promotion](best-vid-promotion.md) (VID 1 starts as Best, and a failed VID 1 stays Best).

**Cause.** `JobService.enqueue` (`quant/api/services/jobs.py` lines 119–123) calls `sp_ins_strategy` before the worker runs. The live procedure is `db/liquidbase/bt/procedures/SP_INS_STRATEGY_VID_BY_NM.sql` lines 95–108: VID 1 is inserted with `IS_BEST_IND = 'Y'`. `SP_INS_STRATEGY.sql` is the frozen pre-1.10 body; the changelog does not apply it. The job read joins that strategy row, so a RUNNING VID 1 already carries the version and the Best flag. If the job then fails, decision #63 keeps that flag.

**Fix direction.** Show Best only after promotion has run, or mark the chip provisional until the job is terminal. That is a display change on the existing job payload. The enqueue insert can stay.

## B12. My Jobs listed the oldest 50

**Status:** fixed on main. **Severity:** medium while it was live. **Effort:** medium if the list should page past 50.

Not in PR #58 or #59. Commit `9c1af3619` (2026-09-26 23:38 HKT, release `bt/1.25.0`).

**Repro (dossier).** `GET /api/v1/backtest/jobs` on 2026-09-25, `raw/jobs_before.json` and `raw/jobs_list_after_enqueue.json`: exactly 50 rows, oldest first, 2026-08-30 through 2026-09-22. Jobs `ad13d108`, `fa4c92dd`, and `8acefd92` were absent. After the fix, the dossier's later GETs are newest first. Not re-fetched here.

**Cause, and the residual.** `BT.SP_GET_QUEUE` now orders active rows by `CREATED_AT DESC` (`db/liquidbase/bt/procedures/SP_GET_QUEUE.sql` line 90). `list_for_user` (`quant/api/services/jobs.py` lines 141–142, `quant/queue/repo.py` lines 161–163) still passes `limit=50`. The procedure's own default is also 50 (line 37). Job `3f6bf5f7` (B6) drops off that window. The worker does not use this order to claim: `in_run_order` puts the lowest priority, then the earliest enqueue, first.

**Fix direction.** Page the list, or raise the cap and say so. The sort itself is done.

## B13. Strategy identity includes the interval

**Status:** by design. **Severity:** medium for the research workflow. **Effort:** large if `RECIPE_KEY` is adopted. That amends decision #58.

[Decision #58](../decisions.md) puts cadence in the name because hourly and daily Sharpe are annualised with different period counts, and one Best per `STRATEGY_ID` would compare them bare. PR #59 [Strategy identity](2026-09-25-backtest-data-hygiene-proposal.md#strategy-identity) proposes `RECIPE_KEY` and a Best scoped per interval. Decision #82 records that proposal as not adopted.

**Cause.** `BT.SP_INS_STRATEGY` resolves `(USER_ID, STRATEGY_NM)`. The name embeds the traded symbol, the interval, and every factor. `JobService._assert_cadence_in_name` (`quant/api/services/jobs.py` lines 94–108) rejects a name whose traded leg does not end with that cadence. A daily Bollinger lineage and its hourly twin are two ids. Best is per name.

**Fix direction.** Leave it until someone adopts the PR #59 key. A display-only grouping in the promotion accordion is the smaller option that proposal already names, and it does not merge versions.

## B14. Enqueue reported queue position 1

**Status:** the ranking on main orders jobs that are still queued. **Severity:** low. **Effort:** small, and only for the residual.

I disagree with reading the six responses as a confirmed defect. Each enqueue returns, then the worker can claim, before the client sends the next job. An idle worker makes every response `queue_pos: 1`. The dossier already allows that. It was not re-measured, because that needs a live enqueue.

**Repro (dossier).** Six `POST /api/v1/backtest/jobs` responses, all `queue_pos: 1`: `ad13d108`, `fa4c92dd`, `8acefd92`, `e8632145`, `adb36235`, `fbd97675`. Files: `raw/enqueue_*.json`, `round2/raw/enqueue_*.json`. Job detail showed `queue_vid: 3`.

**What the code does now.** `9c1af3619` changed `queued_position` (`quant/queue/repo.py` lines 165–173) to rank `in_run_order` (lines 22–29): lower priority, then earlier `TRANSACT_FROM_TS`. On two synthetic queued rows the earlier enqueue sorts first, so the later job is position 2 while both are still queued. `queue_vid` is the row version. `get_active` (lines 177–180) returns the last version, so a job that has been QUEUED, RUNNING, and COMPLETED shows 3. That part of the report is right, and it is still true (`quant/api/services/jobs.py` line 282).

**Residual.** The position is taken from at most 500 rows of a newest-first query. A queue deeper than that can omit the job that should run first, and the new job's position is then too small. That is not the six measured responses.

**Fix direction.** Leave `queue_pos` on the run-order rank. If the API keeps returning `queue_vid`, label it as the version count. The 500-row window only matters if the queued set can actually pass 500.

## B15. The first entry is not charged a fee

**Status:** by design. **Severity:** low. **Effort:** none, unless the owner reopens it.

PR #58 [item 5](2026-09-25-backtest-review.md#5-the-first-entry-after-a-nan-position-is-free). Commit `d47731641` (2026-09-25 21:14 HKT) states the rule: charge a fee only when two known positions differ.

**Confirmed by running.** On a synthetic one-factor run the first finite position is +1 and its `trade` is 0. The implementation is `quant/strategy/performance.py` lines 271–277. A later flat-to-long, with both bars known, is charged. The opening of a run, and the bar after a NaN gap, are not. The 2023 BTC measurement (turnover 81, opening trade excluded) is in the review.

## B16. SMA/EMA momentum on raw price is buy-and-hold

**Status:** open. **Severity:** low. **Effort:** small.

PR #58 [item 6](2026-09-25-backtest-review.md#6-arithmetic-sharpe-can-rank-a-ruined-short-and-smaema-band-signals-are-buy-and-hold). The indicators guide already warns that a band threshold on an SMA or EMA level is not a meaningful pair. The grid still searches it.

**Repro (dossier).** Jobs `64c467ef` and `ac4c4ab7` (EMA and SMA, BTC 1H) share Sharpe 0.9726 and MDD 1.259, equal to buy-and-hold MDD. `cc10cae1` and `669be3e3` match buy-and-hold MDD as well. Those MDDs above 1 are also the stale pre-cutover figures in B8.

**Confirmed by running.** A rising synthetic price, SMA window 20, `momentum_band_signal` with threshold 1: every finite position is +1, and the strategy Sharpe equals the buy-and-hold Sharpe. SMA and EMA return a price level (`quant/strategy/indicators.py` lines 23–31). The band signal goes long when that level exceeds a threshold of order 1 (`quant/strategy/signals.py` lines 246–251). On crypto prices the level never crosses back through 1.

**Fix direction.** The review's: keep the pair out of the default grid, or say on the result that the position never left long. Promotion will still accept it whenever buy-and-hold itself clears the Sharpe gate.

## B17. Hourly RSI grids are mostly empty

**Status:** open. **Severity:** low. I agree with the dossier that this is the grid plus a missing explanation, more than a wrong formula. **Effort:** small.

Not in PR #58 or #59.

**Repro (dossier).** Sync optimize, BTC 1H, 2021-07-01 to 2024-06-30 23:00, RSI `momentum_long`, windows 120–1200 step 72, signals 50–80 step 5, 112 trials. File: `raw/optimize_H_BTC_RSI_momL_IS_55735aba82.json`. 51 of 112 valid in that file; across the hourly RSI runs, 42–52 of 112. By signal: 75 and 80 are 0/16, 70 is 3/16, 65 is 5/16. Daily RSI on a similar grid had 106–133 valid of 144.

**Confirmed by running.** The same 112-cell grid on a synthetic hourly geometric walk (seed 0, about 0.8% hourly moves, 26,304 bars), scored the way the objective scores a flat book (finite pnl after the window, NaN when the standard deviation is 0 or the sample is under 60):

| Signal | Valid |
|---|---|
| 50 | 16/16 |
| 55 | 16/16 |
| 60 | 6/16 |
| 65 | 1/16 |
| 70, 75, 80 | 0/16 |

39 of 112 valid. That is not the stored BTC series, so the dossier's 51/112 stands as the live count. The shape matches: the high thresholds are empty. A series stuck at RSI 55 produces an all-flat position at signal 80.

**Cause.** Hourly RSI at these windows is a long average and spends its time near the middle of 0–100. `momentum_long` on a bounded indicator is `momentum_bounded_signal_long_only` (`quant/strategy/signals.py` lines 294–298): long only when the reading is above the signal. A book that never crosses stays flat, pnl variance is 0, and `get_sharpe_ratio` returns NaN (`quant/strategy/performance.py` lines 318–322). The search maps that to invalid (`quant/strategy/optimizer.py` lines 184–187 and 341). The result says how many trials were valid. It does not say they were flat.

**Fix direction.** On the heatmap or the valid-count, say that a trial was dropped because the position never changed (or because the sample was shorter than 60). Narrowing the default hourly RSI signal grid is a research choice, not an engine change.

## B18. A signal type reached the database before the worker

**Status:** that failure will not recur for `momentum_long`. The ordering gap is open. **Severity:** low. **Effort:** medium if enqueue should refuse an unknown signal.

Not in PR #58 or #59.

**Repro (dossier).** Job `cfa2940c-bac7-42c5-afcc-8f53c379163e`, the first `momentum_long` run, FAILED at 2026-09-13 23:20 HKT with `ValueError: SignalDirection has no method 'momentum_band_signal_long_only'`. Job `8252fe48` succeeded 18 minutes later.

**Cause.** The message is the one `resolve_signal_func` still raises (`quant/strategy/signals.py` lines 330–334) when REFDATA names a method the loaded class does not have. `momentum_band_signal_long_only` is on the class now (lines 280–284). The refdata row was released before the worker image that implemented it. Nothing at enqueue checks that the resolved function exists on this process.

**Fix direction.** Resolve the signal function when the job is accepted, and fail the enqueue with the missing method named, so a REFDATA publish cannot queue work the running image cannot score. Shipping the image before the refdata row is the operational half of the same guard.

## B19. API docs URLs serve the website

**Status:** disabling the docs in prod is by design. The 200 from the SPA fallback is a residual. **Severity:** low. **Effort:** small.

**Repro (dossier).** Unauthenticated GETs on 2026-09-27 00:07 HKT. `/docs`, `/redoc`, and `/openapi.json` returned HTTP 200 `text/html`. `/api/v1/docs` and `/api/v1/openapi.json` returned 404 JSON. Not re-requested here.

**Cause.** `quant/api/main.py` lines 128–136 set `docs_url`, `redoc_url`, and `openapi_url` to `None` when `APP_ENV` is `prod`. Nginx then serves the SPA for any other path (`docker/nginx/nginx.cloudflare.conf` lines 112–116, `try_files` to `index.html`). Unknown paths answer 200 with the website, which is what a script sees.

**Fix direction.** Leave the FastAPI docs off in prod. If a missing path should not look like the app, return 404 from nginx for `/docs`, `/redoc`, and `/openapi.json`, or for any path the SPA router does not own.

## B20. Backfill is capped at 10,000 bars

**Status:** by design. **Severity:** low. **Effort:** medium for a background "run every pass" job. That is a product change, not a bugfix.

**Repro (dossier).** Hourly passes in `backfill/fire_hourly_log.json`: BTC 1H six (five that inserted, plus the empty repeat in B9), BNB 1H five, ETH 1H four.

**Cause.** `MAX_BACKFILL_BARS = 10_000` (`quant/market_data/service.py` lines 55–60). The comment and `BackfillTooLargeError` (lines 322–329) say one blocking fill must stay inside the proxy time budget. `handle_backfill_too_large` (`quant/api/exception_handlers.py` lines 153–162) is the same reason. A deep hourly history is several clicks. The empty extra pass is B9, not this cap.

**Fix direction.** A button or job that keeps calling the plan until it completes, once B9 can actually complete. Raising the constant makes the timeout more likely. The file already says a minute-scale fill needs a background job.

## B21. Synchronous optimize timed out at the edge

**Status:** open. **Severity:** low. **Effort:** small.

Not in PR #58 or #59. Seen once.

**Repro (dossier).** `POST /api/v1/backtest/optimize`, file `round3/raw/optimize_A_coarse_ETH_IS_40-40-1_10-150-20_74fabe2c2f0a_ERR.json`. ETH daily, 2021-07-01 to 2024-06-30, FILTER. Factor 1: BTC Bollinger window 40, signals 0–2.5 step 0.25. Factor 2: ETH Bollinger windows 10–150 step 20, signals −1.0–1.5 step 0.25. About 968 trials. HTTP 524, Cloudflare's timeout HTML, after 170 seconds. No JSON body. Unknown whether the process kept computing.

**Cause.** `POST /optimize` (`quant/api/routers/backtest.py` lines 35–50) runs the search in the request. There is no trial cap and no application timeout on that route. Nginx allows 300 seconds (`docker/nginx/nginx.cloudflare.conf` line 94). A 524 is the edge closing first. The 170 second figure is the dossier's one measurement. The queued path exists for this size of search. B20's backfill guard is the pattern: refuse before the proxy, and say which call fits.

**Fix direction.** Above a trial count, return 400 telling the caller to enqueue, or document the sync budget next to the route. Either one is enough. Do not raise the edge timeout to hide it.

## Recommended fix order

1. **B1.** Every stored long-only AND is an OR, and the unit test currently locks that in. Small change, then recompute the affected results.
2. **B3 and B4 together.** Multi-factor stochastic errors; cross-coin stochastic returns the traded coin's oscillator with no error. One indicator-frame change covers both. Small to medium.
3. **B2, the restart.** The label is already fixed. Hold-out metrics, the overfitting ratio, and the decision #83 gate all drop about one window of the out-of-sample bars. Medium.
4. **B5.** Write the comparison rule down before changing promotion. Large as a decision, then medium to implement. The hold-out gate does not make two date ranges comparable.
5. **B6.** Mark the stored Sharpe 5.07 lineage the way PR #59 already describes, and count stochastic's second window in the sample gate. Small.
6. **B9.** Stop re-planning a head the venue does not have. Medium. B20 stays a cap until there is a background fill.
7. **B10 and B11.** Distinct baseline / provisional labels. Small, and they share one story: VID 1 is Best at insert.
8. **B17, B16, B12's cap, B19, B21, B18.** Diagnostics, a paging or a higher cap, a 404 for the disabled docs, a sync trial budget, and an enqueue-time signal check. Each is small or medium, and none of them change a stored Sharpe by themselves.

Leave these as they are unless the owner reopens them: **B7** (fixed; old Volume rows stay wrong until replayed), **B8** (replay is the PR #59 cleanup), **B13** (decision #58), **B14** (rank is in place; `queue_vid` is a version), **B15** (decision in `d47731641`), **B20** (the 10,000-bar cap).

## Already recorded elsewhere

The dossier's appendix, so it is not dropped:

- Multi-factor tie-break used the whole series. PR #58 item 3. Fixed in `f9cb8468e` (2026-09-25 22:02 HKT). That commit does not fix B1.
- Promotion ranked the full-sample Sharpe and ignored `walk_forward.oos_metrics`. PR #58 item 1. Decision #83 / `bb62d6a80` adds the hold-out gate and the buy-and-hold excess gate. The changeset is `refdata,prod-deploy`. The dossier's deploy run `eca4a1d75` was cancelled; whether a later migrate applied `1.26.0` was not checked.
- Live perp fill versus the spot backtest. PR #58 item 4. Not reproduced here.
