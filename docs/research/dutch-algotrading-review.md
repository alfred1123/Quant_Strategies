# Dutch Algotrading Patreon review

**Doc type:** strategy research  
**Status:** Testable rules have been handed to the AlgoDaemon Quant Researcher; platform results pending.

This page paraphrases a review of the paid [Dutch Algotrading](https://www.patreon.com/dutchalgotrading) Patreon. The strategy write-ups below are rewritten. Performance figures are only those recorded in that review, and each one carries an origin:

- **Author's in-sample Freqtrade claim.** A headline, or a figure read from the author's own backtest export.
- **Reviewer's trade-list check.** A re-sum of the author's closed trades. Not a new backtest.
- **Offline close-only approximation, not a platform result.** A Bybit daily-close stand-in: yesterday's position times today's return, minus 10 bps when the position changes, with Sharpe annualised by √365. Rerun it on AlgoDaemon before relying on it.

The review did not execute the author's code, and it did not send anything to an exchange.

## What the Patreon covers

About 80 posts, from late November 2024 through mid-August 2026. Roughly 30 are strategy tests. The usual pattern is to take an indicator recipe from TradingView or a video, port it to Freqtrade, and backtest it over about five years (the start of 2020 to the start of 2025), on a basket of about 10 to 74 Binance pairs, and on six timeframes from 5 minutes up to 1 day. Each test is wrapped in a management-report PDF and a large profit percentage.

The other posts are tooling (an indicator library, a backtest viewer, a dashboard), explainers for Sharpe, Sortino, Calmar, Treynor, the information ratio, M², and Jensen's alpha, ranking methods (TOPSIS and a fixed-anchor score), a few forward-versus-backtest notes, and league tables of 5-minute scalpers.

There is no walk-forward and no held-out sample, no position-sizing study, and no single-asset BTC, ETH, or BNB study. Results are portfolio-level, compounded, and in-sample.

Three parts are still useful after the red flags below. The author's own multi-timeframe runs: below one hour, almost every variant loses after fees, while 1 day and 4 hours are the timeframes that stay positive often enough to notice. The shape "slow trend gate, then a faster momentum confirmation," which has a close-only form this engine can run. And the scoring posts: a hard reject for too few trades or too deep a drawdown, with TOPSIS used only to rank neighbours that already passed.

## How the author tests

Freqtrade, on Binance spot or USDT-margined futures. The reviewed tests use an in-sample window of about five years and a multi-pair basket. The HalfTrend test, as one concrete case, charges 0.1% on spot and 0.05% on futures, compounds an unlimited stake, and allows up to 10 names open at once. Stops are often missing, or present in the file and left off. The reported percentage is the compounded portfolio, not a unit-position Sharpe on one coin.

That setup does not match AlgoDaemon: Bybit spot, one of BTC, ETH, or BNB, 10 bps, daily bars, a position of 0 or 1, and no basket compounding. A four-digit basket percentage is not a target for a single-coin run.

## Ranked ideas

Order is the review's judgement of expected out-of-sample benefit for BTC, ETH, and BNB daily. Offline Sharpes in this section are the close-only approximation, not platform results. The approximation's sample is Bybit daily closes, BTC from 2020-03-25 and ETH and BNB from 2021-07-01, through 2026-09-25. Its in-sample window is 2021-07-01 to 2024-06-30, and its out-of-sample window is 2024-07-01 to 2026-09-25.

Reference points from that same approximation:

| Reference | BTC in-sample / out-of-sample | ETH | BNB |
|-----------|-------------------------------|-----|-----|
| Buy and hold | 0.65 / 0.51 | 0.58 / 0.19 | 0.69 / 0.51 |
| Round-1 regime (BTC z-score, window 85, above 1.0) | 1.28 / 0.77 | 1.23 / 0.85 | 1.44 / 0.82 |

The review also records current platform hold-out Sharpes, which this page does not remeasure: ETH 1.33 (BTC z-score window 80 above 1.5, filtered by ETH z-score window 30 above 0), BTC 0.87, and BNB 1.03.

| Rank | Idea | Tag | One-line rule |
|------|------|-----|----------------|
| 1 | Two-speed confirmation on BTC | Testable now on AlgoDaemon | Spec A. `FILTER` a slow "close above its average" gate with RSI(14) above 50 or 55. |
| 2 | Enter on a strong stretch, hold until faster momentum dies | Needs backend | Enter when a medium-window z-score exceeds about 1 to 1.5. Exit when a faster z-score falls below 0, or when RSI(14) falls below 50. |
| 3 | The BTC two-speed rule, traded on ETH or BNB | Testable now on AlgoDaemon | Spec B. Both factors read BTC. The position is in the alt. |
| 4 | Two moving-average signs, slow gate and fast signal | Testable now on AlgoDaemon | Spec C, low priority. `FILTER` a slow z-score above 0 with a fast z-score above 0, on the same coin. |
| 5 | Volatility-scaled size on any of the above | Needs backend | Weight = min(1, target volatility / realised volatility) times the signal. The Patreon does not study sizing. This is the generic Sharpe lever. |
| 6 | Fast adaptive average, a momentum oscillator, and a high trend-strength reading | Needs backend | Long when close is above a short adaptive average, a true-strength-style oscillator agrees, and trend strength is above 35. |
| 7 | Three oscillators at once | Needs backend | The literal rule needs RSI, a stochastic, and a MACD histogram together. The close-only stand-in collapses to Spec A, and that stand-in is weak. |
| 8 | Balance of power, CCI, pivot supertrend, cloud, and VIDYA recipes | Needs backend | These need open, high, low, or volume, and stops that remember a level. |
| 9 | Dual RSI, slow above 50 and fast above 50 | Testable now on AlgoDaemon | Rejected. The offline out-of-sample Sharpe is about 0. Do not pursue. |
| — | Fixed-anchor score, TOPSIS, and forward-versus-backtest checks | Validation method | A minimum trade count and a minimum out-of-sample length on the promotion gate. TOPSIS only to choose among robust neighbours. |

**How to read the top of the list.** On BTC, the offline approximation of rank 1 has a plateau. With RSI(14) and a slow window from 50 to 200, out-of-sample Sharpe sits about 0.77 to 1.14, against 0.77 for the round-1 regime rule in the same approximation and against the review's current platform BTC hold-out of 0.87. The review's summary of the expected benefit is a small to moderate lift, about 0.9 to 1.1 out of sample versus that 0.87. The in-sample-best cell of the family (slow window 100, RSI 14, threshold 50) went from an in-sample 1.23 to an out-of-sample 0.91. It is not a new bet. It agreed with the round-1 regime rule on about 87% of days, and the daily P&L correlation was 0.84. Most of the out-of-sample gap versus that regime rule showed up in 2025, where the approximation has this family at 0.20 and the regime rule at −0.78. Treat rank 1 as a robustness candidate for the BTC trend book.

On ETH and BNB, every own-price Dutch proxy in the approximation was worse than the existing BTC-gate strategies. The in-sample-best own-price cell was about 0.29 out of sample on ETH and about −0.34 on BNB. Rank 3 (BTC factors, alt position) is the one worth a single run: the review's ranking puts the offline out-of-sample range at about 0.64 to 1.10, below ETH's current 1.33 and around BNB's 1.03.

The pure two-z-score family (rank 4) is weaker in sample. On BTC its in-sample-best cell (slow 100, fast 26) went from 0.88 in sample to 0.79 out of sample, with a grid-median out-of-sample near 0.79. ETH and BNB in that family were about 0.39 and 0.12 out of sample.

The dual-RSI family fails the approximation everywhere: BTC out-of-sample 0.11 at the in-sample-best setting, with an in-sample versus out-of-sample rank correlation of −0.46, and none of that grid above 1 out of sample. ETH was about 0.01 and BNB about −0.16.

Rank 2 is the idea the engine cannot express. A breakout entry and a looser exit is hysteresis, which is [Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers) of the [backend proposal merged in PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63). A close-only channel, if one is added for that entry, is [Proposal D](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-d-a-donchian-on-the-close). Rank 5 is [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) and [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight). The author's local BTC result for the trend-strength recipe (rank 6) was about +3% over five years on the trade-list check, which is why that row stays low even after a backend exists.

## Where the headlines came from

A short map, so the red flags have a subject. Author figures here are in-sample Freqtrade claims on Binance baskets, not AlgoDaemon results.

| Recipe | Public post | Author's in-sample Freqtrade claim | What the review found |
|--------|-------------|-------------------------------------|------------------------|
| HalfTrend line plus a composite oscillator, daily | [HalfTrend and GodMode](https://www.patreon.com/dutchalgotrading/posts/using-halftrend-151302783) | Futures: total return 652.96%, Sharpe 1.15, max drawdown 39.52%, win rate 37.70%, profit factor 1.21. Spot: return 2640.57%, Sharpe 1.19, drawdown 48.54%, win rate 36.49%, profit factor 1.59. Ten pairs, about 2020–2024. | Trade-list check: spot BTC about +104% compounded over five years, far under buy-and-hold; spot ETH about +372%. About 68% of spot profit from SHIB (26%), DOGE (26%), and SOL (16%). Futures BTC and ETH about −33% and −45%, and the short legs lost. About 45–48% of profit from trades opened in 2020–21. The literal rule needs high, low, ATR, and volume, plus a stateful exit. |
| Channel around a fractal adaptive average | [FRAMA channel](https://www.patreon.com/dutchalgotrading/posts/frama-channel-150506895) | Long-and-short best on 4 hours, hypothetical profit over 1,100%. Long-only best on 12 hours, almost 6,000%. Exports: 12-hour spot 5,844%, Sharpe 0.53, max drawdown 28.5% (relative 44.9%), profit factor 2.74, 264 trades. 4-hour futures 1,150%, Sharpe 1.21, drawdown 30.9%. | Trade-list check: 12-hour BTC about +730% and ETH about +1,113%. SHIB, DOGE, and SOL together about 59% of profit. The short side about −233%. The 12-hour headline was chosen after six timeframes, and its Sharpe is 0.53. |
| Balance of power with a stated reward multiple, daily futures | [Balance of power](https://www.patreon.com/dutchalgotrading/posts/trading-on-of-143867863) | Almost 4,000% profit, 52% wins, profit factor 1.44, described as 50 pairs over five years. Export: 3,886.76%, 1,020 trades, Sharpe 1.21, drawdown 32% (relative 49.6%), on 74 pairs. A PDF from a different run calls 1 hour best, at 7,201.72% with Sharpe 6.15, and lists the daily row as 1,943% with 1,081 trades. | Stops do not hold. One ETH short opened 2020-03-13 at 106.97 was stopped the same day at 213.94 (profit ratio −1.0019). A RUNE trade lost 90.7% and an AVAX trade lost 59% on stops described as trailing. The PDF and the export disagree. |
| Momentum envelope, daily | [Momentum envelope](https://www.patreon.com/dutchalgotrading/posts/momentum-simple-142813272) | Export: 2,343.59%, Sharpe 0.88, drawdown 40.9%, profit factor 2.23, win rate 47.7%, 472 trades, 44 pairs, about 2020–2025. | Trade-list check: BTC about +3%, ETH about +93%, BNB about +598%. The config names more pairs than the result keeps. |
| One MACD cell chosen from more than 150 combinations | [MACD grid](https://www.patreon.com/dutchalgotrading/posts/macd-powerhouse-142405440) | Daily export: 10,259.2%, Sharpe 0.90, drawdown 46.3% (relative 61.5%), 1,071 trades. Four-hour: 975% with drawdown 77%. One hour and faster lost 93–99%. | Trade-list check, daily: BTC +474%, ETH +377%, BNB +101%, compounded across trades. About 162% of the 4-hour profit came from trades opened in 2020–21, so later years lost money as a group. The published lookahead check used 20 signals, and only at 5 minutes. |
| Slow MACD histogram as a gate, fast histogram as the signal | [Slow and fast MACD](https://www.patreon.com/dutchalgotrading/posts/these-settings-140007685) | PDF: best timeframe 4 hours, 1,115.75%, Sharpe 3.30, drawdown 40.4%. Daily row 897%, Sharpe 1.08, profit factor 1.41, drawdown 35%. The post text says drawdowns reached nearly 50%. | The file's default timeframe does not match the 4-hour label, and a pullback condition described in the post is not what the implementation trades. The close-only stand-in is Spec A or Spec C. |
| Fast RSI dip inside a slow RSI uptrend | [RSI pair](https://www.patreon.com/dutchalgotrading/posts/strategies-that-139870107) | Four-hour and daily called optimal. Win rate 21%. | Offline approximation: fails out of sample. BTC out-of-sample Sharpe 0.11 at the in-sample-best setting, and none of the grid above 1 out of sample. |
| Two CCI readings | [CCI pair](https://www.patreon.com/dutchalgotrading/posts/impossible-to-139913914) | Described as better than the RSI variant. Daily called optimal. | CCI uses typical price. Not runnable on close-only factors. |
| Pivot supertrend plus a volume oscillator | [Pivot supertrend](https://www.patreon.com/dutchalgotrading/posts/pivot-supertrend-139332775) | 27,571 dollars, win rate 77.8%, profit factor 1.85, max drawdown 41%. The 4-hour export shows Sharpe 0.85 and Sortino 0.53. | Trade-list check: losing trades are not closed. On the daily run, 10 positions opened in 2021–22 were held to a forced exit on 2025-01-01, from −55% to −97%. With those slots full, the daily run opened 5 trades in 2022, none in 2023, and 20 in 2024. The 4-hour run opened 1 trade in 2022 and none in 2023. Forced-exit losses were about −1,925 USDT on the daily run and −1,991 USDT on the 4-hour run. About 120% of daily profit came from trades opened in 2020–21. The win rate counts the small winners and ignores the bags. |
| Adaptive moving-average cross with RSI | [Adaptive crossover](https://www.patreon.com/dutchalgotrading/posts/im-back-adaptive-138350987) | 35,000% return, CAGR 222%, 7,863 trades, win rate 54.1%, profit factor 1.26, Sharpe 3.29, maximum drawdown 62% in the early period. | 7,863 trades is not a daily system. A Sharpe of 3.29 beside a profit factor of 1.26 is not a credible daily result. The close-only core sits inside Spec A's grid. |

A few other posts were only skimmed from the public text. A vigor-trend post reports 2,385 trades, average profit per trade 2.19%, win rate 42%, profit factor 1.27, and maximum drawdown 37%, without a rule the review could restate. An expanded-cloud daily book is about 15,795 USDT, win rate 38%, profit factor 1.4, and drawdown up to 41%. A VIDYA variant is 2,500 dollars, a 50% win rate, profit factor 1.72, and 482 trades. Sub-hourly systems are out of scope, including a 5-minute VWAP book (win rate 93.43%, profit factor 1.68, profit 3,565.46%) and a 5-minute scalper at 843.80% with Sharpe 5.33. The author's own faster timeframes do not survive fees.

## Hand-off specs

**AlgoDaemon testability:** Specs A, B, and C are as-is. Long only, positions 0 or +1. Two conditions use `FILTER`. A long-only AND currently scores as an OR ([bug B1](../design/2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors)).

| Setting | Value |
|---------|--------|
| Venue and bars | Bybit spot, daily |
| Fees | 10 bps |
| Position | Long only |
| In-sample | 2021-07-01 through 2024-06-30 |
| Out-of-sample | 2024-07-01 through the latest bar |
| BTC extra window | Also report 2020-03 through 2021-06 as a pre-sample check |
| Selection | Choose on the in-sample window. Require at least 70% of neighbours, one grid step away, to have in-sample Sharpe of at least 0.8. |
| Report | Out-of-sample Sharpe, trade count (at least 30), maximum drawdown, and time in market, against buy-and-hold and the current per-coin best |

The neighbour rule and the trade-count floor are the review's translation of the author's scoring post into a selection rule. Sharpes quoted under each spec are the offline close-only approximation, not platform results. The approximation's out-of-sample window ends 2026-09-25; a platform run uses the latest bar.

### Spec A: two-speed trend on BTC

Stand-in for the HalfTrend composite, the slow-plus-fast MACD, and the adaptive-cross core.

- Posts: [HalfTrend and GodMode](https://www.patreon.com/dutchalgotrading/posts/using-halftrend-151302783), [slow and fast MACD](https://www.patreon.com/dutchalgotrading/posts/these-settings-140007685), [adaptive crossover](https://www.patreon.com/dutchalgotrading/posts/im-back-adaptive-138350987).
- Asset: BTCUSDT first. ETH and BNB on their own prices are expected to fail in the approximation. Run them only as a check.
- Signal: `FILTER(gate = close > SMA(ws), which is Bollinger z(ws) > 0, long only; primary = RSI(wf) > threshold, long only)`.
- Sweep, 27 runs: slow window ∈ {75, 100, 150}; RSI length ∈ {10, 14, 21}; threshold ∈ {50, 55, 60}.
- Offline expectation to verify: RSI(14), threshold 50 or 55, slow window 75 to 150, has in-sample Sharpe about 0.80–1.23 and out-of-sample about 0.89–1.14. The in-sample-best cell (100 / 14 / 50) has out-of-sample 0.91. RSI(21) is weaker, about 0.6–0.8 out of sample.
- Promote only if the platform out-of-sample Sharpe is at least 0.95, which is a margin over the review's current BTC best of 0.87, the neighbourhood is robust, and there are at least 30 trades.
- Overlap: about 87% of days match the round-1 BTC z-score (window 85) above 1.0. Treat the spec as a replacement or a robustness check, not as a diversifier.

### Spec B: BTC regime, position in ETH or BNB

The same confirmation idea, with both factors on the BTC close. The review combines it with the existing finding that a BTC gate has worked better for the alts than an own-price gate.

- Assets: ETHUSDT and BNBUSDT. Both factors use the BTC close.
- Signal: `FILTER(gate = BTC close > SMA(ws); primary = BTC RSI(wf) > threshold)`.
- Sweep, 18 runs per coin: slow window ∈ {75, 100, 150}; RSI length ∈ {14, 28}; threshold ∈ {50, 55, 60}.
- Offline expectation: ETH with RSI(14), out-of-sample about 0.72–1.07 (in-sample 0.57–1.32). BNB with RSI(14), out-of-sample about 0.80–1.10 (in-sample 0.58–0.84). RSI(28) can print a high in-sample Sharpe, up to about 1.5, and only about 0.4–0.8 out of sample. That gap is an overfit warning.
- Promote only if the platform result beats the per-coin incumbent recorded in the review: ETH 1.33, which the approximation makes unlikely, or BNB 1.03, which it leaves open. Otherwise log a negative result.

### Spec C: two z-scores, low priority

Stand-in for a slow MACD histogram above zero and a fast MACD histogram above zero. Slow lengths in the post are on the order of 100 and 200. Fast lengths are on the order of 13 and 21. Both factors here are "close above its average."

- Post: [slow and fast MACD](https://www.patreon.com/dutchalgotrading/posts/these-settings-140007685).
- Asset: BTCUSDT. ETH and BNB are optional. The approximation expects them to be poor.
- Signal: `FILTER(gate = own z(slow) > 0; primary = own z(fast) > 0)`.
- Sweep, 12 runs: slow window ∈ {50, 100, 150}; fast window ∈ {10, 15, 20, 26}.
- Offline expectation on this grid: in-sample about 0.44–0.88 and out-of-sample about 0.44–1.08. A wider offline grid had a cell (slow 75, fast 15) at out-of-sample 1.22 with in-sample only 0.71, so it would not be the in-sample pick. The family is weak in sample. Run the grid to keep it or drop it.

### After hysteresis exists

Once a position can stay on until a different exit ([Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers)):

- Enter when z(entry window) > entry threshold, with the entry window in {26, 30, 40} and the threshold in {1.0, 1.5}.
- Exit when z(exit window) < 0, with the exit window in {10, 15, 20}, or when RSI(14) < 50.
- On ETH and BNB, add the BTC regime as the FILTER gate.

That is the channel-breakout idea the review ranks second. A stateless "z above 1.5" rule is a different strategy, and it is not this spec.

## Red flags in the author's results

Summarised from the review. These are reasons not to copy a headline percentage into a promotion case.

1. **The PDF reports repeat one boilerplate block.** All five management-report PDFs examined in the review carry the same lines: 4,442 winning trades and 704 losing trades, expectancy 235.76, long profit of 1,213.20 dollars, a "risk per trade" of 27,289.99 dollars, 7.05 trades per day, an average hold of 3 hours 48 minutes, a max win streak of 117, and a hyperoptimised flag, under a header of 2021-01-01 to 2023-01-01, 45 pairs, spot. Those lines contradict the attached exports, which cover 2020–2025, 44 to 74 pairs, and futures where the test was futures. In that template a printed CAGR of 0.65% means 65%. Treat the PDFs as unreliable. The review treated the JSON exports as the artifacts worth reading.

2. **Every published result is in-sample.** There is no held-out split and no walk-forward. The timeframe was chosen after six were tested. Combinations were chosen on the full sample, including the grid of more than 150 MACD cells.

3. **The pair list is chosen with hindsight, and delistings disappear.** The balance-of-power whitelist includes coins listed in 2024 and 2025 inside a test that starts in 2020. The momentum-envelope config names 49 pairs, while delisted names drop out of the result without comment. Headline profits lean on SHIB, DOGE, SOL, and AVAX.

4. **Profits are front-loaded in the 2020–21 bull market.** Trades opened in those two years account for more than the whole profit in several runs: about 120% on the pivot daily book, and about 162% on the 4-hour MACD grid. 2022 was negative for most of the runs the review checked. On the HalfTrend spot book, about 45–48% of profit came from entries in 2020–21.

5. **Compounding across many open slots inflates the percentage.** Unlimited stake and up to 10 positions produce Calmar readings such as 214, and per-pair drawdowns above 100%, that are accounting artifacts.

6. **Stops that do not stop, presented as risk management.** The pivot win rate depends on never closing the losers. The balance-of-power stop and target, described as a fixed reward multiple, are recomputed every bar. The review's summary is that those stops fail by about 60–100%. The ETH short and the RUNE and AVAX losses above are the examples. Several other strategies have no stop at all.

7. **The short book loses** in every long-and-short export the review checked: the HalfTrend composite, the fractal channel, and the balance-of-power book.

8. **Look-ahead checks were thin, and a backward-fill was missed.** The author's lookahead pass used 20 signals and only the 5-minute bars. Balance-of-power indicators are filled backward, which writes later values into the warm-up bars.

9. **Fills inside the bar are optimistic.** Trailing stops and profit targets, without a finer candle inside the signal bar, can fill at prices the bar may not have traded in that order. The author's own forward-versus-backtest note on one 5-minute system shows the scale. The forward claim is about +110 USDT (about 12%, 458 trades, profit factor 1.5, win rate 77.5%) against a backtest of +660 USDT and 994 trades on the same period. The export confirms 660.61 USDT, 994 trades, and Sharpe 7.80. The forward file was not in the review, so the forward side stays an author's claim. The gap is about six times. The post is the author's [forward-versus-backtest comparison](https://www.patreon.com/dutchalgotrading/posts/can-backtests-be-147801673). That gap is a warning for a later live-versus-backtest reconciliation, not a strategy to trade.

10. **A league table reports the best of several runs.** A 2025 top-10 list of 5-minute to 30-minute scalpers, 44 pairs, in a year the review records as a −36% market, includes one modified scalper at 435% (win rate 96.8%, Sharpe 6.4) and another at 234.75% (Sharpe 11.73), while a combined entry is −5.45%. The review found more than one result for the same name (351% and 435%), filename mismatches, and one strategy tested only from mid-2025 into early 2026. Not a daily spot book.

Across the same posts, variants at one hour and faster almost always lose after fees, and 1 day and 4 hours are the timeframes that stay positive. That part is worth keeping, and it is independent of the headline percentages.

## Useful takeaways

1. **Prefer daily bars to intraday bars, once fees are on.** The author's own timeframe grids are the evidence. Fast rows do not keep a profit after fees. Daily rows, and sometimes 4-hour rows, are the ones that do. AlgoDaemon's trusted run is daily. Moving a daily idea onto hourly bars to manufacture trades fights that evidence.

2. **Put scoring deal-breakers on the promotion gate.** The author's fixed-anchor score maps Sharpe onto 0–3, the log of profit factor onto 0 through log 3, and maximum drawdown onto 5–50% inverted, with weights 0.4, 0.3, and 0.3. Grade cutoffs in the post start at 85 for the top mark, then 80, 75, 65, and 55. A worked example scores 56.05. The part worth using is the reject rule: fewer than 30 trades, or a maximum drawdown above 50%, and the candidate is out. A minimum out-of-sample bar count belongs beside the trade count. That floor would have blocked the 24-bar Sharpe of 5.07 that [bug B6](../design/2026-09-27-algodaemon-bug-report.md#b6-a-short-sample-volume-filter-is-still-best) still records as Best. [Bug B5](../design/2026-09-27-algodaemon-bug-report.md#b5-promotion-compares-sharpe-across-different-date-ranges) is the related failure, comparing Sharpes across different date ranges. Fixed anchors are a better pass/fail than a score that moves whenever the candidate set changes. The scoring post is [Implementing a strategy scoring system](https://www.patreon.com/dutchalgotrading/posts/implementing-149520933).

3. **Use TOPSIS to choose among robust neighbours.** TOPSIS ranks a set against itself. Example weights in the post are Sharpe 0.5, drawdown 0.3, and win rate 0.2, with two illustration scores of 0.559 and 0.625. Adding or removing a candidate changes the other scores. Use it after the 70% neighbour rule in the specs, to pick inside a plateau. Do not use it as the promotion gate. The post is [Using TOPSIS](https://www.patreon.com/dutchalgotrading/posts/using-topsis-to-148622584).

RSI length in the offline approximation is noisy. Across windows, lengths 14 and 28 scored better than 21, and on the alt book an RSI(28) cell reached an in-sample Sharpe up to about 1.5 with an out-of-sample Sharpe only about 0.4–0.8. Keep the Spec A and Spec B grids small, and take the neighbourhood rather than the peak.
