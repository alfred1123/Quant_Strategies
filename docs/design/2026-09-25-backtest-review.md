# Backtest review — 2026-09-25

**Doc type:** platform review
**Status:** open findings. This page records the review. It does not change the engine.
**Reviewed:** `main` at `731a93487` (2026-09-25), including the Sharpe-ideas research pages that had just landed.

A read of the backtest and live-apply path, plus the unit tests and one Yahoo backtest. Correctness items come first, then engineering, then nice-to-haves. Each item names the file, why it matters, a rough effort (small, medium, or large), and whether it was confirmed by running code or found by reading it.

This is not a decision-log entry. Adopting any of the fixes is a later change, and a procedure or schema change still needs its own changeset.

## Overview

Quant Strategies is a production backtesting and live-trading platform. Strategies are indicator rules (Bollinger z-score, SMA, EMA, RSI, stochastic) turned into positions of −1, 0, or +1, searched on a parameter grid, and optionally checked with one in-sample / out-of-sample split. The queue worker writes the result to Postgres, promotion picks a best version, and a scheduler can send that signal to Bybit or Binance.

The latest product work moves scheduled apply to five minutes before the bar closes, and the research wiki now lists Sharpe ideas (momentum filters, volatility, funding and basis, microstructure) next to the daily BTC Bollinger baseline. That baseline is quoted at about a 1.48 Sharpe in [Crypto spot — baseline improvements](../research/crypto-spot-baseline-improvements.md). Those research pages are hypotheses. The measurement issues below apply to any Sharpe this engine prints for them.

Two things in the engine are already in good shape, and the review does not reopen them:

- **Next-bar fill on a finished close.** A position decided on bar *t* earns the return from *t* to *t+1*. Confirmed on a five-bar series that rises 10% every day: the signal on the first close earns the next bar’s 10%. See `quant/strategy/performance.py` lines 270–274.
- **Compounded equity.** Simple returns compound with `(1 + pnl).cumprod()`, and drawdown is read off that curve. The unit tests in `tests/unit/test_perf.py` cover the cases that used to report drawdowns above 100%. Rows stored before that worker was deployed still carry the old figures. The cleanup is proposed in [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md).

## What I ran

Dependencies came from `requirements-dev.txt`. No local Postgres was available, so the database integration tests did not run. The frontend suite was not run.

| Check | Result |
|---|---|
| `python -m pytest tests/unit/` | **1610 passed**, 8 skipped. Two skips are the disabled `/backtest/data` route (`tests/unit/test_api.py`). Six are Liquibase baselines marked reference-only (`tests/unit/test_liquibase_changelogs.py`). |
| `python -m pytest tests/integration/test_backtest_pipeline.py` | **54 passed** on synthetic data. CI does not run this file. |
| `python -m quant.cli --symbol BTC-USD --start 2023-01-01 --end 2024-01-01 --window 20 --signal 1.0 --no-grid` | Yahoo returned 365 daily bars. The last bar is **2023-12-31**. Bollinger momentum 20 / 1.0: total return **−14.9%**, Sharpe **−0.40**, max drawdown **26.9%**. Buy-and-hold on the same window: **+86%**, Sharpe **1.74**. |
| Small scripts against `Performance` and `combine_positions` | Confirmed the volume, opening-fee, tie-break, chart-split, SMA-always-long, and short-ruin cases below. |

The CLI run is a real 2023 path, not a synthetic one. A plain Bollinger band on daily BTC lost money in a year when holding BTC was a Sharpe of 1.74. That does not by itself say the engine is wrong. It does say a full-sample Sharpe above zero is a weak reason to trade.

## Correctness

### 1. Promotion trades the full-sample best Sharpe

| | |
|---|---|
| Where | `quant/strategy/backtest_service.py` lines 550–569; `quant/queue/worker.py` lines 158–166; `quant/promotion/evaluate.py` lines 39–40; seed in `db/liquidbase/refdata/releases/archive/1.3.0-promotion-metric.xml` lines 17–21 |
| Evidence | Found by reading |
| Effort | Medium |

