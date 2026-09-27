# Chin Shum Patreon review

**Doc type:** strategy research  
**Status:** Offline checks are done. No new signal to enqueue on the current engine. External-data rules below are a backend proposal.

This page paraphrases a review, dated 27 September 2026, of paid posts by 錢琛 (Chin Shum) on his [Patreon](https://www.patreon.com/chinshumquantspeculation). The methods are restated in our words. A performance number is either his, and the sentence says so, or an offline approximation (replica engine), not platform results. The offline scripts that produced the computed figures are kept outside this repository.

The book the review measured against is Bybit spot BTC, ETH, and BNB, daily bars, 10 bps per side, long or flat. Two conditions use `FILTER`. A long-only AND on this engine currently scores as an OR ([bug B1](../design/2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors)).

## Summary

Chin Shum's premium posts, weekly since mid-2026, are method walk-throughs with a worked example. The standard tier is mostly Hong Kong, US, China, and Japan cross-asset commentary. Older posts are market notes, course promotion, and 2023–24 funding-arbitrage videos. The catalogue that was read lists 151 posts from January 2023 through 26 September 2026. Full text was available for 13 of the most relevant posts. The rest were seen as a title and a date. Tables that existed only as screenshots were not estimated.

He describes the premium tier as a way to learn how to design strategies, rather than a list of backtests to copy. Under our constraints, almost none of the crypto books are directly tradable. They need an external series, a short, a perpetual, or a coin we do not trade. The useful part is the method.

The Sharpes and PBO figures in the four findings below are an offline approximation (replica engine), not platform results. A number that is his is marked in the sentence.

Four findings:

1. **The exact finalist settings are noise inside profitable families.** Combinatorially symmetric cross-validation on the three finalist families gives a probability of backtest overfitting (PBO) of about 0.40 to 0.79 at the actual fill, above the 20–30% limit he treats as the ceiling. The in-sample winner still makes money out of sample in most splits, at about the family's median Sharpe. Plan on that median: roughly ETH 0.9–1.0, BNB 0.75–0.9, BTC 0.65–0.8. Leave the chosen cells in place. A proposed gate for any new finalist is PBO ≤ 0.30 at both fills.
2. **The three-sleeve blend is the Sharpe gain. The weighting scheme is not.** Equal weight, one third each, has an out-of-sample Sharpe of 1.51 in the offline approximation (replica engine), not platform results, against 1.24 for the best single sleeve. His capped inverse-volatility weights land within 0.03 of that. Equal weight with a 0.5 cap per sleeve is the form to implement, and it needs the averaging combiner from [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63).
3. **Three ideas that looked runnable were rejected.** US-overnight seasonality on BTC is negative at 10 bps per side. A percentile gate in place of the BTC z-score gate on BNB is weaker than the incumbent. Picking the middle of a plateau does not lower PBO.
4. **External series are specified, not adopted.** An ETF NAV-premium gate, an ETF-flow score, a treasury-holdings veto, a funding z-score veto, and an on-chain TVL gate are written up for a backend proposal, with publication-time lags and one missing-data rule for the backtest and for live trading.

!!! warning "Offline approximation (replica engine), not platform results"
    Every Sharpe, PBO, drawdown, correlation, turnover, and return computed for this page is an **offline approximation (replica engine), not platform results**. The replica rebuilds daily net P&L at 10 bps with a fill at the signal close. It matched the recorded platform finalists on in-sample, out-of-sample, late, and full-sample Sharpe: ETH A2 1.398 / 1.241 / 1.002 / 1.324, BNB (BTC z-score window 100 above 0.5) 1.144 / 1.037 / 1.215 / 1.094, and BTC (own z-score window 60 above 2.25) 1.313 / 1.068 / 0.646 / 1.211. Those four-tuples are the recorded platform metrics used as the check. Nothing was enqueued, promoted, or sent to an exchange. His reported numbers are marked as his and are not that replica.

## What the Patreon covers

Three tiers show up in the catalogue.

- **Premium columns**, weekly since mid-2026. Each post walks through one method on one example: funding-rate arbitrage, overfitting probability, position sizing, missing-data treatment, factor design, stationarity, a new on-chain series, using a crypto series on a traditional underlier, and event studies.
- **Standard columns.** Cross-asset notes for Hong Kong, the US, China, and Japan (rates, credit, the yield curve, a China bond against A50, variance risk on the S&P, a Hang Seng lead-lag), usually with a spreadsheet backtest.
- **Free and older posts.** Market commentary (treasury companies, ETFs, exchange concentration, the 10 October 2025 liquidation cascade), course and seminar promotion, and 2023–24 funding-arbitrage videos.

The posts that bear on this book are the overfitting calculation, the sizing recipe, and the data-handling rules (lag a US close by a day, use the same missing-value rule live and in the backtest, do not build a treasury universe from today's list, and prefer Calmar to Sharpe when most days are flat). Those rules carry over to any external-data proposal. A new main signal that this engine can express today does not.

A handful of attached examples listed in the catalogue were not in the set that was read, and most equity curves lived only in screenshots. Where a figure was not in the text, this page does not invent one.

## Ranked methods

Order is the review's judgement of expected benefit for BTC, ETH, and BNB daily. Tags: **Method** can be used on grids we already have. **Needs backend** names a missing engine feature. **Needs external data** names a series the platform does not store. **Not applicable** is a short, a perpetual, an arbitrage, or a non-crypto book. Offline Sharpes in the benefit column are an offline approximation (replica engine), not platform results.

| Rank | Method | Fit | One-line use | Expected benefit |
|------|--------|-----|--------------|------------------|
| 1 | Overfitting probability via combinatorially symmetric cross-validation (15 Aug 2026) | Method, usable now. Done offline | On every candidate family, compute PBO at 10, 12, and 16 blocks, at a same-close fill and at a one-day delay. Gate at PBO ≤ 0.30 | High, as a reading of the finalists rather than a new trade. The exact settings are noise inside robust families. Plan on the family-median Sharpe |
| 2 | Capped inverse-volatility sizing, with Kelly rejected (5 Sep 2026) | Needs backend. The averaging combiner in [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63) | Per-sleeve weight proportional to one over in-market volatility, cap 0.4–0.5, leftover cash stays cash. Cut a sleeve whose live drawdown runs too far from the backtest | Moderate. The blend lifts out-of-sample Sharpe from 1.24 to about 1.51. Inverse volatility versus equal weight adds nothing. The cap is risk control |
| 3 | ETF NAV-premium gate (21 Aug 2026) | Needs external data (daily ETF premium) | Flat BTC when the prior published premium is below a threshold. Carry the last premium across weekends | Unknown until it is run here. His figure: last-observation Sharpe 0.97 against buy-and-hold 0.69, at 2 bps, 26 Jan 2024 to 20 Aug 2026. The effect may be mostly how weekends are filled. Best-documented external series |
| 4 | Funding z-score as a crowding veto (idea taken from an equity-index perpetual, 12 Sep 2026) | Needs external data (Bybit funding history, which is public) | `FILTER` a finalist with BTC funding z-score below a threshold | Unknown. He has no BTC result for it |
| 5 | ETF holdings-flow score (27 Jun 2026) | Needs external data | Gate on a score of the change in spot-ETF holdings measured in BTC, not in dollars | Unknown. He published no backtest of the flow |
| 6 | On-chain TVL momentum (7 Aug 2026) | Needs external data, in native units | ETH or BNB-chain TVL z-score above a threshold, as a gate | Speculative. His figure on the MORPHO token is a Sharpe of 1.83 over about 20 months, with shorts and a window that does not match the write-up |
| 7 | Treasury-company net-selling veto (5 Jun 2026) | Needs external data, with filing timestamps | Flat BTC for a few days after aggregate treasury holdings fall | Low. About a dozen events, no costs in his formulas, and a timing risk |
| 8 | Stablecoin-supply regime (18 Nov 2025) | Needs external data | Gate on the z-score of a 30-day change in stablecoin supply | Speculative. Commentary only, no backtest |
| 9 | BTC overnight seasonality (14 Apr 2026) | Needs backend (a time-of-day factor), and not worth building at our fees | Long outside US cash hours | Negative at our fees. Offline out-of-sample Sharpe −0.66 at 10 bps per side |
| 10 | Percentile or median-deviation normalisation (27 Jun 2026) | Testable now as a close-only proxy, and rejected | A BTC percentile gate for BNB | Rejected. Median out-of-sample Sharpe about 0.6 |
| 11 | BTC-dominance relative value (29 Apr 2026) | Not applicable (a perpetual that is short altcoins). A long-only ETH/BTC rotation would need a ratio column | — | — |
| 12 | Funding-rate arbitrage, on stock perpetuals and on crypto perpetuals | Not applicable | — | — |
| 13 | Long-short crypto basket | Not applicable | — | — |
| 14 | Equity-index funding, a skew-index gate on the S&P, and the Hong Kong and cross-asset theses | Not applicable | — | — |
| 15 | A 2023 "scalability" test of a Hong Kong rule on ETH and ATOM (20 Jan 2023) | Rules were not in the captured text | — | Cannot rate |
| — | Missing-data discipline, a one-day lag on US closes, Calmar for sparse signals, and a drawdown-duration stop | Method | Use these in the external-data proposal and in later live monitoring | Indirect |

## Overfitting check on the three finalist families

**AlgoDaemon testability:** the check itself does not need a new strategy. It needs per-cell daily returns. The platform stores a Sharpe per cell, so the returns below were rebuilt offline. A later optimize response that returns per-cell daily P&L would let the same gate run on platform output.

### How his procedure works

The procedure is the combinatorially symmetric cross-validation of Bailey, Borwein, López de Prado, and Zhu. Start from a matrix of daily strategy returns, one column per parameter set. Split the rows into an even number of contiguous blocks, so that autocorrelation stays inside a block rather than being broken by shuffling single days. He uses 10 blocks. For every way of holding out half the blocks as the test, take the column that won in sample and record where it ranks out of sample. PBO is the share of those splits in which the in-sample winner lands at or below the out-of-sample median. It answers whether *picking the winner* is informative. In a grid of near-duplicate cells it drifts toward one half even when every cell is profitable.

His worked example is not crypto. It is long the S&P 500 while a skew-index z-score stays above a floor. He reports that book's PBO as 14–15%, and he treats 20–30% as the highest PBO he will accept. A re-run of that same example, on his own file and not on this replica, gives 14.68% at 10 blocks, 16.99% at 12, and 17.80% at 16. That matches his claim. He also suggests checking a few train/test ratios (4:1, 85:15, 9:1, 19:1) and regards a rolling year of training with a three-month test as less accurate. He notes that the procedure needs a long sample. One cell he highlights (a 140-day window, floor −0.8, 1 bp of cost, 2 Nov 2020 to 7 Aug 2026) has, in his sheet, a Sharpe of 1.15 against 0.79 for the index. Those are his figures.

### How the check was run

No per-cell daily returns were stored for the round-3, round-4, or round-5 grids. Per-cell daily net P&L was rebuilt with the replica at 10 bps, fill at the signal close, and his CSCV function was applied unchanged. The sample is the common valid window inside 1 Jul 2021 to 25 Sep 2026. BTC-factor z-scores use BTC history from 25 Mar 2020, so they are already warm on 1 Jul 2021. ETH starts on 29 Oct 2021 on the local grid and on 8 Nov 2021 on the wide grid, because the ETH window has to warm up. Block counts are 10, 12, and 16. A one-day delay was run beside the same-close fill.

The grids:

- **ETH A2 local**, 400 cells. BTC gate window 55–75 step 5, gate threshold {1.75, 2.0, 2.25, 2.5}, ETH filter window {80, 90, 100, 110, 120}, ETH filter threshold {−1.0, −0.5, 0, 0.5}.
- **ETH A2 wide**, 375 cells. Gate window {45, 55, 65, 75, 85}, gate threshold from 1.5 to 2.5, ETH window {30, 50, 70, 100, 130}, ETH threshold {−1, 0, 1}.
- **BNB and BTC researcher grid**, 440 cells after dropping one cell that never fires. This is the round-3 single-factor grid: window 10–250, threshold 0–3.
- **BNB and BTC local**, 143 cells. Window 40–160 step 10, threshold 0–2.5 step 0.25.

The three finalists inside those families are ETH A2 (BTC z-score window 65 above 2.25, filtered by ETH z-score window 100 above −1.0), BNB when BTC z-score window 100 is above 0.5, and BTC when its own z-score window 60 is above 2.25.

### Results

PBO at 10 / 12 / 16 blocks. Offline approximation (replica engine), not platform results.

| Family | Cells | PBO, fill at signal close | PBO, 1-day delay | P(in-sample best loses out of sample), delay 0, 10 blocks | Median out-of-sample Sharpe of the in-sample best, vs the grid median (delay 0, 10 blocks) | In-sample best beats coin buy-and-hold out of sample (delay 0) |
|--------|------:|---------------------------|------------------|----------------------------------------------------------:|---------------------------------------------------------------------------------------------:|----------------------------------------------------------------:|
| ETH A2 local | 400 | **0.60 / 0.66 / 0.66** | 0.22 / 0.41 / 0.34 | 7.9% | 0.99 vs 1.04 | 96% |
| ETH A2 wide | 375 | 0.47 / 0.53 / 0.56 | 0.14 / 0.26 / 0.26 | 10.7% | 0.93 vs 0.93 | 94% |
| BNB researcher grid | 440 | **0.48 / 0.45 / 0.33** | 0.22 / 0.15 / 0.19 | 5.6% | 0.73 vs 0.74 | 71% |
| BNB local | 143 | 0.76 / 0.79 / 0.63 | 0.38 / 0.36 / 0.36 | 6.3% | 0.73 vs 0.88 | 62% |
| BTC researcher grid | 440 | **0.46 / 0.40 / 0.42** | 0.30 / 0.38 / 0.34 | 6.0% | 0.69 vs 0.67 | 59% |
| BTC local | 143 | 0.65 / 0.65 / 0.57 | 0.38 / 0.37 / 0.32 | 7.1% | 0.64 vs 0.77 | 53% |

The same function on his skew-index example returns 14.68% at 10 blocks. That line is a check of his example, not a replica result.

Selecting by the in-sample neighbourhood median, which is the rule the researcher actually used, does not lower PBO. At a same-close fill and 10 blocks the neighbourhood PBO is ETH 0.63 / 0.59, BNB 0.55 / 0.65, BTC 0.55 / 0.72, written as the researcher or wide grid and then the local grid. The regression of out-of-sample Sharpe on in-sample Sharpe, for the in-sample winner, has a negative slope in every family, about −0.6 to −1.2. A block that looks strong in sample tends to be followed by a weaker block. That is regime rotation between 2021–22 and 2023–26.

His repeated-ratio check (4:1, 85:15, 9:1, 19:1) is inconsistent across splits, which is what a PBO near one half predicts. The in-sample winner beats the grid median in 4 of 4 splits on both ETH grids and on the BTC researcher grid, in 1 of 4 on the BNB researcher grid, and in 0 of 4 on the BNB and BTC local grids. The neighbourhood pick passes in 0 or 1 of 4 splits, except the BTC local grid, where it passes all 4. The last-year window is the informative one. Over the 4:1 out-of-sample stretch (October 2025 to September 2026, 359 days) the ETH family's grid-median Sharpe is −0.16, and A2 itself is −0.16. BTC at 60 / 2.25 is 0.48. BNB at 100 / 0.5 is 1.81. Those are an offline approximation (replica engine), not platform results. The full split table is under [Repeated train and test splits](#repeated-train-and-test-splits).

### What the numbers mean

1. Every finalist family sits above his 20–30% limit at a same-close fill. PBO there is 0.40 to 0.79. Picking the best-looking parameter inside a family says nothing reliable about which setting will win next. The exact cells (65 / 2.25 / 100 / −1.0, 100 / 0.5, and 60 / 2.25) are arbitrary picks inside families that are robust and profitable. Choosing the best cell adds nothing measurable over picking a typical cell in the same grid.
2. The families are not overfit into losses. The in-sample winner has a negative out-of-sample Sharpe in about 6–11% of splits (5.6–10.7% in the table). Its out-of-sample Sharpe sits near the grid median. The figure to plan on is the **family median**, not the finalist's published out-of-sample Sharpe: roughly ETH 0.9–1.0, BNB 0.75–0.9, BTC 0.65–0.8. Those are half-sample Sharpes, and each half mixes both regimes.
3. BTC and BNB add little Sharpe over buy-and-hold. The in-sample winner beats the coin's buy-and-hold in 53–71% of out-of-sample halves (59% and 71% on the researcher grids, 53% and 62% on the local grids). Median Sharpe gains over buy-and-hold are about +0.67 on ETH, +0.14 on BNB, and +0.09 on BTC. The BTC and BNB gain that is real is the drawdown: about 9% and 30%, against about 50–77% for buy-and-hold. ETH is different. Its family beats ETH buy-and-hold in 94% of wide-grid splits and 96% of local-grid splits.
4. With a one-day delay, PBO falls to 0.14–0.41, and the chosen cells become a recurring in-sample winner (BTC at 60 / 2.25 is the in-sample winner in 18–42% of splits; BNB's delay-1 consensus is a window of 65 and a threshold of 2.25). The delay-robust selection in round 4 was a sound choice. Under the actual fill at the signal close, fine-tuning is noise.
5. Leave the finalists as they are. A fresh search will not help while PBO is about one half. Do not promote a cell because it prints 0.1 more Sharpe than its neighbours. Prefer a rule that shares its parameters across the three coins.

### Proposed promotion gate

Add this next to the existing delay-1 check and the sub-period check. It is a process rule. It does not need a platform call.

- Compute CSCV PBO on the candidate's local grid, at 10, 12, and 16 blocks, at a same-close fill and at a one-day delay.
- Accept the cell only if PBO ≤ 0.30 on both fills. Otherwise report the family median as the expected Sharpe, and keep a pre-committed cell rather than the in-sample peak.

### Repeated train and test splits

Chin Shum checks several in-sample to out-of-sample ratios. Here each ratio means the in-sample window runs from the common start to the day before the out-of-sample start, and the out-of-sample window runs from that start through 25 Sep 2026. The in-sample winners below were chosen offline on the researcher grids. A platform confirmation is about 24 performance calls (3 families × 4 splits × the winner and the finalist), with no new strategy. It has not been run. The pass/fail is none: this is information. The 19:1 windows are 90–96 days and are too short to weigh. The point of the run, if it is done, is to confirm that the ranking depends on the split, and that the ETH family is flat to negative over the last year.

All figures in this table are an offline approximation (replica engine), not platform results. The in-sample end is the out-of-sample start minus one day. The dates are 80%, 85%, 90%, and 95% of each family's common sample, which is why ETH differs slightly from BNB and BTC. Using the BNB and BTC dates for all three is fine.

| Family | Split | Out-of-sample start | Days | In-sample best cell | Its out-of-sample Sharpe | Grid-median out-of-sample Sharpe | Finalist out-of-sample Sharpe |
|--------|-------|---------------------|-----:|---------------------|-------------------------:|---------------------------------:|-------------------------------:|
| ETH A2 (gate window, gate threshold, ETH window, ETH threshold) | 4:1 | 2025-10-02 | 359 | (55, 2.25, 80, 0.5) | 0.05 | −0.16 | −0.16 |
| | 85:15 | 2025-12-31 | 269 | (55, 2.25, 80, 0.5) | 0.22 | 0.09 | −0.06 |
| | 9:1 | 2026-03-30 | 180 | (55, 2.25, 80, −0.5) | 0.43 | 0.11 | −0.08 |
| | 19:1 | 2026-06-28 | 90 | (55, 2.25, 80, −0.5) | 1.60 | 0.93 | 0.93 |
| BNB, BTC z-score gate (window, threshold) | 4:1 | 2025-09-08 | 383 | (65, 1.75) | 0.99 | 0.98 | 1.81 |
| | 85:15 | 2025-12-13 | 287 | (65, 1.75) | 0.39 | 0.94 | 1.75 |
| | 9:1 | 2026-03-18 | 192 | (65, 1.75) | 0.70 | 1.26 | 2.15 |
| | 19:1 | 2026-06-22 | 96 | (55, 1.75) | 1.50 | 1.96 | 3.02 |
| BTC (window, threshold) | 4:1 | 2025-09-08 | 383 | (65, 2.25) | 0.49 | 0.18 | 0.48 |
| | 85:15 | 2025-12-13 | 287 | (65, 2.25) | 0.68 | 0.61 | 0.78 |
| | 9:1 | 2026-03-18 | 192 | (65, 2.25) | 0.84 | 0.82 | 1.18 |
| | 19:1 | 2026-06-22 | 96 | (65, 2.25) | 1.81 | 1.64 | 2.32 |

For reference, our own split (in sample through 30 Jun 2024) picks ETH (60, 1.75, 110, −1.0) with out-of-sample Sharpe 0.93, BNB (55, 1.75) with 0.67, and BTC (60, 1.75) with 0.58. The finalists score 1.24 / 1.04 / 1.07 on that same out-of-sample window. Offline approximation (replica engine), not platform results.

### Consensus cells

These are the cells chosen most often as the in-sample winner across the CSCV splits. The BTC row is already in the round-4 platform table. The other two are worth a lookup in the round-3 grids before any new performance call. Offline approximation (replica engine), not platform results. Metrics are in-sample / out-of-sample / late / full / delay-1 out-of-sample / full-sample max drawdown.

| Rule | Offline metrics | Finalist, same metrics |
|------|-----------------|------------------------|
| BNB long when BTC Bollinger z(65) > 2.25 | 1.03 / 1.34 / 1.59 / 1.12 / 0.94 / 18% | BNB when BTC z(100) > 0.5: 1.14 / 1.04 / 1.22 / 1.09 / 0.99 / 30% |
| `FILTER(BTC z(65) > 2.25, ETH z(80) > −1.0)` | 1.37 / 1.24 / 1.00 / 1.31 / 1.26 / 19% | ETH A2: 1.40 / 1.24 / 1.00 / 1.32 / 1.26 / 19% |
| BTC long when its own z(65) > 2.25 | 1.69 / 1.05 / 0.62 / 1.44 / 0.74 / 10% | BTC z(60) > 2.25: 1.31 / 1.07 / 0.65 / 1.21 / 0.97 / 9% |

A BTC trigger near a window of 60–65 and a threshold of 2.25 is the recurring winner in all three families. Using that same trigger on BNB would raise the BNB sleeve's correlation with the other two. The current BNB–ETH daily correlation is 0.22, and that low overlap is where the blend in the next section earns its Sharpe.

- **BNB consensus.** Smaller full-sample drawdown and a higher out-of-sample Sharpe, with a lower delay-1 Sharpe. Record it as an alternative. Leave the finalist in place. With PBO near one half, a better out-of-sample print is not evidence of a better cell.
- **ETH consensus.** It matches A2. No change.
- **BTC consensus.** Higher in-sample Sharpe, weaker delay-1 Sharpe. Keep window 60 and threshold 2.25.

## Sleeve sizing

**AlgoDaemon testability:** needs a fractional weight and an average across the three sleeves. That is [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) and [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight) of the [backend proposal merged in PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63). The comparison below is offline.

### His sizing rules

He rejects Kelly, including half Kelly, because the formula's binding case is a total loss, which is the wrong loss model for these books. The process he describes is three steps. Set a budget per coin. Inside that coin, assign inverse-volatility weights. Then cap each strategy, and leave the clipped remainder in cash rather than handing it to the other strategies. On the book he uses as the example, the coin budgets are 30% for BTC, 30% for ETH, 20% for SOL, and 20% for XRP, with a 2% cap on any one strategy. An older note of his used equal weight inside the same coin budgets. The illustration he gives is two strategies with the same Sharpe and very different volatility: an equal-Sharpe weight lets the noisier strategy dominate, and inverse volatility is the conservative correction. For live monitoring he compares the live max drawdown, and how long it lasts, with the backtest, and cuts the book if the live path has run too far from the test.

A re-reading of that same allocation example, not a replica result, shows the 2% cap binding on eight strategies and only 44.6% of the budget actually invested. One ETH strategy with a very small unconditional volatility took 26.5% of the raw weight before the clip, so ETH received 5.5% of its 30% budget. A strategy that is rarely in the market has a tiny unconditional volatility and soaks up raw weight. That is the tail risk the cap is meant to catch, and the cap then leaves the unused budget in cash. The volatility he feeds the formula is the unconditional standard deviation of the backtest, which understates the risk of a strategy that is usually flat.

### Comparison on the three sleeves

Sleeves are ETH A2 on ETH, BNB at 100 / 0.5 on BNB, and BTC at 60 / 2.25 on BTC, each long or flat. Holding equals weight times position. Fees are 10 bps on every change of holding, including rebalance trades. The common start is 8 Oct 2021, after ETH warm-up, so the in-sample window here is 8 Oct 2021 to 30 Jun 2024. Weights are estimated on that window only. Daily correlations of the sleeves are ETH–BNB 0.22, ETH–BTC 0.61, and BNB–BTC 0.18. Two or more sleeves are on together on 7.8% of days, and gross exposure reaches 100% only when all three are on.

Offline approximation (replica engine), not platform results.

| Scheme | Weights ETH / BNB / BTC | In-sample Sharpe | Out-of-sample Sharpe | Out-of-sample Sharpe, delay 1 | Out-of-sample max drawdown | Out-of-sample annualised return | Out-of-sample average gross |
|--------|-------------------------|-----------------:|---------------------:|------------------------------:|---------------------------:|--------------------------------:|----------------------------:|
| Best single sleeve (out of sample) | — | — | 1.24 (ETH) | 1.26 (ETH) | 11% (ETH) | — | — |
| Equal weight, one third | 0.333 / 0.333 / 0.333 | 1.66 | **1.51** | 1.47 | 11.0% | 23.5% | 18% |
| His inverse vol, unconditional in-sample vol, cap 0.5 (the cap does not bind) | 0.404 / 0.170 / 0.425 | 1.74 | 1.53 | 1.48 | 9.2% | 20.9% | 12% |
| His inverse vol, unconditional vol, cap 0.4, excess left in cash | 0.400 / 0.170 / 0.400 | 1.74 | 1.53 | 1.49 | 9.0% | 20.4% | 12% |
| Inverse vol on in-market vol, cap 0.4 or 0.5 | 0.345 / 0.316 / 0.339 | 1.68 | 1.52 | 1.48 | 10.6% | 23.2% | 17% |
| His older fixed coin budgets, 80% invested | 0.30 / 0.20 / 0.30 | 1.72 | 1.54 | 1.50 | 7.6% | 17.6% | 12% |
| Dynamic inverse vol, 90-day sleeve vol, cap 0.5 | rolling | 1.50 | 1.45 | 1.37 | 9.1% | 22.0% | 19% |
| Dynamic inverse vol, 90-day sleeve vol, no cap | rolling | 1.47 | 1.38 | 1.26 | 10.5% | 21.8% | 21% |
| Dynamic inverse vol, 90-day coin vol | rolling | 1.71 | 1.48 | 1.44 | 11.5% | 23.2% | 20% |

Blending is what adds the Sharpe: 1.51 out of sample against 1.24 for the best single sleeve, at about the same drawdown. Capped inverse volatility stays within 0.03 Sharpe of equal weight in every static form. Unconditional inverse volatility tilts toward BTC and ETH because those sleeves are usually flat. Their unconditional volatilities are 15.6% and 16.4%, low only because they are rarely on. That tilt cuts gross exposure and drawdown without improving the risk-adjusted return. On in-market volatility (54–59% for all three), the weights collapse to equal weight. A trailing 90-day inverse-volatility weight is worse, with out-of-sample Sharpe 1.38 to 1.45.

### How this maps onto the combiner

We have one sleeve per coin, so his per-coin budget is the sleeve weight.

1. If inverse volatility is implemented, feed it in-market volatility or the coin's volatility. Unconditional sleeve volatility is the wrong input. Estimate it on the in-sample window and refresh it at most quarterly.
2. Cap each sleeve at 0.40–0.50. Leave clipped weight in cash.
3. Do not use Kelly.
4. Flag or cut a sleeve whose live max drawdown, or the length of that drawdown, exceeds the backtest.

The form that matches the table is equal weight, which is what in-market inverse volatility becomes here, with a 0.5 cap per sleeve.

## Ideas tested offline and rejected

These do not need platform calls. Every computed figure is an offline approximation (replica engine), not platform results.

### Overnight seasonality

The rule is long BTC outside the US cash session (10:00–16:00 New York, Monday to Friday), weekends included, on hourly Bybit closes. He defines the split by the regular US trading session, and he starts the sample when the US spot ETF listed, on the view that the market structure changed. He disputes a published claim of more than 200% since the start of 2024 against 47% for holding BTC. His own no-cost replication is a Sharpe of about 1.5. He then says that trading the same idea in US ETFs costs at least about 5 bps a side, 10 bps round trip, after which the result is about the same as buy-and-hold, and that a perpetual at about 2.5 bps a side plus funding still beats holding BTC but is nothing like that published chart. His metric table was not in the captured text. Those sentences are his.

The hourly check, offline approximation (replica engine), not platform results:

| Window | Buy-and-hold Sharpe | Overnight, gross | 2.5 bps per side | 5 bps per side | 10 bps per side | Trades per year |
|--------|--------------------:|-----------------:|-----------------:|---------------:|---------------:|----------------:|
| Pre-ETF, Jul 2021 to 10 Jan 2024 | 0.49 | 0.71 | 0.44 | 0.16 | **−0.39** | 521 |
| Post-ETF, 11 Jan 2024 to 23 Sep 2026 | 0.70 | 1.08 | 0.74 | 0.40 | **−0.27** | 521 |
| Out of sample, 1 Jul 2024 to 23 Sep 2026 | 0.52 | 0.72 | 0.37 | 0.03 | **−0.66** | 522 |

The effect is there, gross, as he says. At 10 bps per side it is negative, and the engine has no time-of-day factor to express it. An intraday-only book is negative even before costs, with gross Sharpe from −0.12 to −0.31. Building a calendar factor for this rule is not worth it at our fees.

### Percentile gate

His factor-design post prefers a percentile, or a deviation from the median scaled by a robust spread, when a series is skewed or fat-tailed. As a proxy that this engine can run, the BTC z-score gate on BNB (window 100 above 0.5) was replaced by a rolling percentile rank of the BTC close, and separately by a close-only stochastic %D. Each grid is length 20–150 by threshold 50–90, 30 cells. Median out-of-sample Sharpe is 0.62 for the percentile rank and 0.60 for the stochastic. Only 3% and 7% of cells beat the incumbent's out-of-sample 1.04. The in-sample winners score 0.51 and 0.16 out of sample. The Bollinger z-score is the better normalisation for this gate. Rejected.

### Plateau picking

Choosing the cell with the best in-sample neighbourhood, rather than the single best cell, does not lower PBO. The neighbourhood figures are 0.55 to 0.72 at a same-close fill and 10 blocks, as listed in the overfitting section. Rejected as a cure for the overfitting probability. It remains a sensible way to avoid a one-cell spike. It is not evidence that the chosen cell will keep its rank.

## Notes on his crypto examples

These are the books behind the external-data specs. His numbers are his. The local readings are a re-reading of his examples, not the replica, and not platform results.

### ETF NAV premium

Hold BTC, and go flat when the previous day's NAV premium is negative. The series is the IBIT premium, in percentage points, with a daily BTC price. The position uses the prior premium. Cost in his example is 2 bps per unit change of position, and he annualises with 365. The sample is 26 Jan 2024 to 20 Aug 2026. He compares eight ways to fill missing premiums: carry forward, carry backward, linear interpolation, fill with zero, an expanding mean, a 7-day rolling mean, hold the last position, and unwind to flat.

He reports that the expanding mean looks best overall, that linear interpolation has the highest Sharpe and some look-ahead, and that carrying the last value forward lifts Sharpe to 1 and beats buy-and-hold on Sharpe and on Calmar. Unwind is poor because too many days are flat. His performance table puts the carried-forward Sharpe at 0.97, not 1, against 0.69 for buy-and-hold. Zero-fill and the expanding mean print the same Sharpe, the same annualised return, the same Calmar, and the same drawdown in that table.

A re-reading: 310 of 939 rows have no premium, which is weekends and holidays. Any non-negative weekend fill stays long, so "zero" and "expanding mean" are the same strategy. The winning imputation is "stay long over the weekend," not a smarter fill. The rule flips on a premium of a few basis points around zero (265 negative-premium days), and the threshold of exactly zero was not varied. The lag is conservative: a US date drives a later UTC day, so there is no look-ahead in the timing. Annual return is a mean times 365, and the drawdown is on summed P&L rather than compounded wealth. One ETF, about 2.6 years. His live rule for a missing print is a flat position.

### ETF flows

The design post is an exploratory pass, not a backtest. He reports flow skewness since 2024 of −0.19, and he says a z-score or a Bollinger band is a poor model once skewness reaches 1 and excess kurtosis reaches 3. In that case he prefers a percentile or a median-deviation score. Transforms he walks through include logs, differences, cumulative sums, and a square as a volatility proxy.

A re-reading reproduces the skewness near −0.19, and finds that the "flow" is the change in a balance quoted in dollars. In BTC units the same flow has excess kurtosis 4.97, above his own threshold of 3, so a z-score would fail his rule on the series that is actually a flow. A dollar change in ETF balances is mostly the coin's price move.

### Treasury holdings

The published book is short BTC when a basket of treasury companies reduces holdings. The universe is ten companies that already held BTC in 2022, so it is not a list drawn from today's survivors. The signal is on when the change in total holdings is below a floor (he uses zero), and the hold is one to five days, from the start of 2022 through 4 Jun 2026. He reports that a two-day hold has a Calmar close to 2, and he uses Calmar because a large number of zero-return days inflates Sharpe. He also flags survivorship in a vendor's current list, and delays in the data.

A re-reading: about 12 signal days in 4.4 years, several of them a handful of coins. The sheet's formulas charge no transaction cost. The holding period was chosen on those 12 events. Returns are summed. The timing is the serious risk. The day's P&L uses a position known the day before, while the price return is a midnight-to-midnight UTC move, so a holdings change has to be dated after it was public. He notes one sale that was news before the vendor recorded it. Nothing shows that this is true of all 12 events, and a filing that backdates a purchase would leak. The short version does not fit this book. The long-only version is a flat-after-selling veto, in the spec below.

### On-chain TVL

The published book is long or short the MORPHO token when a z-score of Morpho protocol deposits is beyond a symmetric threshold. He describes hourly deposits aggregated to two-hour bars, a 165-day z-score, and a threshold of 2.625, and he reports that Sharpe and the other metrics beat holding the token, with a parameter plateau. A later edit says raw deposits were more useful than deposits scaled by market cap. His sheet, at that threshold and at 3 bps of cost, shows a Sharpe of 1.83, annualised with the square root of 365 times 12, from late November 2024 to 7 Aug 2026. Those are his figures.

A re-reading: the z-score window in the sheet is 165 rows of two-hour bars, about 14 days, not 165 days. Time in the market is 5.2% (2.4% long, 2.8% short), with 138 position changes and about 20 months of data. Buy-and-hold Sharpe from the same sheet is about 0.70. The threshold is very precise. Deposits quoted in dollars move with crypto prices, so part of the signal is price momentum. MORPHO is outside our universe, and the short side does not fit. The transferable piece is a TVL gate on ETH or BNB, in the spec below.

### Funding as a crowding veto

The published book is a contrarian z-score of hourly funding on an equity-index perpetual: short when the z-score is above 1.3, long when it is below −1.3, with a 384-hour window, 1 bp of cost, and annualisation by the square root of 8760. He reports that some cells of a window-by-threshold heatmap reach a Sharpe of 3, with few trades because the windows are long, and that less than a year of data means the annualised Sharpe is extrapolated and may be inflated. The vendor history he used is about ten months. He describes the signal as still being watched. The summary table was not captured. Shorts, a non-crypto underlier, a short sample, and an optimised heatmap. Not applicable as published. The piece that transfers is a BTC perpetual-funding z-score used only as a veto.

### Books that do not fit

**Dominance index.** Hold a BTC-dominance perpetual (BTC against a basket of large altcoins; he notes the top five alts already carry about 90% of that relative-value weight). His figures since 2024: funding cost about 44%; after that cost, Sharpe 0.8 against 0.7 for BTC, max drawdown 40% against 50%, annual return 26% against 28%, and correlation with holding BTC of about 0.2. About 2.3 years, a heavy funding bill, and no timing rule. It is buy-and-hold of a spread that is implicitly short altcoins. A long-only stand-in would be an ETH/BTC or BNB/BTC rotation, which needs a ratio column this engine does not have.

**Funding-rate arbitrage.** Long the stock or the spot, short the perpetual, or the reverse. Rank by a 30-day average APR. He says a 90-day window lagged too much. Filters in the example require a large open interest and a large day's volume, and a 30-day APR of at least 30%. Execution is a limit on the more expensive venue and then a market hedge on the cheaper one. He reports a minimum 30-day APR of 30% and a realised annualised APR of about 15% with no leverage and capital split across the two legs. A long-run total above 20% is what he calls acceptable. In May 2026 he said the book had returned about 5% over the prior year. A question-and-answer note, whose exact wording was not captured, describes a normal BTC or ETH funding book with a half-year Sharpe in the high single digits and an annual return around 11%. He puts about half the allocation in trend-style algorithms and about a tenth in arbitrage. Liquidation risk and venue risk are his own caveats. The stock-perpetual samples are short, and the returns have decayed. Not applicable.

**Long-short basket** (28 Sep 2025). Long a quality or top-five basket, or BTC, and short about twenty losers, rebalanced monthly, dollar-neutral or beta-neutral, tradable names only. No performance numbers. Not applicable.

**The 2023 scalability sheet.** A Hong Kong rule tried on ETH and on ATOM. The rules are not in any captured text. The sheet's "optimal" parameters are an in-sample pick on about two years, fees are not stated, and a benchmark drawdown above 100% shows that returns were summed. It cannot be rated.

## Red flags in his published results

1. **Short samples, which he says himself.** The equity-index perpetual is about 10 months, the TVL book about 20 months, the dominance index and the overnight study start in 2024, the ETF premium starts in January 2024, and the treasury signal is about 12 events.
2. **Headlines often live in screenshots.** The spreadsheets are what can be checked, and twice the file disagrees with the post: the TVL window is 165 two-hour bars rather than 165 days, and the imputation Sharpe he calls 1 is 0.97 in his own table.
3. **Costs are light or missing.** The treasury book charges none. Imputation uses 2 bps. The equity-index perpetual uses 1 bp. The TVL book uses 3 bps. The skew example uses 1 bp. Ours is 10 bps per side. Overnight dies at that cost.
4. **Returns are summed, not compounded,** and an annual return is a mean times the number of periods. Drawdowns are in summed-return points. A benchmark drawdown above 100% shows up on the 2023 scalability sheet.
5. **Shorts and perpetuals** in most of the crypto examples: treasury selling, TVL, the equity-index funding book, the dominance index, and the arbitrage.
6. **Timing.** He lags ETF data by a day, which is the right direction. Treasury dates depend on when the vendor stamps a filing. A short taken on the same day's print can be look-ahead.
7. **A "flow" in dollars is contaminated by the price.** The change in a USD ETF balance is mostly price times holdings.
8. **What he does well.** He reports his own biases (linear interpolation looks ahead, a current treasury list is survivorship, an annualised Sharpe on a short sample is extrapolated). He uses Calmar when many days are flat. He lags US data. The overfitting calculation matches the 14–15% he stated.

## External-data specs for a backend proposal

**AlgoDaemon testability:** none of these run today. Each one is a `FILTER` on an existing finalist, or a standalone BTC long-or-flat rule, once the series exists. Daily bars, 10 bps, long or flat.

Shared rules:

- In sample is 1 Jul 2021 to 30 Jun 2024 where the history allows it. ETF history starts in January 2024, so that book's in-sample window would be January 2024 to June 2025.
- A timestamp is the publication time, not the event date. A value for US date *d* may affect only the position set at the close of the first daily bar that ends after publication. For data released in US hours, the default bar is the one that closes at 00:00 UTC on *d*+2.
- Scheduled gaps (weekends, US holidays) carry the last observation forward. An unscheduled vendor outage sets the position to flat, with the same rule in the backtest and live.
- Run CSCV at 10, 12, and 16 blocks on each grid before any promotion, and apply the [PBO ≤ 0.30 gate](#proposed-promotion-gate).

### E1 ETF NAV premium gate

Source: the 21 Aug 2026 imputation post.

- **Data.** IBIT daily market price, NAV, and premium or discount, from an ETF-history vendor or from the issuer's files, from 11 Jan 2024.
- **Rule.** The gate is on when the prior published premium is at least *k*.
- **Sweep.** *k* ∈ {−0.25, −0.10, 0, +0.10, +0.25} percentage points, lag ∈ {1, 2} bars, missing ∈ {carry forward, unwind}. That is 20 cells. A z-score variant: premium z-score of window *w* at least *k*, with *w* ∈ {20, 60, 120} and *k* ∈ {−1, −0.5, 0}. That is 9 cells.
- **Apply as** a standalone BTC rule, and as `FILTER` on BTC z(60) > 2.25.
- **Check** whether the result survives when weekends are forced to a carried-forward long and when weekends are forced flat. His identical zero-fill and expanding-mean rows say the weekend choice is the result.

### E2 ETF flow score

Source: the 27 Jun 2026 factor-design post.

- **Data.** Total US spot-ETF BTC holdings in BTC, from issuer holdings or from published flows divided by price. Do not use the dollar balance.
- **Transform.** Daily flow is the change in holdings. His own rule says that once excess kurtosis reaches 3, use a percentile or a median-deviation score, not a z-score. On his file the BTC-unit flow has excess kurtosis 4.97, so the score should be the robust one.
- **Rule.** The gate is on when the score of the flow, or of cumulative holdings, over window *w* is at least *k*.
- **Sweep.** *w* ∈ {20, 40, 60, 120}, *k* ∈ {−0.5, 0, 0.5, 1.0}, and both the flow and the cumulative holdings. That is 32 cells.

### E3 DAT net-selling veto

Source: the 5 Jun 2026 treasury post.

- **Data.** Treasury holdings for a point-in-time universe (companies that held BTC on that date, not today's list), plus the filing or announcement time of each change.
- **Rule.** The gate is off for *H* days after aggregate net selling of at least *m* BTC.
- **Sweep.** *H* ∈ {1, 2, 3, 5}, *m* ∈ {0, 100, 1000}. That is 12 cells.
- **Limit.** About 12 events from 2022 to 2026. The result cannot be validated statistically. Treat it as a risk-off overlay only if the ETF series in E1 and E2 is already being built.

### E4 Funding-rate crowding veto

Source: the idea in the 12 Sep 2026 equity-index funding post, transferred to BTC.

- **Data.** BTCUSDT perpetual funding from the Bybit public history, 8-hour prints averaged to a daily mean.
- **Rule.** The gate is off when the funding z-score over window *w* is above *k* (crowded longs). A contrarian entry when the z-score is below −*k* needs a two-leg combination this engine does not have. Leave that out.
- **Sweep.** *w* ∈ {7, 14, 30, 60} days, *k* ∈ {1.0, 1.5, 2.0}, veto only. That is 12 cells on each finalist, 36 runs.
- **His parameters, for reference only.** A 384-hour window and a threshold of 1.3, on hourly funding of an equity-index perpetual.

### E5 On-chain TVL momentum

Source: the idea in the 7 Aug 2026 TVL post, transferred off the MORPHO token.

- **Data.** Ethereum DeFi deposits and BNB Chain deposits, in the native coin or divided by the coin's price. He prefers a protocol's own feed to an aggregator, on data-quality grounds.
- **Rule.** The gate is on when the TVL z-score over window *w* is above *k*, in the momentum direction he used.
- **Sweep.** *w* ∈ {7, 14, 30, 60} days, *k* ∈ {0.5, 1.0, 1.5, 2.0}. That is 16 cells per coin.
- **Do not copy his published window.** The post says 165 days and the file uses 165 two-hour bars. His later edit preferred raw deposits to deposits over market cap.

### E6 Stablecoin supply, low priority

Source: the 18 Nov 2025 liquidity note. No backtest. His observation in that note is a stretch when the S&P was up by more than 2% and BTC was down by more than 11%, with spot-ETF holdings, treasury demand, and stablecoin supply as slow liquidity factors.

- **Data.** Combined USDT and USDC supply, daily.
- **Rule.** The gate is on when the z-score of the 30-day change, over window *w*, is above *k*.
- **Sweep.** *w* ∈ {60, 120}, *k* ∈ {−0.5, 0, 0.5}. That is 6 cells.

### What the backend still needs

Beyond the series themselves:

- The fractional combiner in [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63), so the three sleeves can be weighted.
- An optimize response that returns per-cell daily P&L, so PBO is computed from platform output rather than from the replica.
- A ratio column, if anyone later wants a long-only ETH/BTC rotation as a stand-in for the dominance perpetual. That book is not applicable as he published it.
- A time-of-day factor would be required for the overnight rule. That rule loses at 10 bps, so the factor is not justified by this review.

## Subscription verdict

The subscription is being kept. Its value for this book today is moderate, and almost entirely methodological.

What it has already given us is a CSCV calculation that changes how the finalists are read: expect the family-median Sharpe, and leave the cells alone. It has given a sizing recipe that confirms equal weight, with a cap, for the three-sleeve blend. It has given concrete shapes for external series (ETF premium and holdings, treasury filings with a publication time, public funding history, protocol deposits) and the lag and missing-data rules a backend proposal needs.

What it has not given us is a new signal this engine can run. The crypto strategies are short-sample, lightly costed, and built on shorts, perpetuals, or outside data. He is explicit that the premium tier teaches the method.

Set next to the [Dutch Algotrading review](dutch-algotrading-review.md), this source is stricter. He measures overfitting, lags US data, and flags his own biases. It is also much less portable: there is no close-only rule here that is ready to enqueue. The premium price he charges is 539 Hong Kong dollars a month. That is worth paying while the external-data feed and the combiner are being built. Once those are in place, the standard tier plus an occasional premium month is enough.

Posts worth reading as they appear:

1. Premium posts that attach a crypto factor (ETFs, treasury holdings, deposits, funding, liquidations, open interest). They feed the specs above. When a post and its worked example disagree, trust a re-reading of the example. Two disagreements have already shown up, on the TVL window and on the imputation Sharpe.
2. Method posts: cross-validation, Monte Carlo, sample size, sizing and equity-curve trading (he has said he will write the equity-curve piece separately), how similar two alphas are, regression against buckets, and stationarity. Those bear on the promotion gate and on the blend.
3. The monthly question box is the channel for a direct answer. Three questions worth sending: whether he still applies a PBO gate when every cell in a grid is profitable; what the 2023 scalability rule actually was; and how the treasury vendor dates a holdings change.
4. BTC calendar posts, if a time-of-day feature is ever built for some other reason. Check the cost assumption against 10 bps per side before trusting the headline.
5. Skip funding-rate arbitrage, the Hong Kong, China, Japan, and US cross-asset theses, course promotion, and market commentary.

Posts that were catalogued and not read in full include later notes on ETF data, Monte Carlo, event studies, regression against buckets, stationarity, residualisation, how long a backtest should be, liquidation heatmaps, open interest, a worked inverse-volatility spreadsheet, buy-and-hold helpers, and portfolio construction, plus about fifteen cross-asset notes and about sixty administrative or commentary posts. They are not reviewed here.
