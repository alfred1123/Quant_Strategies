# Fractional sizing and stateful exits

**Doc type:** proposal. Nothing here is adopted. No schema, procedure, or engine change ships with this page.
**Status:** proposed.
**Read against:** `main` at `9c1af3619` (2026-09-26).

The strongest published crypto trend rule we have a reproduction spec for — Zarattini, Pagani, and Barbon, *Catching Crypto Trends* ([SSRN 5209907](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)) — does not fit this engine. Positions are −1, 0, or +1, so a volatility-targeted fraction and an average of nine sub-model weights cannot be stored. Signals are a function of the current indicator only, so a stop that ratchets up and resets on the next entry cannot be stored either.

This page proposes three backtest slices (A, B, C) and says what has to be true before any of them may send a live order. Adopting one is a later decision-log entry. A Liquibase changeset that seeds a new indicator or conjunction takes the schema context only, until the owner asks for `prod-deploy`.

Related pages, linked so they are not repeated:

- [Backtest review (2026-09-25)](2026-09-25-backtest-review.md) — [PR #58](https://github.com/alfred1123/Quant_Strategies/pull/58). Next-bar fill, the promotion gates, the free first entry, and the one-line note that position size is a large change.
- [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md) — [PR #59](https://github.com/alfred1123/Quant_Strategies/pull/59). Stale stored metrics, strategy identity, and the fact that no column stores an engine version.

PR #58 is merged. It does not describe the long-only AND result. That result is read from the combiner in [The long-only AND path](#the-long-only-and-path).

## How claims are marked

| Mark | Meaning |
|------|---------|
| **Read** | Taken from the file and function named, on the commit above |
| **Checked** | The unit test named already asserts it |
| **Inferred** | Follows from those facts, and was not executed as a backtest |
| **Spec** | Taken from the reproduction note for SSRN 5209907, which quotes the paper. Not a result this repository has run |
| **Proposal** | A choice this page recommends. The paper leaves it unstated, or the code does not do it yet |

No Concretum backtest was run for this page. No database was queried.

## Why the published rule does not fit

**Spec.** The model is long or flat on daily closes. For each lookback `n` in {5, 10, 20, 30, 60, 90, 150, 250, 360}:

- Enter or stay long when the close equals the `n`-day closing high (the window includes today).
- Exit when the close is at or below a trailing stop.
- Otherwise keep yesterday's position.
- The stop used tomorrow is `max(today's stop, today's Donchian mid)`. It never moves down. On a new entry the stop starts at that day's mid. While flat, the stop is irrelevant and the next entry starts it again.
- Size `w_n = min(0.25 / σ_t, 2) × Pos_n`. `σ_t` is the asset's own 90-day annualized volatility, shared across lookbacks. The paper's only cap is 200%.
- The book is the equal-weight average of the nine `w_n`, not a vote. The weight at the close of day `t` earns the asset's return on day `t+1`.
- Rebalance when a trend signal changes, immediately. Rebalance a volatility-driven gap only when it exceeds 20%. Results after the paper's §5.1 are net of 10 bps plus that threshold.

**Spec**, authors' own figures, net of 10 bps and the 20% threshold, full sample (their Table 3):

| Coin | From | CAGR | Vol | Sharpe | Sortino | Max drawdown | MAR |
|------|------|------|-----|--------|---------|--------------|-----|
| BTC | Jan 2015 | 30% | 17% | 1.56 | 1.23 | 19% | 1.15 |
| ETH | Aug 2015 | 27% | 16% | 1.51 | 1.22 | 15% | 0.96 |
| BNB | Jul 2017 | 17% | 15% | 1.06 | 0.99 | 17% | 0.77 |

BTC's sample in the paper runs from 1 Jan 2015 to 19 Mar 2025. ETH and BNB start at the later of Jan 2015 and the listing date. The authors' blog restates the BTC line as CAGR 30%, Sharpe 1.56, max drawdown 19%. These numbers are not a target for this platform and have not been reproduced here.

Gross of costs, their Table 1 Combo on BTC is CAGR 30%, vol 17%, Sharpe 1.58, Sortino 2.03, max drawdown 19%. The same note flags three inconsistencies inside the paper, which a reproduction should leave as printed: Combo MAR is 0.88 in Table 1 and 1.15 in Table 3 while 30/19 is about 1.58 either way; BTC Combo Sortino falls from 2.03 to 1.23 when Sharpe barely moves; the text's 5-day gross CAGR (34%) does not match Table 1 (36%).

**Spec**, the note's own calculation, not the authors': on Binance spot daily closes from 2017 through 26 Sep 2026, `0.25 / σ_90` with simple returns, sample standard deviation, and √365 never exceeded 1 for BTC, ETH, or BNB (max raw weights 0.90, 0.82, 0.96). A spot cap of 1× is then almost the same model as the paper's 200% cap, at a 25% target, on those three coins, in that window. The 200% cap can still bind in a quieter sample the note did not measure (BTC 2015–2016 is the obvious one). Raising the target vol is when a 1× cap starts to bind.

## What the engine does today

### Positions are −1, 0, or +1

**Read.** `SignalDirection` in `quant/strategy/signals.py` (`momentum_band_signal`, `reversion_band_signal`, `momentum_bounded_signal`, `reversion_bounded_signal`, and the four `*_long_only` wrappers) writes 1, −1, or 0 from the current indicator value and a threshold. `_long_only` clips negatives to 0 and leaves +1 in place. Nothing in those methods reads the previous position.

**Read.** `TechnicalAnalysis` in `quant/strategy/indicators.py` is SMA, EMA, RSI, Bollinger z-score, and stochastic %D. Stochastic uses High, Low, and Close. There is no close-only Donchian channel, no rolling max of the close, and no realized-volatility series.

**Read.** The drawer stops at two factors. `addFactor` in `frontend/src/components/ConfigDrawer.tsx` returns when `factors.length >= 2`, and the Add Factor button renders only while `factors.length < 2`. `OptimizeRequest.factors` in `quant/schemas/backtest.py` has a minimum length of 1 and no maximum. `combine_positions` stacks however many arrays it is given; `tests/unit/test_strat.py` already calls it with three. Decision #2 recorded "max 2 substrategies initially." The Python path can hold nine. The page that submits a backtest cannot.

### PnL, fees, and the next bar

**Read.** `Performance._compute_pnl_columns` in `quant/strategy/performance.py`:

- `chg` is `price.pct_change()` (simple close-to-close). The backtest frame's `price` column is the close (`quant/strategy/backtest_service.py` sets it from the series `v`; `PriceBarService` sets it from the bar close).
- Yesterday's `FinalPosition` earns today's `chg`.
- Turnover is `|FinalPosition − prior|`, and only when both values are finite. Fee is turnover times `fee_bps / 10_000`. The default is `DEFAULT_FEE_BPS = 10.0`.
- A missing prior is not a trade, so the first finite position pays no fee. The [backtest review](2026-09-25-backtest-review.md) left that rule as it is.

`Objective._sharpe` in `quant/strategy/objective.py` uses the same turnover and the same `prior × chg − fee` line, then the same Sharpe (`mean / std × sqrt(trading_period)`, sample std, undefined below `Performance.MIN_METRIC_OBS` of 60).

**Read.** For a weight that is exactly 0 or exactly 1, the weight of a fully invested book does not drift: 100% of NAV stays in the coin without a trade, and 0% stays in cash. The formula never marks a weight between those two. Putting a fraction such as 0.4 into `FinalPosition` and leaving the formula unchanged would earn `0.4 × chg` and would charge the fee on every change of that number. It would also put the book back on 0.4 at every bar, with no extra fee, whenever the signal repeats 0.4. That is a free rebalance back to the target. The paper's 20% band exists so that rebalance is not free and not daily.

**Inferred.** The drift of a weight `w` after a simple return `r`, with the rest of NAV in cash, is `w * (1+r) / (1 + w*r)`, provided `1 + w*r > 0`. At `w` of 0 or 1 this equals `w` again. At `w = 0.5` and `r = 0.10` it is about 0.524. The code does not compute it.

### Combining factors

**Read.** `Performance._compute_multi_factor_outputs` and `MultiFactorObjective.__call__` both call `combine_positions(..., strengths=indicator_values)`. The strengths are the raw indicator readings. With strengths, a bar where the factors disagree takes the sign of the most convicted non-flat factor (`_combine_and`, `_strongest_sign`). Conviction is a past-only percentile rank (`_conviction`).

**Checked.** `test_and_one_flat_gives_flat` calls `combine_positions` without strengths: a long beside a flat stays flat. `test_and_strength_ignores_flat_factors` calls it with strengths: the flat factor drops out and the remaining sign wins, so one long and one flat become long. The backtest and the search always pass strengths, so they take the second test.

#### The long-only AND path

**Read and inferred from the two tests.** A long-only factor is in {0, +1}. On a bar where one factor is +1 and the other is 0, `_combine_and` does not see unanimous +1, does see a non-zero factor, and with strengths writes +1. `test_or_any_long` writes +1 for the same inputs under OR. Two long-only factors combined with AND, on the path the engine actually runs, match OR.

**Checked.** FILTER with two factors returns the second factor when the first is non-zero, and 0 when the first is 0 (`_combine_filter`, `test_filter_gate_active_uses_signal_direction`). Two long-only factors are then +1 only when the gate is +1 and the signal is +1. That is the AND a long-only pair needs.

The [indicators guide](../guides/indicators-strategies.md#conjunction-modes-multi-factor) describes AND as "only when all factors agree," which is the no-strengths path. This proposal does not change AND. An averaged ensemble has to be a new combiner. Building it on top of AND would average the wrong series for long-only factors, because AND has already turned "one of them is long" into "the book is long."

### Walk-forward

**Read.** `WalkForward.run` in `quant/strategy/walk_forward.py` cuts every symbol with `iloc[:split_idx]` and `iloc[split_idx:]`, optimizes on the first piece, and scores the second piece with a fresh `Performance`. Indicators on the out-of-sample piece start with no bars from before the cut. The [backtest review](2026-09-25-backtest-review.md) records that cut, and what promotion does with the full-sample and out-of-sample Sharpes. A stop carried into the cut would be dropped the same way: the out-of-sample replay would begin flat.

### Live orders

**Read.** `compute_latest_position` in `quant/strategy/live_service.py` builds `Performance` on a lookback window and returns the last finite `FinalPosition`. `live_lookback_bars` is `max(window) * 3 + 60`. A 360-day window asks for 1,140 bars, not the whole history.

**Read.** `LiveApplyOrchestrator` in `quant/trade/live_apply.py` takes that float and orders `deployment.qty`, a fixed size stored on the deployment. It does not multiply by the signal. `TradeAdapter.intended_side` in `quant/trade/adapters/base.py` sets `sig = int(round(signal))` and then chooses BUY, SELL, HOLD, OPEN_SHORT, or CLOSE_SHORT. A signal of 0.4 rounds to 0. A signal of 0.6 rounds to 1. A position that is already long and a signal that is still positive is HOLD, so a move from 0.6 to 0.9 sends nothing.

**Read.** `CcxtTradeAdapter.execute_action` buys or opens `qty` (the deployment size) and sells or covers `abs(position_qty)` (the whole holding). For a spot instrument, `CcxtTradeGateway.fetch_position_qty` is the base-coin balance, not a signed contract (`_base_balance`). There is no order that buys or sells the gap between the current coin balance and a target fraction of NAV.

**Inferred.** A binary 0/1 signal can already travel this path. A fractional signal would be rounded to all-in or all-out, or ignored because the account is already long. That is the wrong order, not a smaller version of the backtest.

## What can be run before the upgrade

**Read.** A single long-only threshold rule is expressible today: one indicator, `momentum_long` (or another `*_long_only` function), position +1 or 0, fee on unit turnover, next-bar return. That is the BTC daily Bollinger book already written up in [Crypto spot — baseline improvements](../research/crypto-spot-baseline-improvements.md). It is the right thing to run while this proposal is open. It is a different rule from a Donchian.

**Read.** A 1× Donchian with one lookback and a plain mid-line exit is not expressible, ratchet or not.

- The entry is "close equals the max of the last `n` closes, including today." No indicator returns that max. Stochastic %D is a smoothed position inside the High/Low range, and a bounded momentum signal is long only while %D stays above the threshold. It does not stay long after the breakout bar until a mid-line is hit.
- The bars between entry and exit are `Pos(t) = Pos(t−1)`. Every `SignalDirection` method ignores `Pos(t−1)`. The [adding-strategies guide](../guides/adding-strategies.md) shows the same signature: `(indicator, threshold) → {−1, 0, 1}`.
- A non-ratcheting exit ("flat when close ≤ today's mid, and only if we were already long") is the same memory. "Long whenever close > mid" would be stateless, and it is still not the paper: it is long through the upper half of the channel without a breakout, and it needs a mid-line we do not compute. Bollinger `z > 0` is close above the SMA, which is a third rule.

**Proposal.** Do not grid-search a Bollinger stand-in and compare the Sharpe to the table above. The comparison would treat two strategies as one. The slice that unblocks a real single-lookback Donchian, plain exit or ratchet, is [Proposal C](#proposal-c-a-stop-that-remembers) at weight 1, before A and B.

## Proposal A — fractional weights

**Proposal.** `FinalPosition` may be any real number in **[−1, 1]**. A spot, long-only book clips the target to **[0, 1]** before the fee and the threshold. The paper's 200% cap stays out of scope: this engine's general range remains [−1, 1], and the spot book cannot borrow to reach 2.

The fee stays the one already in `_compute_pnl_columns`: charge `fee_bps / 10_000` times the absolute change in weight. What changes is which weight is "current."

**Proposal.** Keep a held weight, separate from the target:

1. The weight that earns `chg[t]` is the held weight decided at the previous close.
2. After that return, the drifted weight is `w * (1+r) / (1 + w*r)`. At 0 and at 1 this equals `w`, so a unit long/flat book does not move and does not trade because of price drift.
3. The target is computed from the close of bar `t`.
4. Trade to the target when a **position state** changes (any sub-model enters or exits), even if the weight gap is inside the band. Also trade when the gap is a volatility-driven drift past the threshold. Otherwise the held weight becomes the drifted weight, and the fee on that bar is zero.
5. Default threshold: relative, on the combined target, `|w_drift − w_target| / max(|w_target|, ε) > 0.20`. An exit to a zero target is a position-state change, so the ratio is not how an exit fires.
6. On a signal-change bar, trade to the full new target, including whatever volatility gap has accumulated. The paper requires the signal change to trade immediately. Whether that trade also absorbs the volatility gap is **Spec** unstated; this is the choice the reproduction note recommends, and it is the one to implement first. An absolute band of 0.20 of NAV is a second setting, not the default. The paper does not say which definition it used.

**Proposal.** When every weight is in {−1, 0, +1} and no threshold is configured, the pnl series matches today's `_compute_pnl_columns` and `Objective._sharpe`, including the unpaid first entry after NaN. That keeps stored unit-position Sharpes comparable. The [hygiene proposal](2026-09-25-backtest-data-hygiene-proposal.md) is what a formula change does to old `BT.RESULT` rows; this slice should not create another one.

**Inferred.** A vol target that updates every day, fed through the current formula with no threshold, pays 10 bps on every small `|Δw|`. On a daily crypto book that can remove the edge the table is reporting. The threshold is part of A, not a later option, if the goal is the paper's net results.

## Proposal B — an average, then a volatility weight

**Proposal.** A new conjunction, seeded in `REFDATA.CONJUNCTION` the same way AND, OR, and FILTER are (the dropdown rule in `AGENTS.md`). Name it by what it does: average the sub-model weights. Do not fold it into AND.

For `N` sub-models with weights `w_n` already scaled, the book is `w = (w_1 + … + w_N) / N`.

A vote of those same weights is a different book. Four of nine long, each at scale `s`, is an average of `4s/9`. A majority vote is 0 until five are long, then `s`. The paper is the average. The nine lookbacks are a fixed list, not nine axes of `ParametersOptimization`. A Cartesian product of nine window grids is the search the worker is built to run (`optimize_multi` in `quant/strategy/optimizer.py`), and it is the wrong search for this recipe. If anything is searched, search a small set: target vol, vol lookback, threshold. Leave the lookback list written down.

**Proposal.** The sizer, applied per sub-model before the average, because the paper scales each `Pos_n` and then averages:

```text
w_n = min(target_vol / σ_t, cap) × Pos_n
```

- `σ_t`: sample standard deviation of simple close-to-close returns over `vol_lookback` bars, times `sqrt(trading_period)`. Pandas `rolling.std` and `Objective._sharpe` already use sample std (`ddof=1`). Crypto `trading_period` is 365. The paper does not state return type, sample versus population, or √365 versus √252. Matching the engine's existing std and year length is the default. √252 is a sensitivity, not a second engine.
- `target_vol` default 0.25. `vol_lookback` default 90. Spot `cap` default 1.0. The general signed cap default 1.0, so the product stays inside [−1, 1]. The paper's cap of 2.0 is a recorded alternative, not the spot default.
- `σ_t` is the asset's volatility, one series for every lookback. It is not the volatility of the strategy's own pnl.

**Inferred.** With one shared `σ` and one shared cap, `w = min(0.25/σ, cap) × (fraction of sub-models long)`. The average and the sizer commute in that case. They stop commuting if each sub-model ever gets its own cap or its own `σ`. Implement scale-then-average anyway, so a later per-model cap does not silently change the definition.

The UI change is the factor cap in `ConfigDrawer`: a fixed ensemble of nine is a recipe, not nine clicks on Add Factor. How that recipe is selected (a REFDATA strategy template versus raising the cap to nine) can wait until C and A score one lookback. Raising the cap without a template would invite a nine-axis grid.

## Proposal C — a stop that remembers

**Proposal.** A Donchian on the close, not on High/Low:

- `up[t] = max(price[t−n+1 : t])`, `down[t] = min(...)`, `mid[t] = (up[t] + down[t]) / 2`. Today is inside the window.
- Entry when `price[t]` is that max. Computing `up` from the same closes makes `price[t] == up[t]` the same test as `price[t]` being the max; do not compare against a separately rounded band.

State per lookback, one row per bar:

| Field | When long | When flat |
|-------|-----------|-----------|
| `in_position` | true | false |
| `stop` | the level the next bar will compare | absent |

Step at bar `t`, using the stop carried in from `t−1`. The paper compares today's close with the stop already known at the start of the day, then ratchets with today's mid for tomorrow.

1. If in position and `price[t] <= stop`, exit. `stop` becomes absent.
2. If flat (including a bar that just exited) and `price[t]` is the `n`-day high, enter. Initial `stop = mid[t]`.
3. If still in the position that was already open, `stop = max(carried stop, mid[t])` when the ratchet is on. A plain mid-line exit writes `stop = mid[t]` instead of the max. Same step, one branch.
4. Otherwise stay flat with no stop.

**Spec.** Same-bar exit and re-entry is unstated. The reproduction note's default is the order above: exit first; re-enter on that bar only if the close is the high and the close is above `mid[t]`. Keep the other order (entry first) as a tested switch. Do not pick it silently.

**Proposal.** One function of `(prior state, price, up, mid, ratchet_on)` produces the next state. The backtest scans forward and writes `in_position` into the series that becomes `FinalPosition` (1 or 0, until A multiplies by the scale). Live calls the same function.

**Read.** Live today replays indicators on a finite lookback and keeps the last value. A stop replay that starts flat at the first bar of that window is wrong when the open trade began earlier. **Spec** Table 2: the 360-day BTC model has 5 trades from 2015 to March 2025, so a trade can last longer than `live_lookback_bars` (1,140 days for window 360). **Proposal.** For a stateful rule, replay from the first stored bar of the fitted series, not from `live_lookback_bars`. The bars are the state. A stop saved on the deployment would be a second copy, free to disagree with a fresh replay after a restart. Daily BTC, ETH, and BNB are small enough that replaying the stored history on each apply is the consistent choice.

The plain single-lookback exit is this step with `ratchet_on` false and the sizer left at 1. That is the interim research can run once C is in the backtest. It is still one lookback, all-in or all-out, and it will not match Table 3.

C does not fit the guide's "add a method to `SignalDirection`" step. That method never receives the prior stop. The indicator can still be a `TechnicalAnalysis` method, seeded through [Adding indicators](../guides/adding-indicators.md), returning the mid (and the entry flag) for the chart. The position has to be produced by the stepper, then optionally scaled by B and held by A.

## Impact

### Live order generation

**Proposal.** Ship A, B, and C in the backtest first. A binary C signal (exactly 0 or exactly 1) may use the current apply path: `intended_side` and a fixed `deployment.qty` already mean all-in or all-out.

A fractional last position must not be applied until the order is a delta. **Proposal.** Until then, refuse the apply when the latest position is not within `_FLAT_EPS` of −1, 0, or +1 (`quant/trade/adapters/base.py` defines that epsilon for the broker quantity; the signal path today uses `int(round(signal))` instead). Rounding 0.4 to flat or 0.6 to a full `deployment.qty` would report a live fill the backtest did not score.

When live sizing is built, the target coin qty is `held_weight × NAV / price`, and the order is the gap to the base balance, subject to the venue minimum the adapter already checks in `_undersized`. Spot NAV is cash plus coin, which this backtest does not read. That is a separate change, and it places real orders. It is the large slice. It does not belong in the same release as the first backtest of C.

Scheduled apply still runs on the forming bar, five minutes before the close. The review states that gap. A Donchian evaluated on a candle that is not finished is a different trade from the daily-close rule. Daily is the milder case. This proposal does not move the apply clock.

### Walk-forward

**Proposal.** Score the out-of-sample segment by running the stepper on the bars before the cut and then keeping pnl only from the cut forward. The prefix warms the channel, the vol window, and the stop. It is not a second chance to pick the parameters. `WalkForward._evaluate` today constructs `Performance` on the sliced frame alone; a stateful rule needs the prefix passed in and the metric slice applied after.

The in-sample search, if it runs at all, still sees only the in-sample bars. A fixed Concretum list does not need that search. Which Sharpe the promotion gate ranks is the review's subject; this page does not move that gate.

### Stored metrics

**Read.** `extract_shredded_metrics` in `quant/queue/result_metrics.py` stores five strategy numbers and five buy-and-hold numbers: total return, annualized return, Sharpe, max drawdown, Calmar. They are defined on a simple-return pnl series. A, B, and C can keep that contract if they only change how `pnl` is built.

**Inferred.** A book that is typically 0.3× to 0.5× invested can post a Sharpe that ranks above a 1× book with a larger payoff. Promotion compares Sharpe across current rows of one strategy lineage. A new conjunction is a new `STRATEGY_NM` and, by decision #63, a new `STRATEGY_ID`. Leave it that way so a vol-targeted ensemble is not a later VID of a unit Bollinger lineage.

Sortino and the paper's MAR are not stored. The review already lists Sortino as a nice-to-have. Matching Table 3's Sortino waits on that. Our Calmar is CAGR over max drawdown; do not rename it to agree with the paper's MAR, which the spec already shows is inconsistent with CAGR/MDD.

No engine-version column exists (PR #59). A result computed by A/B/C is a new row because the config is a new recipe, not because old unit-position rows were recomputed.

### Tests to add

Backtest parity first, in `tests/unit/test_perf.py`, `tests/unit/test_objective.py`, and `tests/unit/test_strat.py`:

| Case | Expect |
|------|--------|
| Weights exactly −1, 0, +1, no threshold | Same pnl as today's `Performance` and `Objective`, including a NaN prior that pays no fee |
| Held weight 0.5, asset return 10%, no trade | Bar pnl 0.05. Next held weight about 0.524, not 0.5 |
| Target moves 0.50 → 0.52, relative band 0.20, position state unchanged | No trade, fee 0, held weight follows the drift |
| Position state flips while the weight gap is inside the band | Trade to the full new target. Fee is `fee × \|target − drifted\|` |
| Spot clip | A negative target becomes 0. A target above 1 becomes 1. Signed mode still allows −0.4 |
| Two weights 1 and 0, average combiner | 0.5. The strengths-based AND of the same long-only pair stays +1, so the new combiner is what changed |
| Shared `σ`, cap not binding, four of nine sub-models long | Combined weight `(4/9) × (target_vol / σ)` |
| Ratchet | While long, stop is non-decreasing. A new entry sets stop to that bar's mid, even if an older stop was higher. Flat carries no stop |
| Plain exit | Stop equals today's mid, and a later lower mid exits |
| Exit and a new high on the same bar | Exit-first default, and one test of the other order |
| Live replay | Last state of a full-history replay equals the backtest's last state on the same bars |
| Lookback shorter than the open trade | A replay that starts flat inside an old trade does **not** equal the full-history state. This is the regression the short window must fail |
| Fractional position offered to apply, before delta sizing exists | Apply is refused. `int(round(0.4))` must not be the order |

`tests/unit/test_ta.py` covers the Donchian window: today included, mid halfway between max and min of closes, NaN until `n` closes exist.

## Effort and risks

| Slice | Work | Effort | Biggest risk |
|------|------|--------|----------------|
| C, backtest, one lookback, weight 1, plain exit and ratchet | Stepper, Donchian on `price`, REFDATA indicator seed, tests. No live qty change | Medium | Out-of-sample scored on a sliced frame, so the stop resets at the cut |
| A, backtest | Held weight, drift, threshold, spot clip. Unit path bit-for-bit when the weight is −1/0/1 and the threshold is off | Medium | Implementing A as "put a float in `FinalPosition`" and charging a fee on every vol twitch, with free rebalance in between |
| B, backtest | Average combiner, shared `σ`, fixed lookback list | Medium | Someone points the existing Cartesian search at nine windows |
| Live delta to a target weight | NAV, base balance, min lot, refuse-or-replace `int(round(signal))` | Large | A rounded fraction sent as a full `deployment.qty` on a live account |
| Guard | Refuse apply unless the signal is −1, 0, or +1, until the delta path exists | Small | Shipping A or B to a deployment that still uses `intended_side` |

Recommended order: C at 1× so a single-lookback Donchian can be checked by hand; then A so the fee and the band are real; then B with the lookbacks fixed; live sizing last, and not in the same release. The guard ships with the first build that can emit a non-unit position, even if that build is backtest-only, so a saved config cannot be applied by the scheduler.

### Risks that are easy to miss

- **Paper gaps, marked as choices.** Annualization, the exact 20% (relative or absolute, combo or sub-model, drifted or not), and same-bar entry are **Spec** unstated. The defaults above are proposals. A match to Table 3 is not evidence that the unstated choice was the authors'.
- **1× versus 200%.** At a 25% target and √365, the spec's own 2017–2026 check says the spot cap rarely binds on BTC, ETH, and BNB. That check is not the authors' result, and it does not cover 2015–2016 BTC.
- **Next-bar timing.** The engine already earns tomorrow's return on today's position. That matches the paper's primary timing (weight at the signal close, earn the next day's return). A one-bar delay is a research sensitivity, not a change this proposal requires.
- **AND left as it is.** Long-only AND on the strengths path behaves as OR. FILTER is the AND that works. Fixing AND is a separate decision; doing it inside B would move every stored two-factor long-only result.
- **Identity and promotion.** New combiner, new name, new `STRATEGY_ID`. Do not replay old unit-position rows through the drift formula.

## What this page did not read

- The paper PDF itself. Figures and rules are from the reproduction spec, which cites the paper's sections and tables. Where that spec says the paper is silent, this page says **Spec** unstated.
- Production rows, broker balances, and a live apply. The order path is from the source, not from a fill.
- Whether `live_lookback_bars` on a deployed strategy has ever truncated a multi-year trade. The formula was read. The Concretum trade count was not run here.
- PR #58's branch as an unmerged review. The PR is merged; the long-only AND behavior was read from `combine_positions` and `tests/unit/test_strat.py` on `9c1af3619`.