`run_optimize` searches the whole date range, stores that trial as `performance.strategy_metrics`, and optionally attaches a walk-forward block beside it. The worker then calls promotion on that payload. `_extract_metric` reads only `performance.strategy_metrics`. It never reads `walk_forward.oos_metrics`.

The hard gates are Sharpe > 0 and max drawdown ≤ 40%. Nothing requires the out-of-sample Sharpe to be positive, and nothing requires the strategy to beat the buy-and-hold columns that are already shredded onto `BT.RESULT`. The drawer defaults walk-forward on, so the out-of-sample number is often already sitting in the result. [Decision #33](../decisions.md) and the [Phase 0.1 sign-off](../archive/phase-0/phase-0.1-signoff.md) already recorded the live BTC candidate this way: full-sample Sharpe 1.19, walk-forward out-of-sample Sharpe negative, and a note to defer live apply. The parameters that can still be promoted are the in-sample maximum.

That maximum is taken over a grid of about 200 cells on the daily defaults (windows 5–100 step 5, signals 0.25–2.5 step 0.25). The best cell of 200 noise Sharpes is biased high. Walk-forward, when it runs, is one cut in `quant/strategy/walk_forward.py` lines 106–147, not a rolling walk. The out-of-sample slice is `iloc`’d off the frame, so indicators restart with no warm-up from the in-sample history, and the equity curve stored for the walk-forward is the full sample run with the in-sample parameters. The parameters promotion keeps are the full-sample best, which can be a different pair.

Why it matters: this is the number that becomes a live order. A strategy can clear the gates, become the best version, and still have failed the hold-out window the UI already computed.

### 2. A one-factor volume strategy is silently a price strategy

Fixed. The single-factor path now reads `SubStrategy.data_column` the same way the multi-factor path does. Stochastic still scores High, Low, and Close.

| | |
|---|---|
| Where | `quant/strategy/performance.py` lines 190–205; `quant/strategy/objective.py` lines 121–128. The multi-factor path that does honour the column is `performance.py` lines 168–174. |
| Evidence | Confirmed by running |
| Effort | Small |

On the same symbol, the single-factor path never reads `SubStrategy.data_column`. It uses the frame’s `factor` column, and the fetch path sets that column to the close. A 120-bar SMA with `data_column="Volume"` matched the price SMA (last value 93.87) and not the volume SMA (1210). The same column is honoured once there are two factors.

[Crypto spot — baseline improvements](../research/crypto-spot-baseline-improvements.md) says volume-as-input works today (`COLUMN_NAME = Volume`). A one-factor volume experiment does not. The optimizer and the reported Sharpe agree with each other, so the bug is invisible in the parity tests: both sides ignore the column.

Stochastic has the same shape. `get_stochastic_oscillator` in `quant/strategy/indicators.py` lines 54–63 always uses High, Low, and Close, and never the factor series. Selecting volume as the input of a stochastic still scores the price range.

Why it matters: the research notes tell a reader they can point a factor at volume. A one-factor run will backtest the close and label the result as if it had used volume.

### 3. Multi-factor tie-breaks use the future

| | |
|---|---|
| Where | `quant/strategy/signals.py` lines 99–116, called from `quant/strategy/performance.py` lines 225–228 and `quant/strategy/objective.py` lines 159–161 |
| Evidence | Confirmed by running |
| Effort | Small |

When factors disagree, the winner is whichever reading is further from the median of its **full-sample** percentile. `_conviction` sorts the whole column, including bars after the one being decided.

On a 30-bar series the two factors conflicted only on bar 0. That bar’s combined position was **+1**. Adding two later spikes to factor A, and changing nothing about bar 0, flipped the same bar to **−1**. The same flip showed up for both OR and AND. FILTER disagreements go through the same rank. Bars where every factor already agrees are unaffected.

Live evaluation ranks inside the lookback window only, so a tie-break at apply time will not match the backtest that promoted the strategy.

Why it matters: any multi-factor recipe that spends time in conflict — the FILTER gates in the new research notes included — is scored with a look at the future, and the live order will not reproduce that score.

### 4. Live orders are not the fill the backtest measures

| | |
|---|---|
| Where | `quant/trade/brokers/ccxt/config.py` lines 134–138; `quant/trade/bar_source.py` lines 102–107; `quant/market_data/service.py` lines 648–651; fee and pnl in `quant/strategy/performance.py` lines 101 and 270–274 |
| Evidence | Found by reading. [Decision #65](../decisions.md) and [decision #81](../decisions.md) already name the gap. [ccxt bar timezones](ccxt-bar-timezones.md) says backtest PnL was left unchanged on purpose. |
| Effort | Medium |

Bybit is wired as `default_type="linear"` (USDT perpetuals). The research product and the default fee of 10 bps are Bybit spot taker, documented under [Transaction costs](../guides/indicators-strategies.md#transaction-costs). The backtest charges that one fee on close-to-close turnover. It does not charge funding, borrow, or slippage. A perp long held through a positive funding regime pays a cost the Sharpe never saw. The new [funding and basis](../research/funding-basis-carry.md) notes describe that cashflow as a research input. The live adapter can already be on the perp while the backtest is still the spot close.

Separately, scheduled apply runs five minutes before the close and appends the still-forming candle (`include_forming=True`) before sending the order. The backtest enters on the finished close and earns the next bar only. Five minutes is a small slice of a daily candle and about eight percent of an hourly one. A manual Apply in the middle of the day uses a half-built daily candle. The signal inputs (high, low, close, volume) are not the values the completed bar will have, and the fill happens before the close the backtest assumed.

Why it matters: scheduled apply now uses this path. A Sharpe measured on spot closes is not the pnl of a linear-perp order sent five minutes before the bar finishes. Daily BTC is the milder case. Hourly, and any manual mid-bar apply, are not.

### 5. The first entry after a NaN position is free

| | |
|---|---|
| Where | `quant/strategy/performance.py` lines 270–274 |
| Evidence | Confirmed on the 2023 BTC CLI run |
| Effort | Small |

Turnover is `|position − position.shift(1)|`. The shift of the first valid position is NaN, so that bar’s trade and pnl are NaN and the opening fee is never charged. Later changes, including a flat-to-long after a real zero, are charged. A long-to-short is correctly two units of turnover.

On BTC-USD Bollinger 20 / 1.0 for 2023, the first position is +1 on 2023-01-20 with a NaN trade. Later turnover sums to 81, which is 8.1% of notional at 10 bps, and does not include that open. On a clean series the miss is one side, 10 bps, once per spell that begins from NaN. A hole that writes a NaN into the middle of the series skips the re-entry the same way.

Why it matters: it will not invent a 1.5 Sharpe on a multi-year daily run. It does make every backtest a little cheaper than going live, and the 2023 sample shows the miss on a real series, not only on a toy one.

### 6. Arithmetic Sharpe can rank a ruined short, and SMA/EMA band signals are buy-and-hold

| | |
|---|---|
| Where | Equity floor in `quant/strategy/performance.py` lines 57–72; Sharpe in lines 306–317. SMA/EMA levels in `quant/strategy/indicators.py` lines 23–31. Band comparison in `quant/strategy/signals.py` lines 243–248. |
| Evidence | Confirmed by running |
| Effort | Small |

The search maximizes `mean / std × sqrt(trading_period)` on the raw per-bar pnl. Total return and CAGR use the equity curve, which floors a bar of −100% or worse at zero and stays there. A series of one −150% bar and then eighty +5% bars finished at **−100% wealth** with an arithmetic Sharpe of **+3.42**. Reaching −100% in one bar takes a short and a one-bar move of about 100% or more, so a long-only spot book will not hit it. A short grid can still crown a trial whose compounded wealth is zero.

SMA and EMA return a price level. `momentum_band_signal` goes long when that level exceeds a threshold of order 1. On a rising line every post-warmup position was +1, and the strategy Sharpe equalled buy-and-hold. The [indicators guide](../guides/indicators-strategies.md) already warns that SMA/EMA plus a band threshold is not a meaningful pair. The grid will still search it, and promotion will still accept it whenever buy-and-hold itself clears Sharpe > 0.

Why it matters: the objective and the wealth curve answer different questions after a ruinous short bar, and a price-level indicator can be promoted as a strategy when it is the benchmark.

### 7. The walk-forward chart marks the split one warmup late

| | |
|---|---|
| Where | `quant/strategy/backtest_service.py` lines 502–506 |
| Evidence | Confirmed by running |
| Effort | Small |

The in-sample and out-of-sample metrics use the true cut (`WalkForward.split_idx` on the original frame). The chart drops leading NaN cumulative rows and then indexes that shorter frame with the original split index. With a window of 20 and a 70% split, the marker landed on 2020-06-09 instead of 2020-05-20, twenty bars later. The plotted out-of-sample region is short by the indicator warmup.

Why it matters: someone reading the chart will think the hold-out starts later than the metrics did. The numbers in the table are the ones to trust until this is fixed.

## Engineering

### 8. Dependencies are not pinned

| | |
|---|---|
| Where | `requirements.txt` (bare names, except `redis>=8`); `requirements-dev.txt` pulls that file in and adds unpinned `pytest`, `pyyaml`, and `mkdocs-material` |
| Evidence | Found by reading |
| Effort | Small |

A later pandas, numpy, or ccxt release can change rolling variance, the Sharpe the parity tests lock in, or the order payload the adapter sends. There is no lockfile. The unit tests passing on today’s resolver does not freeze that resolver.

Why it matters: a backtest re-run months later, or a container rebuild, can move a reported Sharpe without a commit in this repo.

### 9. CI skips the pipeline test, and a failed walk-forward is dropped

| | |
|---|---|
| Where | `.github/workflows/tests.yml` lines 28–29 run `tests/unit/` only. The swallow is `quant/strategy/backtest_service.py` lines 562–569. Per-trial failures become −∞ in `quant/strategy/optimizer.py` lines 184–191. |
| Evidence | The unit-test CI scope was read from the workflow. The pipeline file was run by hand (54 passed). The swallow was read. |
| Effort | Small |

`tests/integration/test_backtest_pipeline.py` is the test that drives fetch-shaped frames through `Performance`, the optimizer, and `WalkForward`. It is green and unrun in CI. Database integration tests skip cleanly when `QUANTDB_URL` is unset; this file does not need a database.

`run_optimize` logs and swallows an exception from the inline walk-forward, then returns `walk_forward` empty. The job can still complete. The UI treats a missing block as “walk-forward was off,” including when it was on and threw. Inside the search, an exception on one cell is stored as Sharpe −∞, so a broken indicator looks like a bad parameter.

Why it matters: the check that would have caught a regression in the full pipeline is optional, and a walk-forward crash is easy to miss because the optimize job still succeeds.

### 10. The CLI year length is a separate constant

| | |
|---|---|
| Where | `quant/cli.py` lines 78–80 (`crypto` 365, `equity` 252). The app scales `trading_period` by bars per day from the drawer (365 daily, 8,760 hourly). |
| Evidence | Found by reading. A separate check of annualization scaling was run and is described below. |
| Effort | Small |

The CLI has no bar-interval flag, so it cannot express an hourly run at all. A CLI daily crypto Sharpe uses 365 even if `REFDATA.ASSET_TYPE` later changes. The app and the CLI can print different Sharpes for the same daily recipe only if those constants diverge. Today they match for daily crypto and daily equity.

Annualization itself was checked rather than assumed. A slow 48-hour signal on independent hourly noise produced an hourly Sharpe of 0.65 when annualized with √8760, and 0.66 when the same wealth path was compounded into daily bars and annualized with √365. The √(bars per year) scaling is consistent when bar pnl is close to independent. It overstates when bar pnl is strongly autocorrelated (slicing one daily shock into 24 identical hours inflated the annualized Sharpe by about 6.6× in a constructed series). A daily-sampled Sharpe next to the native one, on hourly jobs, is a useful check. It is not a reason to replace the formula.

Why it matters: the CLI is the path the guides still give for a walk-forward sign-off. It cannot see the cadence the app now treats as part of a strategy’s identity.

### Secrets

No API keys, `.env` files, or private keys were found in the tree. `.env` is gitignored. Broker credentials are Fernet-encrypted in the database. The root `README.md` line 47 publishes the production host `http://52.221.3.230/`. That is an operational address in a public file, not a key. This note does not edit that README.

## Nice to have

### Sortino, and a buy-and-hold excess gate

The 2023 CLI sample is the illustration: strategy Sharpe −0.40, buy-and-hold Sharpe 1.74. Long-only crypto Sharpe treats the right tail as risk. [Measurement hygiene](../research/crypto-spot-baseline-improvements.md#4-measurement-hygiene) already asks for Sortino, and the buy-and-hold metrics are already stored. Putting “must beat buy-and-hold out of sample” on the promotion gate is the higher-value half of this item.

**Effort:** small for the metric, medium to make it a gate. **Evidence:** the 2023 comparison was run; the missing metric was read.

### Rolling walk-forward, or a deflated Sharpe

One 50/50 or 70/30 cut still leaves the in-sample winner chosen from about 200 tries. A rolling walk, or a haircut for the number of cells searched, is the usual way to stop the best cell from being the story.

**Effort:** large. **Evidence:** found by reading `quant/strategy/walk_forward.py` and `quant/strategy/optimizer.py`.

### Position size

Signals are fully in or fully out. Fees are `|Δposition| × fee` on a unit position. ATR volatility targeting, which the research notes ask for next, needs a sized position in both the pnl line and the live order.

**Effort:** large. **Evidence:** found by reading. The [Sharpe ideas index](../research/sharpe-ideas-index.md) states the same limit.

### Point-in-time equity data

Yahoo uses `auto_adjust=True` (`quant/data/sources.py` lines 195–197), so split adjustment uses the factors known today. Alpha Vantage daily uses the unadjusted close (`sources.py` lines 137–143). Glassnode builds its request window with `time.mktime` (`sources.py` line 91), which is the machine’s local timezone. Crypto research now prefers exchange bars, where this matters less. There is no universe scan, so a classic survivorship bias across a historical constituent list does not arise. Studying only coins that still exist is a selection choice, and venue coverage already refuses a start date before the first stored bar.

The CLI run also showed Yahoo’s `end` date is exclusive: `--end 2024-01-01` stopped on 2023-12-31. Callers who treat the end date as inclusive drop the last day.

**Effort:** medium if equity backtests will be compared across Yahoo and Alpha Vantage. Small to document the exclusive end date. **Evidence:** the exclusive end date was confirmed by the CLI run. The adjustment and timezone differences were read.

### RSI is Cutler’s, not Wilder’s

`quant/strategy/indicators.py` lines 33–45 average gains and losses with a simple rolling mean. TradingView’s RSI uses Wilder smoothing. The same threshold will not fire on the same bars.

**Effort:** small. **Evidence:** found by reading.

## What to do first

1. **Gate promotion on the out-of-sample result, and on beating buy-and-hold.** The walk-forward block is already produced. Promotion throws it away and can mark a full-sample Sharpe winner as best when the held-out window fails. That is the number that becomes a live order. The Phase 0.1 sign-off on the BTC candidate already failed this test. **Medium.**
2. **Make the backtest describe the order that actually goes out.** Charge funding and the perp fee, and fill on the pre-close price, or keep the spot close-to-close research backtest and stop treating a linear-perp, pre-close fill as the same experiment. This is the gap that matters now that apply runs before the bar closes. **Medium.**
3. **Fix the one-factor column bug and the full-sample tie-break.** Both are small. Both make an experiment answer a different question from the one that was asked, and the volume case contradicts the research note that says it already works. **Small.**
