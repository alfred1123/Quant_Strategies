# AlgoDaemon bug verification, rounds 3–4 (2026-09-27)

**Doc type:** platform review. It checks the research agent's round 3 and round 4 findings against the code, and round 5 item B26 in [section 7](#7-b26-volume-limited-to-a-raw-input-column). This page does not change the engine.
**Status:** open findings, checked against `main` at `69bf240d8` (2026-09-27 08:16 HKT).
**Follows:** [AlgoDaemon bug report (2026-09-27)](2026-09-27-algodaemon-bug-report.md) (PR #64), which checked B1–B21 against `9c1af3619`. The eight commits after `9c1af3619` are documentation PRs (#60–#66), so the engine lines that report cites have not moved.
**Sources:** the research dossier (items B22–B25, compiled 2026-09-27 01:50 HKT), the raw job rows in `round3/raw/`, the round 4 notes (`round4/README.md`), and the round 5 note on B26. These files are on the researcher's machine and are not in this repository. Live `algodaemon.com` was not called for this page.

Bar times are UTC. Clock times are HKT.

How each item was checked:

| Mark | Meaning |
|---|---|
| Ran | Reproduced on synthetic data with the engine code from this `main`. Production job ids and their stored numbers are still the dossier's. |
| Read | The cause is in the current source. Line numbers are `main` at `69bf240d8`. |
| Raw | Read from the stored job or strategy rows the researcher saved from the API. |
| Offline | Measured by the researcher's offline copy of the engine (`round4/replica.py`). That copy matches the platform to 2e-16 on the round 3 grids, but it is not a platform run. |

## Summary

Seven items. All seven are real. Two of the round 3–4 items are smaller than first reported.

- **SMA and EMA are raw price levels** (item 1). Compared with a threshold of 0 to 0.10, they are always long or never long. "Price above its EMA" cannot be built. Open.
- **Grids over 10,000 cells are sampled** (item 2). The search switches to Optuna TPE with seed 42 and runs 10,000 trials. The config drawer does show "capped from N combos" before the run. Nothing on the result or the stored job says the grid was sampled, and the sampler repeats cells. The repeated `top10` is fixed. Labelling the sample is still open.
- **Window ranges have no lower bound** (item 3). Window 0 passes validation. For SMA, Bollinger, RSI and stochastic it scores NaN and wastes trials. For EMA, window 0 fails the whole run. A negative window also fails the whole run. Open, low.
- **A signal fills on the same close** (item 4). This is not lookahead. It is a modelling choice, and there is no option to delay the fill. Offline, some Best rules lose most of their out-of-sample Sharpe with a one-day delay. Open, as a proposal.
- **B24: duplicate jobs make duplicate versions** (item 5). The version is created at **enqueue**, not when the job completes. `SP_INS_STRATEGY` always adds a new `STRATEGY_VID` for the name and never compares `CONFIG_JSON`. Confirmed. Open.
- **Hourly annualisation** (item 6). **Downgraded.** The web app sets `trading_period` from the bar interval: 365 × 24 = 8,760 for hourly crypto. What is left is that the API accepts any `trading_period` with any interval, and one narrow path in the drawer.
- **B26: volume is only a raw input column** (item 7). `TechnicalAnalysis` is SMA, EMA, RSI, Bollinger, and stochastic. A factor reads one column, and a rule does not remember the previous position, so OBV, VWAP, dollar volume, Amihud, and "enter when volume confirms, then hold" cannot be built. Lowercase `"volume"` is an opaque HTTP 400 on the paths that look the column up. Open, as a limitation.

## Status

| # | Dossier | Title | Severity | Status | Verified |
|---|---|---|---|---|---|
| [1](#1-sma-and-ema-compare-the-raw-average-with-the-threshold) | B22 | SMA and EMA compare the raw moving average with the threshold | Medium | Confirmed, open. Extends #64 [B16](2026-09-27-algodaemon-bug-report.md#b16-smaema-momentum-on-raw-price-is-buy-and-hold) | Ran + read |
| [2](#2-big-grids-are-sampled-without-saying-so) | B23 | Grids over 10,000 cells are sampled by TPE; the result does not say so | Medium | Confirmed. Repeated `top10` fixed. Labelling still open. A pre-run caption exists | Read + raw |
| [3](#3-window-ranges-have-no-lower-bound) | B23 | `RangeParam` has no bounds; window 0 or below is accepted | Low | Confirmed, open | Ran + read + raw |
| [4](#4-a-signal-is-filled-on-the-same-close) | Round 4 | Same-close fill, with no fill-delay option | Medium | Confirmed as a modelling limit, open. Proposal only | Read + offline |
| [5](#5-b24-duplicate-jobs-create-separate-versions) | B24 | Duplicate jobs create separate strategy versions | Low | Confirmed, open | Read + raw |
| [6](#6-hourly-annualisation-default) | — | Hourly runs annualised on a daily `trading_period` | Low | Downgraded. The web app derives it from the interval. The API does not check it | Read + raw |
| [7](#7-b26-volume-limited-to-a-raw-input-column) | B26 | Volume can only be used as a raw input column | Medium (limitation) | Confirmed, open. No volume indicators, no column arithmetic, no stateful entry | Read. The Sharpe and the replica match: researcher |

Items already covered, or fixed:

| Item | Where | Status on `69bf240d8` |
|---|---|---|
| B5. Promotion compares Sharpe across different date ranges | #64 [B5](2026-09-27-algodaemon-bug-report.md#b5-promotion-compares-sharpe-across-different-date-ranges) | Open. Covered in #64 |
| Stochastic warm-up is about 2 × window, and the extra window slips past the sample-size count (dossier B25) | #64 [B6](2026-09-27-algodaemon-bug-report.md#b6-a-short-sample-volume-filter-is-still-best) | Open. Covered in #64. `%D` is still a rolling mean of `%K` (`quant/strategy/indicators.py` line 62) |
| B1. FILTER with 3+ factors behaves like OR in its direction factors | #64 [B1](2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors) | Open. Covered in #64 |
| B12. My Jobs listed the oldest 50 | #64 [B12](2026-09-27-algodaemon-bug-report.md#b12-my-jobs-listed-the-oldest-50) | Fixed in `9c1af3619`. `SP_GET_QUEUE.sql` line 90 still reads `ORDER BY q.CREATED_AT DESC`. The 50-row cap remains |
| B7. Single-factor Volume run used price | #64 [B7](2026-09-27-algodaemon-bug-report.md#b7-a-single-factor-volume-run-used-price) | Fixed in `c35ea23d2`. `quant/strategy/performance.py` lines 196–197 still replace `factor` with the requested column. The researcher confirmed the fix live in round 5: capital-V `Volume` matched their offline replica to 2e-16. This page did not re-run that |

## 1. SMA and EMA compare the raw average with the threshold

**Status:** confirmed, open. **Severity:** medium. **Effort:** small for new indicator variants. Stored SMA/EMA results do not need a replay; they are buy-and-hold or empty.

This extends #64 [B16](2026-09-27-algodaemon-bug-report.md#b16-smaema-momentum-on-raw-price-is-buy-and-hold) and PR #58 [item 6](2026-09-25-backtest-review.md#6-arithmetic-sharpe-can-rank-a-ruined-short-and-smaema-band-signals-are-buy-and-hold). Both record the symptom. Neither proposes an indicator that can express a trend rule.

**Repro (dossier).** `POST /backtest/performance`, BTC daily, 2021-07-01 to 2026-09-25, 10 bps. `get_sma` and `get_ema`, window 50:

- `momentum_long` at signals 0.00, 0.05 and 0.10: 100% time in market, turnover 0, Sharpe 0.4814. Buy-and-hold is also 0.4814.
- `reversion_long` at 0.05: 0% time in market, Sharpe NaN.
- Signal 60,000: in the market on 48–49% of days. That is "the average is above 60,000 USDT", not a trend rule.
- As a FILTER gate (window 200, signal 0.05) in front of BTC Bollinger 55/1.75, the gate is always open.

**Confirmed by running.** A synthetic random walk between about 22,000 and 177,000, window 50, through `Performance`:

- `momentum_band_signal_long_only` at 0.00, 0.05 and 0.10 is long on every scored bar. Sharpe equals buy-and-hold (1.0281) for both SMA and EMA.
- `reversion_band_signal_long_only` is never in the market. Sharpe is NaN.
- On the same series, price was above its EMA(50) on 60% of bars. That is the rule a user expects, and no setting produces it.

**Cause.** `quant/strategy/indicators.py`:

```python
def get_sma(self, period):                                        # line 23
    sma = self.data['factor'].rolling(window=period).mean()
def get_ema(self, period):                                        # line 28
    ema = self.data['factor'].ewm(span=period, adjust=False).mean()
```

Both return the average itself, in price units. The band signals compare that value with the threshold (`quant/strategy/signals.py` lines 246–251):

```python
position = np.where(data_col > signal, 1, np.where(data_col < -signal, -1, 0))
```

On a positive price, the average is always above any small threshold. Only Bollinger is normalised: it returns `(factor - sma) / rstd` (lines 47–52). So Bollinger at signal 0 is exactly "price above SMA(w)". There is no EMA equivalent.

The seeded range suggests a relative distance was intended. `db/liquidbase/refdata/data/INDICATOR.sql` lines 5–6 give SMA and EMA a signal range of 0.00–0.10, step 0.01. That only makes sense for something like `price / MA − 1`.

**Fix direction (no code here).** Add distance-from-average variants, for example `price / SMA(w) − 1` and `price / EMA(w) − 1`, or `(price − MA) / MA`. They are unbounded like Bollinger, so they work with the existing band signals, and the seeded 0–0.10 range becomes a real "at least x% above the average" threshold. Then take the raw-level SMA and EMA out of the default picker, or label them "level". Nothing that is stored needs a replay.

## 2. Big grids are sampled without saying so

**Status:** confirmed. Repeated `top10` rows are fixed. Labelling is still open. **Severity:** medium. The drawer caption stops it from being fully silent, but the result and the stored job say nothing. **Effort:** small for labelling, medium for a hard limit.

**Repro (raw).** ETH jobs `63dac35d-dd23-4e25-bd62-3e558cec074a` (VID 3) and `666b8aa4-7c5d-4215-90d8-2abae293d7c1` (VID 4), strategy `1f84c585`. Both factors use `window_range` 0–160 step 5 (33 values) and `signal_range` 0–2.5 step 0.25 (11 values). That is 33 × 11 × 33 × 11 = 131,769 cells. The stored result has `total_trials` 10,000 and `valid` 9,346.

Checked in the stored `grid` of `63dac35d`:

- The 10,000 trials cover only **9,655 distinct cells**. TPE picks from a categorical space and repeats cells.
- `top10` is **ten copies of the same cell** (55/2.25 + 65/1.25, Sharpe 1.4027). There is no de-duplication before the top 10 is cut.
- 654 trials have a null Sharpe. 475 of those contain a window of 0 (item 3).
- The Best pick is the highest full-period Sharpe among the sampled cells. The job's own walk-forward picked 25/2.25 + 100/0.25, with out-of-sample Sharpe 0.355. The walk-forward's in-sample search is the same size, so it is sampled too.

**Cause.** `quant/strategy/optimizer.py`:

```python
OPTUNA_MAX_TRIALS = 10_000                                        # line 28
OPTUNA_SEED = 42                                                  # line 29

def _select_search(total, n_trials):                              # line 320
    if n_trials is None:
        n_trials = min(total, OPTUNA_MAX_TRIALS)
    if n_trials >= total:
        return ExhaustiveSearch(), total
    return BayesianSearch(), n_trials
```

`run_optimize` calls `opt.run(window_list, signal_list)` with no `n_trials` (`quant/strategy/backtest_service.py` line 565), so any grid over 10,000 cells goes to `BayesianSearch` (`TPESampler(seed=OPTUNA_SEED)`, line 251). The only record is the INFO log line from `BayesianSearch.log_start` (lines 234–245). At `69bf240d8`, `_build_result` (lines 340–353) sorted all trials by Sharpe and kept duplicates.

**top10 de-duplication (fixed).** `_build_result` still sorts by Sharpe, then keeps the first row of each parameter cell (the best Sharpe for that cell) before the top-10 cut. `grid` and `n_valid` still count every trial, including revisits. Labelling (`search`, `grid_size`, `distinct_trials`) is still not stored or shown.

**What the user sees.**

- API: `OptimizeResponse` (`quant/schemas/backtest.py` lines 149–163) has `total_trials` and `valid`, and no field for the grid size or the search method. `total_trials` is `len(result.grid_df)` (`backtest_service.py` line 591), so it reads 10,000, the trials run, not the cells in the grid. The stored job result is the same payload.
- Config drawer: before the run it shows `10,000 trials (capped from 131,769 combos)` (`frontend/src/components/ConfigDrawer.tsx` lines 237–243 and 565). "Capped" does not say the 10,000 are chosen by TPE, or that cells repeat. The drawer keeps its own copy of the 10,000 constant (line 241).
- Results: the chip reads `9346 / 10000 valid trials` (`frontend/src/pages/BacktestPage.tsx` line 349). Nothing there, or on a stored job opened later, says the grid was sampled.

**Fix direction.** Return and store `search` (`exhaustive` or `tpe`), `grid_size`, and `distinct_trials` with the result, and show them on the results chip and the job row. De-duplicate `top10` by parameters. Then decide the limit: refuse grids above 10,000 cells, or keep TPE and label the Best as "best of a sample". The drawer caption should say "sampled" instead of "capped".

## 3. Window ranges have no lower bound

**Status:** confirmed, open. **Severity:** low. **Effort:** small.

**Cause.** `quant/schemas/backtest.py` lines 5–14:

```python
class RangeParam(BaseModel):
    min: float
    max: float
    step: float
```

There are no bounds on `min`, `max` or `step`. The frontend `RangeFields` inputs have no minimum either. `require_scoreable_sample` (`backtest_service.py` lines 539–556) reads only `window_range.max`. Window values come from `to_values(as_int=True)`, which is `range(int(min), int(max) + 1, int(step))`.

**What happens downstream (ran, pandas 3.0.6 with this `main`'s engine code).**

| Input | Result |
|---|---|
| Window 0: SMA, Bollinger, RSI, stochastic | `rolling(window=0)` is allowed and returns all NaN. The position is NaN, the Sharpe is NaN, and the trial is counted as invalid. The run completes. A 0–20 step 5 grid with 3 signals gave 15 trials and 12 valid. The 3 window-0 trials had a null Sharpe |
| Window 0: EMA | `ewm(span=0)` raises `ValueError: span must satisfy: span >= 1`. `IndicatorCache` builds every window in the `Objective` constructor, before the per-trial `try` in `SearchStrategy.evaluate` (`optimizer.py` lines 184–191). So the **whole run fails**: HTTP 400 on the sync route, FAILED in the queue |
| Negative window, any rolling indicator | `rolling(window=-5)` raises `ValueError: window must be an integer 0 or greater`. The whole run fails in the same way |
| `step` 0 | `range()` raises `ValueError` for windows. `np.arange` raises `ZeroDivisionError` for signals. The run fails |

The live case is the first row. In job `63dac35d`, 475 of the 10,000 sampled trials had a window of 0, and every one of them had a null Sharpe. Because the grid was sampled, those wasted trials were also cells that were never searched.

On the queue path, `EnqueueRequest.config_json` is a plain `dict` (`quant/api/schemas/jobs.py` line 26). `OptimizeRequest` validation happens only in the worker (`quant/queue/worker.py` line 124). The strategy version is created at enqueue (item 5). So a run that fails on a bad range still leaves a new VID behind.

**Fix direction.** Give `RangeParam` `step > 0` and `max >= min`. Add a window-specific minimum of 2 (Bollinger's rolling standard deviation is NaN at window 1). Validate `config_json` as an `OptimizeRequest` at enqueue, before `sp_ins_strategy`, so a bad range gets a 422 and never becomes a version. Put the same minimum on the drawer inputs.

## 4. A signal is filled on the same close

**Status:** confirmed as a modelling limit. Open as a proposal. **Severity:** medium, for how far live results can fall short of the backtest. **Effort:** small for an option, medium once the drawer, stored config and promotion carry it.

This is not lookahead. PR #58 already notes the timing in its [overview](2026-09-25-backtest-review.md#overview) and [item 4](2026-09-25-backtest-review.md#4-live-orders-are-not-the-fill-the-backtest-measures). What is new here is the round 4 measurement and the missing option.

**Cause.** `quant/strategy/performance.py`, `_compute_pnl_columns` (lines 271–285):

```python
prior = self.data['FinalPosition'].shift(1)
...
self.data['pnl'] = (self.data['FinalPosition_x1'] * self.data['chg']
                    - self.data['trade'] * self.transaction_cost)
```

`chg` is `price.pct_change()` (line 237 or 244). The position decided on the close of bar *t* uses only data up to *t*, and earns the move from *t* to *t+1*. In effect it is filled at the close that produced the signal. The optimizer's `Objective._sharpe` (`quant/strategy/objective.py` lines 74–93) does the same thing with `pos_x1[1:] = pos[:-1]`. There is no delay parameter anywhere in `quant/strategy/` or on `OptimizeRequest`. The only `shift` in the engine is the one above.

**Offline measurements (researcher, `round4/README.md`, `fill_timing.py`, `e_hourly.py`).** These come from the offline engine copy, not from a platform run. "Delay 1" means a fill one bar later, `FinalPosition.shift(2)` in the formula above.

| Rule | OOS Sharpe, delay 0 → delay 1 | FULL Sharpe, delay 0 → delay 1 |
|---|---|---|
| ETH A1 (Best v5: gate 55/2.25, ETH 110/−0.75) | 1.60 → 0.69 | 1.43 → 1.20 |
| ETH A2 (gate 65/2.25, ETH 100/−1.0) | 1.24 → 1.26 | 1.32 → 1.57 |
| BNB Best 75/2.5 | 1.20 → 0.45 | 1.25 → 1.10 |
| BTC Best 55/1.75 | 0.82 → 0.00 | — |

- A1 and the BNB and BTC Best rules lose most of their out-of-sample Sharpe with a one-day delay. A2 holds up.
- Across the round 3 grids, a one-day delay raises in-sample Sharpe and lowers out-of-sample Sharpe. The recent edge is concentrated on the first day after each signal. A1 earns 41% of its OOS gross P&L on its 10 entry days.
- Hourly ETH A1 (windows × 24, `trading_period` 8,760): Sharpe 1.10 after 10 bps fees and 1.33 with no fees. OOS is 1.36 after fees and 1.60 with no fees. 6.6% time in market. On hourly bars, fees cost about 0.24 Sharpe.

With about 10 out-of-sample entries per gated rule, a few days decide these numbers.

**Proposal (no code).** Add `fill_delay_bars` (default 0, today's behaviour) to `OptimizeRequest`, `PerformanceRequest` and the stored `CONFIG_JSON`. Apply it as `FinalPosition.shift(1 + fill_delay_bars)` in both `_compute_pnl_columns` and `Objective._sharpe`, and charge turnover on the delayed position. Show it on the results chip. Before any rule is promoted for live trading, a delay-1 re-score beside the delay-0 score would show which winners are delay-fragile. Whether promotion should require it is a separate decision.

## 5. B24: duplicate jobs create separate versions

**Status:** confirmed, open. **Severity:** low. **Effort:** small for a server-side check.

**Repro (raw).** `round3/raw/job_63dac35d-….json`, `job_666b8aa4-….json` and `strategies_all_after_r3.json`:

| | `63dac35d-dd23-4e25-bd62-3e558cec074a` | `666b8aa4-7c5d-4215-90d8-2abae293d7c1` |
|---|---|---|
| Strategy | `1f84c585`, VID 3 | `1f84c585`, VID 4 |
| Version created | 2026-09-26 22:15:02 HKT | 2026-09-26 22:15:33 HKT |
| Job completed | 22:33:38 HKT | 22:33:57 HKT |
| `config_json` | identical (same SHA-256 of the key-sorted JSON) | identical |
| Sharpe | 1.40274733793208 | 1.40274733793208 |
| Stored `grid` | identical | identical |

VID 3 became Best, then lost Best to VID 5 (`53d62e76`, Sharpe 1.4304). VID 4 was never Best. The two versions were created 31 seconds apart. The web app disables Run while an enqueue is pending (`BacktestPage.tsx` line 296, `isRunning={enqueue.isPending}`), so this was not a fast double-click in the UI. It was two separate submissions. Who sent them is not established.

**Where the version is created.** At **enqueue**, not when the job completes.

- `JobsService.enqueue` (`quant/api/services/jobs.py` lines 112–137) calls `self._repo.sp_ins_strategy(strategy_nm=..., config_json=..., user_id=...)` (lines 119–123), then `sp_ins_queue`. It does not look for an existing version, a config hash, or a job that is already queued.
- `BtQueueRepo.sp_ins_strategy` (`quant/queue/repo.py` lines 107–128): "When `(user_id, strategy_nm)` already exists the SP reuses that `STRATEGY_ID` and bumps `STRATEGY_VID`."
- The procedure, `db/liquidbase/bt/procedures/SP_INS_STRATEGY_VID_BY_NM.sql`, looks up the id by name only (lines 60–66), then:

```sql
SELECT COALESCE(MAX(STRATEGY_VID), 0) + 1 INTO V_VID
  FROM BT.STRATEGY WHERE STRATEGY_ID = V_STRATEGY_ID;           -- lines 73–76
INSERT INTO BT.STRATEGY (..., CONFIG_JSON, ...) VALUES (..., IN_CONFIG_JSON, ...);  -- lines 85–109
```

`CONFIG_JSON` is written and never compared. The advisory lock on user plus name (lines 55–57) orders concurrent inserts. It does not merge them.

- `BT.STRATEGY` (`db/liquidbase/bt/tables/STRATEGY.sql`) has no hash column. Its only unique key is `(USER_ID, STRATEGY_NM, STRATEGY_VID)`.
- On completion, the worker (`quant/queue/worker.py` lines 158–176) inserts the result, runs promotion, and writes COMPLETED. It does not create or merge versions.
- `EnqueueRequest` (`quant/api/schemas/jobs.py` lines 22–27) has `strategy_nm`, `config_json` and `priority`. There is no idempotency key.

**Relation to PR #59.** [Strategy identity](2026-09-25-backtest-data-hygiene-proposal.md#strategy-identity) proposes a server-built `RECIPE_KEY` so the server, not the client's name string, decides which rows are one lineage. That fixes **lineage** identity, and decision #82 records it as not adopted. It does not stop this bug: under `RECIPE_KEY`, every enqueue is still the next VID. [Proposed key](2026-09-25-backtest-data-hygiene-proposal.md#proposed-key) puts the date range, fee, grid and walk-forward settings on the version on purpose, so a version-level check has to compare the whole normalised `CONFIG_JSON`.

**Fix direction.** Store a `CONFIG_HASH` on `BT.STRATEGY`. It is a hash of the normalised `CONFIG_JSON`: sorted keys, and numbers as numbers (the stored configs mix `"0.25"` strings with floats). In `SP_INS_STRATEGY`, if the latest version for that id has the same hash, return it instead of inserting. Then either refuse a second queued job on that version, or return the existing `queue_id`. A deliberate re-run can pass an explicit flag. The existing duplicate (VID 4) can be retired with `LOGICAL_DELETE_IND`. It is not Best.

## 6. Hourly annualisation default

**Status:** downgraded. The web app does not leave hourly runs on 365. **Severity:** low. **Effort:** small.

**What the code does.**

- Backend: `OptimizeRequest.trading_period: int` and `PerformanceRequest.trading_period: int` are required, with no default and no bounds (`quant/schemas/backtest.py` lines 59 and 94). `build_config` passes the number straight through (`backtest_service.py` line 327, `trading_period=req.trading_period`). Nothing compares it with `tm_interval_id`. PR #41 (`c932fa432`, 2026-09-03 23:28 HKT) dropped a server-side `_require_annualization` guard on purpose, and moved the job to the drawer.
- Frontend default: `DEFAULT_CONFIG.tradingPeriod: 365` with `tmIntervalId: null` (`frontend/src/pages/BacktestPage.tsx` lines 44–45). The drawer then seeds DAILY (`ConfigDrawer.tsx` lines 116–120), so 365 matches.
- Frontend derivation: `annualization` (`ConfigDrawer.tsx` lines 145–149) multiplies the asset type's daily `trading_period` by bars per day for the chosen interval:

```ts
const perDay = row ? barsPerDay(row.period_length) : null;
return perDay ? Math.round(dailyTradingPeriod * perDay) : dailyTradingPeriod;
```

It runs when the Bar Interval changes (line 326), when a product is picked (line 305), and when an asset type is picked (line 373). `barsPerDay` (`frontend/src/utils/interval.ts` lines 37–40) is 86,400 ÷ the bar length in seconds. Hourly crypto gets 365 × 24 = 8,760.
- Clone and Re-backtest restore the stored `trading_period` (`frontend/src/utils/requestBuilders.ts` line 89).

**Stored evidence (raw).** Every job and strategy row the researcher saved that has `tm_interval_id` 2 (1H) carries `trading_period` 8,760: 30 distinct hourly jobs, for example `cc10cae1`. All 32 daily jobs carry 365.

**What is left.**

1. The API accepts `trading_period` 365 with an hourly `tm_interval_id` and scores it. Hourly Sharpe is then about √24 ≈ 4.9 times too low, and annualised return is far too low as well. A script, or an old client, can store such a row, and promotion would compare it bare.
2. One narrow path in the drawer (read from code, not reproduced in a browser). The Bar Interval handler updates `tradingPeriod` only when `selectedAssetType` is set (lines 325–327). On first load the asset type is filled in by an effect that deliberately leaves `tradingPeriod` alone (lines 127–135). A user who switches to 1H before that effect runs keeps 365. Clearing the asset type also resets 365 regardless of interval (line 370), but validation then blocks the run until an asset type is picked again, and picking one recomputes the value.

**Fix direction.** Derive `trading_period` on the server from `tm_interval_id` and the product's asset type, or refuse a request whose `trading_period` is not the daily figure × bars per day. That is not the arbitrary 366 threshold that #41 rejected. In the drawer, recompute `tradingPeriod` whenever `assetType` or `tmIntervalId` changes, not only in the three handlers.

## 7. B26: volume limited to a raw input column

**Status:** confirmed, open. **Severity:** medium (limitation). Nothing in the engine is silently wrong here except the 3-factor FILTER case, which is #64 [B1](2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors). **Effort:** small for the error text. Medium for a derived series or a column expression. The stateful hold is the [PR #63 proposal](2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers).

**Indicators (read).** `TechnicalAnalysis` (`quant/strategy/indicators.py`) has five methods:

```python
def get_sma(self, period):                                        # line 23
def get_ema(self, period):                                        # line 28
def get_rsi(self, period):                                        # line 33
def get_bollinger_band(self, period):                             # line 47
def get_stochastic_oscillator(self, period):                      # line 54
```

There is no OBV, VWAP, MFI, CMF, relative volume, dollar volume, or Amihud. On a `Volume` column the transforms that return a scale-free series are Bollinger's z-score and RSI. SMA and EMA return the raw level, which is [item 1](#1-sma-and-ema-compare-the-raw-average-with-the-threshold).

**One column (read).** `FactorConfig` carries a single `data_column` (`quant/schemas/backtest.py` line 32). `build_config` copies it onto the `SubStrategy` (`quant/strategy/backtest_service.py` line 314). The series the indicator sees is that one column:

```python
return sub_df[sub.data_column].reindex(main_index)               # performance.py line 174
```

`Objective._factor_series_for_sub` is the same read (`quant/strategy/objective.py` line 101). Multi-factor then builds a frame that holds only that series (`performance.py` lines 183–184, `objective.py` lines 151–152). There is no second column and no expression, so dollar volume (V·C), Amihud, OBV, and VWAP cannot be built. Stochastic is the exception already recorded as #64 [B3](2026-09-27-algodaemon-bug-report.md#b3-stochastic-in-a-multi-factor-run-fails-on-high) and [B4](2026-09-27-algodaemon-bug-report.md#b4-cross-coin-stochastic-uses-the-traded-coins-hlc): it reads `High`, `Low`, and `Close` and ignores `factor`.

**Stateless (read).** Every signal is `(data_col, signal)` (`quant/strategy/signals.py` line 236). `momentum_band_signal` (lines 246–251) maps the current indicator value to −1, 0, or 1. Nothing in `SignalDirection` reads the previous position. The only `shift` in the engine is the fill lag in `_compute_pnl_columns` ([item 4](#4-a-signal-is-filled-on-the-same-close)). "Enter when volume confirms, then hold" needs `Pos(t−1)`. That hold is [Proposal C](2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers) on the fractional-sizing page (PR #63). The rule the engine can run is the stateless one: be long only on the bars where volume itself is above the threshold.

**Opaque name (read).** `data_column: str = "price"` has no enum and no check against the loaded columns. The exchange frame's columns are `price`, `factor`, `Open`, `High`, `Low`, `Close`, and `Volume` (`quant/market_data/service.py` lines 751–762). `factor` is a copy of the close. Those names are not put in the error.

The lookup that raises is `sub_df[sub.data_column]`. `str(KeyError("volume"))` is `"'volume'"`. The sync routes turn any exception that is not a `BacktestError` into HTTP 400 with that string (`quant/api/routers/backtest.py` lines 29–32):

```python
return HTTPException(status_code=400, detail=str(exc))            # line 32
```

Multi-factor always takes the lookup (`performance.py` line 219, `objective.py` line 151), and so does a factor on another product. A one-factor run on the traded coin does not. It looks the name up only when the name is already a column (`performance.py` lines 196–197, `objective.py` lines 127–129). `"volume"` is not `"Volume"`, so that guard skips the lookup and the pre-filled `factor` (the close) is scored. Lowercase `"volume"` is the 400 on a multi-factor or cross-product run, and a silent price score on a one-factor same-coin run. This page did not call the live API. The researcher's 400 is their sync probe.

**Researcher's measurements (not re-run).** From the round 5 note. This page did not replay them.

- A 3-factor FILTER of BTC Bollinger 65/2.25, ETH Bollinger 100/−1, and ETH Volume z-score 20/0 returned exactly A2's Sharpe, 1.3240, and was long on 62 days when the volume leg was off. That is B1: with three or more factors, FILTER combines the non-gate factors by strongest sign.
- `data_column: "Volume"` on the traded coin or on another coin, on `/performance` and `/optimize`, single- and multi-factor, matched their offline replica to 2e-16 on 1,559+ grid cells. That is B7 still fixed, confirmed live by the researcher. The code path is the one #64 already cites (`performance.py` lines 196–197).
- On their offline copy, not a platform run, ETH A2 with a volume entry confirmation went from out-of-sample Sharpe 1.24 to 1.38–1.63 across a plateau. Their stored-bar check (daily and hourly BTC, ETH, and BNB volume: 0 gaps, 0 NaN, 0 zeros) is also theirs.

**Fix direction.** Validate `data_column` against the columns on the loaded frame and put the valid names in the error, including on the one-factor path that currently skips a missing name. Add derived-series indicators (OBV, dollar volume, Amihud, VWAP deviation, volume-weighted mean return), or a `data_column` expression. The stateful "enter only when volume confirms, then hold" belongs with PR #63.

## Recommended order

1. **Item 2, labelling.** Store and show `search`, `grid_size` and `distinct_trials`. Small. `top10` de-duplication is done. Research conclusions currently read a sampled maximum as a grid maximum.
2. **Item 1.** Add distance-from-average SMA and EMA. Small, and it unlocks the trend-filter family the research needs.
3. **Item 5 and item 3 together.** Validate `config_json` at enqueue, add `CONFIG_HASH`, and add `RangeParam` bounds. All three sit in front of `sp_ins_strategy`. Small.
4. **Item 4.** Decide whether `fill_delay_bars` belongs on the request and in the promotion checks. Medium.
5. **Item 6.** Server-side derivation or check of `trading_period`. Small.
6. **Item 7, the error.** Reject a `data_column` that is not on the loaded frame, and list the valid names, including on the one-factor path that currently skips a missing name. Small. Derived volume series, or a column expression, are the larger piece. "Enter when volume confirms, then hold" is the PR #63 proposal.

The #64 order still stands for B1–B21. B1 (AND and 3+-factor FILTER behaving as OR) is still first.
