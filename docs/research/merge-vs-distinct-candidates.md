# Which candidate strategies to merge vs run as separate sleeves

**Doc type:** strategy research  
**Status:** Platform sweeps have been handed to the AlgoDaemon Quant Researcher; results pending.

This page compares the candidate rules already written up on [Methods from the PolyU quantitative trading course](polyu-quant-course-methods.md) and the [Dutch Algotrading Patreon review](dutch-algotrading-review.md), together with the round-1 BTC z-score regime rule and the BTC-gate family that includes the current ETH candidate. The question is which of those names are the same strategy, and which are different enough to run side by side.

!!! warning "Offline close-only approximation, not platform results"
    Every Sharpe, drawdown, correlation, agreement, turnover, and return on this page is an **offline close-only approximation, not a platform result**. The replica rebuilds the AlgoDaemon profit maths on Bybit daily closes taken from platform responses already cached when the check was run. Nothing was enqueued, nothing was promoted, and nothing touched an exchange. The platform re-run is the test that counts. Where a figure below is compared with a platform number, the sentence says so.

## Bottom line

Most of the candidates that look different are one strategy: a **BTC-regime trend cluster**. On BTC their daily returns correlate 0.83–0.99. That cluster covers the round-1 BTC z-score regime rule (R1), the cross-asset BTC-gate family that includes the ETH candidate (XG), [Dutch Specs A, B, and C](dutch-algotrading-review.md#hand-off-specs), [PolyU A4](polyu-quant-course-methods.md#rules-that-can-be-tested-now), and, on BTC, PolyU A1 and A3. Collapse them into one rule the engine can already run:

`FILTER(gate = BTC Bollinger z(wg) > k, long only; factor 2 = own Bollinger z(wf) > 0, long only)`

On **BTC and BNB** the second leg adds nothing, so run the single-factor gate. On **ETH** the own-trend confirmation leg adds real value. Extra two-factor merges that were tried on top of that (an RSI confirmation, a slow-trend gate, a Bollinger strength leg) did not beat the simple members in a way that survives the neighbourhood. They only add complexity.

The only diversification that is both clearly distinct and robust is **across coins**: the same merged rule on BTC, ETH, and BNB. Sleeve correlations there are 0.31–0.56. An equal-weight three-coin blend has an offline out-of-sample Sharpe of **1.24** (inverse-vol 1.32), against 0.82 for the single sleeve that would have been picked in sample and 1.18 for the best single sleeve in hindsight. Out-of-sample max drawdown falls to 13% from 20–28%. Those blends need fractional sizing. The engine cannot express them today. The averaging combiner and the fractional weight are [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight) and [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) of the [backend proposal merged in PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63).

Dip-buy rules ([PolyU B1, B2, B3, and C1](polyu-quant-course-methods.md#rules-that-can-be-tested-now)) are distinct (correlation at most 0.35) and weak on their own. They cut out-of-sample Sharpe on BTC and BNB. The ETH B1 gain rests on 9 in-sample trades and 7 out-of-sample trades.

The sanity check that changes the reading: out-of-sample Sharpe for the whole regime cluster roughly **halves with one extra day of execution delay**, while in-sample barely moves. The incumbent ETH candidate 80/1.5/30 is the fragile cell (out-of-sample 1.33 → 0.61). The nearby 70/1.75/30 holds up (1.18 → 1.08). Details are in [Caveats](#caveats).

## Data, conventions, and replica validation

**Data.** Bybit spot daily closes, from cached platform performance responses. The public Bybit API returned HTTP 403 from the machine that ran the check, so there was no fresher download. The last bar is the 2026-09-25 UTC daily close.

| Coin | Closes used |
|------|-------------|
| BTC | 2020-03-25 → 2026-09-25 |
| ETH, BNB | 2021-07-01 → 2026-09-25 |

**Conventions mirrored from the engine.** All of the following are part of the offline approximation, not a fresh platform run.

- Long-only positions in {0, 1}. The signal at the close of day *t* is held over day *t*+1.
- 10 bps per side, charged on the absolute change in position.
- Sharpe is mean divided by the sample standard deviation, times √365. Warm-up bars, where an indicator is missing, are dropped.
- In sample is 2021-07-01 → 2024-06-30. Out of sample is 2024-07-01 → 2026-09-25 (817 days, about 2.2 years).
- BTC's own indicators use history from March 2020. For ETH and BNB, the BTC factor is cut to the traded coin's calendar, as the engine does.
- `FILTER` is the platform combiner in which the gate is factor 1 and the position is factor 2's signal while the gate is on. Sweeps for this page are FILTER, not AND. A long-only AND on this engine currently scores as an OR ([bug B1](../design/2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors)).
- Indicator formulas follow the platform: SMA-based RSI, and a Bollinger z-score.
- Sortino, where it is quoted, uses a 0% target: mean divided by the root-mean-square of the negative returns, times √365. Turnover is the sum of absolute position changes per year.

**How a representative was chosen.** Each family was gridded. The pick is the grid point with the highest in-sample neighbourhood mean Sharpe (the mean over one step either way in every dimension), provided there are at least 10 in-sample entries and the neighbourhood is at least 60% of the full interior. That rejects a corner and prefers the middle of a plateau. Out-of-sample numbers were not used in the choice. A representative passes the in-sample screen only when both its Sharpe and its neighbourhood mean are at least 0.6.

**Families.** R1 is BTC z(window) above a threshold. XG is FILTER of own z(fast) above 0 with a BTC z(gate) threshold. DA, DB, and DC are [Dutch Specs A, B, and C](dutch-algotrading-review.md#hand-off-specs). A1, A3, A4, B1, B2, B3, and C1 are the [PolyU rules](polyu-quant-course-methods.md#rules-that-can-be-tested-now). ST is a close-only stochastic proxy built for this check; it is not the platform stochastic, which uses high and low and is broken in a multi-factor run ([bug B3](../design/2026-09-27-algodaemon-bug-report.md#b3-stochastic-in-a-multi-factor-run-fails-on-high), [bug B4](../design/2026-09-27-algodaemon-bug-report.md#b4-cross-coin-stochastic-uses-the-traded-coins-hlc)). CONC* is the nine-lookback Donchian ensemble from [Catching crypto trends](catching-crypto-trends.md), shown unsized, with engine timing. It is a reference, not the paper's volatility-targeted model.

A3 and A4 need a price-versus-EMA or EMA-versus-EMA comparison. This check treated them as not expressible on the engine today.

**The replica matches the platform on the reference rules**, to about 0.03 Sharpe. Offline close-only approximation in the first pair of figures; platform in-sample / out-of-sample in the second.

| Rule | Coin | Offline IS / OOS | Platform IS / OOS |
|------|------|------------------|-------------------|
| Round-1: BTC z(85) > 1.0 | BTC | 1.28 / 0.77 | 1.31 / 0.77 |
| Round-1 | ETH | 1.23 / 0.85 | 1.23 / 0.85 |
| Round-1 | BNB | 1.44 / 0.82 | 1.44 / 0.80 |
| BTC z(80) > 1.25, FILTER own z(50) > 0 | BTC | 0.97 / 0.86 | 0.98 / 0.87 |
| Same rule | BNB | 1.07 / 1.05 | 1.07 / 1.03 |
| BTC z(80) > 1.5, FILTER ETH z(30) > 0 (the ETH candidate) | ETH | 1.12 / 1.33 | 1.12 / 1.33 |

The three current platform bests are one family (XG). BTC and BNB share 80/1.25/50. ETH uses 80/1.5/30. The small BTC in-sample gap (1.28 offline against 1.31 on the platform) comes from using March 2020 history for warm-up.

What the in-sample screen keeps, before any merge: only the BTC-regime families (R1, XG, and Dutch Spec B) pass on every coin with a plateau. Trend and oscillator families that use the coin's own price are weak on ETH and BNB, which matches the [Dutch review](dutch-algotrading-review.md#ranked-ideas). The dip rules spend about 2–15% of days in the market. C1 overfits: on BNB the representative goes from an in-sample 1.31 to an out-of-sample −0.47.

## Per-coin clusters

Pairwise statistics use each pair's common valid days over the full sample (in sample and out of sample together). The out-of-sample-only structure is the same. Correlation measured only on days when at least one rule is in the market differs from the full-sample correlation by at most **0.019** across every pair, so the tables below are the full-sample daily net-return correlations. Days when both rules are flat do not move that number.

**Same strategy**, for the clusters below, means return correlation at least 0.7, or agreement at least 0.8 together with a Jaccard overlap of in-market days of at least 0.5. Clustering is complete linkage, so every pair inside a cluster has to meet that test. Agreement on its own is the wrong test. Low-exposure rules are both flat most of the time, so they "agree" while their returns do not. On ETH, XG and B1 agree on 84% of days, their return correlation is 0.00, and their Jaccard overlap is 0.00. Distinct, in the reading below, means correlation at most 0.4.

Each table is the offline close-only approximation, not a platform result. Blank cells are the diagonal. BH is buy and hold.

### BTC

| | R1 | XG | DA | DC | A4 | A1 | B1 | BH |
|------|-----|-----|-----|-----|-----|-----|-----|-----|
| **R1** | | 0.99 | 0.88 | 0.90 | 0.83 | 0.68 | 0.00 | 0.59 |
| **XG** | | | 0.89 | 0.90 | 0.83 | 0.69 | 0.00 | 0.59 |
| **DA** | | | | 0.87 | 0.91 | 0.75 | 0.00 | 0.61 |
| **DC** | | | | | 0.84 | 0.71 | 0.00 | 0.65 |
| **A4** | | | | | | 0.82 | 0.00 | 0.65 |
| **A1** | | | | | | | 0.21 | 0.78 |
| **B1** | | | | | | | | 0.18 |

R1 and XG are the same book: correlation 0.99, position agreement 98%, Jaccard 0.96. The round-1 rule (85/1.0) and the platform best (80/1.25/50) sit in the same cluster, at 0.92–0.96 with R1 and XG. B3 correlates 0.31 with R1. The unsized Concretum reference correlates 0.80 with R1, so it is a trend-cluster member, not a diversifier.

| Cluster | Members | Reading |
|---------|---------|---------|
| BTC-regime / two-speed trend | R1, XG, Dutch Spec A, Dutch Spec C, PolyU A4 (0.83–0.99) | Same strategy. Merge. |
| Slow trend | PolyU A1 and A3 (0.92 with each other; 0.68–0.86 with the regime cluster) | Adjacent. Not distinct. Joins the regime cluster under average linkage. |
| Dip and other | B3 (0.31 vs R1), B2 (0.26), B1 (0.00), C1 (0.10), close-only stochastic (0.67) | B1–B3 and C1 are distinct. B1, B2, C1, and the stochastic fail the in-sample screen. |

### ETH

| | R1 | XG | DB | A4 | A1 | B1 | Candidate | BH |
|------|-----|-----|-----|-----|-----|-----|-----------|-----|
| **R1** | | 0.66 | 0.84 | 0.75 | 0.69 | 0.00 | 0.78 | 0.51 |
| **XG** | | | 0.63 | 0.43 | 0.43 | 0.00 | 0.84 | 0.34 |
| **DB** | | | | 0.68 | 0.63 | 0.00 | 0.73 | 0.52 |
| **A4** | | | | | 0.77 | 0.00 | 0.59 | 0.48 |
| **A1** | | | | | | 0.06 | 0.54 | 0.64 |
| **B1** | | | | | | | 0.00 | 0.13 |
| **Candidate** | | | | | | | | 0.40 |

"Candidate" is the incumbent ETH rule, BTC z(80) > 1.5 with FILTER ETH z(30) > 0. The XG row is the in-sample representative, 70/1.75/30, which correlates 0.66 with R1 on the full sample and 0.70 out of sample. Dutch Spec C and PolyU A4 fail the in-sample screen and only join the regime group through the agreement-plus-Jaccard test.

| Cluster | Members | Reading |
|---------|---------|---------|
| BTC-regime | R1 and Dutch Spec B (0.84) | Same strategy. |
| XG | Representative 70/1.75/30, and the incumbent 80/1.5/30 (0.84 with the representative, 0.78 with R1) | Borderline against R1. It is R1 plus an own-trend filter, so it is the merged upgrade of R1 on ETH, not a second sleeve. |
| Own trend | A1 and the stochastic (0.78), Dutch Spec A, A3 | Weak. A1, Spec A, Spec C, and A4 fail the in-sample screen. A3 is not expressible and its out-of-sample Sharpe is −0.49. |
| Dip | B1 (0.00 vs XG, about 2% of days in the market), B3 (0.18), B2, C1 | Distinct and thin. B2, B3, and C1 fail the in-sample screen. |

### BNB

| | R1 | XG | DB | DA | A1 | B1 | C1 | BH |
|------|-----|-----|-----|-----|-----|-----|-----|-----|
| **R1** | | 0.96 | 0.90 | 0.67 | 0.72 | 0.00 | 0.34 | 0.55 |
| **XG** | | | 0.86 | 0.68 | 0.73 | 0.00 | 0.34 | 0.53 |
| **DB** | | | | 0.68 | 0.71 | 0.01 | 0.34 | 0.56 |
| **DA** | | | | | 0.76 | 0.00 | 0.38 | 0.55 |
| **A1** | | | | | | 0.00 | 0.29 | 0.72 |
| **B1** | | | | | | | 0.00 | 0.09 |
| **C1** | | | | | | | | 0.23 |

The platform best, 80/1.25/50, correlates 0.88 with R1 and 0.92 with XG.

| Cluster | Members | Reading |
|---------|---------|---------|
| BTC-regime | R1, XG, Dutch Spec B (0.86–0.96) | Same strategy. Merge. |
| Own trend | A1, A3, A4, and the stochastic (0.78–0.89), plus Spec A and Spec C (0.85 with each other) | 0.63–0.75 with the regime cluster. Weak. Spec A passes the screen (in-sample 0.72) and then prints out-of-sample 0.02. The others fail the screen. |
| Dip and push | B1, B2, B3 (0.00–0.28 vs R1), C1 (0.34) | Distinct. B1–B3 fail the screen. C1 is the overfit (in-sample 1.31, out-of-sample −0.47). |

## Merge decisions

The merged rules that were tested are all one FILTER of two close-only factors, gridded and picked with the same in-sample neighbourhood rule. They are an own-RSI confirmation on the BTC gate, the same idea with a BTC RSI leg, a slow own-trend leg on the BTC gate, and a slow-trend gate with a Bollinger strength signal. None of them beat the simple member of the cluster in a way that holds up in the neighbourhood.

Offline close-only approximation, not platform results.

| Coin | Cluster | Best single representative | Does a merged FILTER beat it? | Decision |
|------|---------|----------------------------|-------------------------------|----------|
| BTC | R1, XG, Dutch A, Dutch C, PolyU A4 | **R1: BTC z(w) > k.** In-sample pick 65/1.0 (IS 1.13 / OOS 0.93; neighbourhood mean 1.12; out-of-sample neighbourhood median 0.98). Plateau: window 65–85, threshold 0.75–1.0, in-sample 1.08–1.34, out-of-sample 0.77–1.03. | XG is the same rule. The second leg is almost always on when BTC z is above 1 (correlation 0.99). An RSI-confirmed merge at 75/0.75/21/50 scores 1.17 / 1.03, but its out-of-sample neighbourhood median is lower (0.87 vs 0.98) and in-sample turnover is the same (16 per year). The slow-trend and Bollinger-strength merges are lower. Dutch A and C are lower, with turnover of 21–27 per year. | **Merge into single-factor R1.** Two-factor versions only add complexity. Retire [Dutch Spec A](dutch-algotrading-review.md#spec-a-two-speed-trend-on-btc), [Spec C](dutch-algotrading-review.md#spec-c-two-z-scores-low-priority), and [PolyU A4](polyu-quant-course-methods.md#rules-that-can-be-tested-now) as separate BTC strategies. |
| ETH | R1, Dutch B, plus XG | **XG: FILTER(ETH z(30) > 0, BTC z(70) > 1.75).** IS 1.22 / OOS 1.18; neighbourhood mean 1.13; 89% of neighbours have out-of-sample Sharpe above 1. | XG is the merged R1-plus-own-trend rule, and it beats R1 (85/1.0: 1.23 / 0.85). Time in market drops from 32% to 15%. Out-of-sample max drawdown drops from 36% to 20%. In-sample turnover rises from 10 to 14 per year. The RSI, BTC-RSI, slow-trend, and Bollinger-strength merges all score lower (in-sample 0.14–0.91). | **Merge R1 and [Dutch Spec B](dutch-algotrading-review.md#spec-b-btc-regime-position-in-eth-or-bnb) into the XG form.** Retire Spec B on ETH as its own strategy. |
| BNB | R1, XG, Dutch B | **R1: BTC z(85) > 1.0.** IS 1.44 / OOS 0.82; neighbourhood mean 1.22. Plateau: window 75–95, threshold 0.75–1.25, in-sample 1.04–1.46, out-of-sample 0.72–1.04. | XG at 90/1.0/50 scores 1.36 / 0.84 and correlates 0.96 with R1. It adds nothing. The other merges are lower (slow-trend 1.07 / 0.78; own RSI 1.06 / 0.21; BTC RSI 0.96 / 0.65). The incumbent 80/1.25/50 (1.07 / 1.05) is a local peak: 6% of its neighbours are above 1 out of sample. | **Merge into single-factor R1.** Retire Spec B on BNB. |
| ETH and BNB | Own-price trend and oscillators (Dutch A and C, PolyU A1, A3, A4, close-only stochastic) | — | — | **Drop.** Weak in sample. Where they are decent, on BTC, they already sit inside the regime cluster. |

[Dutch dual RSI](dutch-algotrading-review.md#ranked-ideas) stays retired. The Dutch review already rejected it, and this check does not bring it back.

## Blends against the best single sleeve

Equal weight is a fixed split. Inverse-vol weights are proportional to one over the trailing 60-day standard deviation of each sleeve's net profit, using data through the close of day *t* for the position held over day *t*+1. If a sleeve had fewer than 10 non-zero days in that window, the coin's own 60-day return volatility stands in, so a flat sleeve does not take an infinite weight. Weights are equal until 60 observations exist. Holdings are netted per coin, and fees are charged on the sum of absolute holding changes per coin. Each row is that blend's own common window, which is why the "best single" in-sample Sharpe is not always the full-sample representative. The best single is chosen **in sample**. The best out-of-sample single in hindsight is shown beside it.

These fractional blends need the averaging combiner and fractional sizing from [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63) ([Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights), [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight)). The engine cannot express them today.

Offline close-only approximation, not platform results. Sharpe columns are best single / equal weight / inverse-vol.

| Blend | Window from | IS-chosen single | IS Sharpe | OOS Sharpe | OOS hindsight best | OOS max DD |
|-------|-------------|------------------|-----------|------------|--------------------|------------|
| BTC trend + dip (R1 + B3) | 2021-07-01 | BTC R1 65/1.0 | 1.13 / 1.16 / 1.13 | 0.93 / 0.80 / 0.76 | 0.93 | 20% / 14% / 13% |
| BTC trend + slow trend (R1 + A1) | 2021-07-01 | BTC R1 65/1.0 | 1.13 / 1.00 / 1.01 | 0.93 / 0.60 / 0.71 | 0.93 | 20% / 23% / 19% |
| BTC R1 + A1 + B3 | 2021-07-01 | BTC R1 65/1.0 | 1.13 / 1.03 / 1.05 | 0.93 / 0.57 / 0.68 | 0.93 | 20% / 15% / 14% |
| ETH trend + dip (XG + B1) | 2021-11-28 | ETH XG 70/1.75/30 | 1.20 / 1.54 / 1.50 | 1.18 / 1.43 / 1.34 | 1.18 | 20% / 6% / 9% |
| ETH trend + dip (XG + B3) | 2021-10-09 | ETH XG 70/1.75/30 | 1.25 / 1.28 / 1.20 | 1.18 / 1.36 / 1.29 | 1.18 | 20% / 12% / 14% |
| ETH XG + R1 | 2021-09-24 | ETH R1 85/1.0 | 1.23 / 1.36 / 1.32 | 0.85 / 1.07 / 1.13 | 1.18 | 36% / 21% / 20% |
| ETH XG + R1 + B1 | 2021-11-28 | ETH XG 70/1.75/30 | 1.20 / 1.44 / 1.37 | 1.18 / 1.21 / 1.20 | 1.18 | 20% / 12% / 14% |
| BNB trend + dip (R1 + B3) | 2021-10-09 | BNB R1 85/1.0 | 1.48 / 1.58 / 1.52 | 0.82 / 0.79 / 0.90 | 0.82 | 28% / 15% / 16% |
| BNB R1 + Dutch A | 2021-09-24 | BNB R1 85/1.0 | 1.44 / 1.17 / 1.13 | 0.82 / 0.46 / 0.52 | 0.82 | 28% / 21% / 22% |
| BNB R1 + C1 | 2021-09-24 | BNB R1 85/1.0 | 1.44 / 1.59 / 1.56 | 0.82 / 0.52 / 0.58 | 0.82 | 28% / 19% / 19% |
| Three-coin IS representatives (BTC R1, ETH XG, BNB R1) | 2021-09-24 | BNB R1 85/1.0 | 1.44 / 1.61 / 1.56 | 0.82 / **1.24** / **1.32** | 1.18 | 28% / **13%** / 12% |
| Three-coin incumbents (80/1.25/50, 80/1.5/30, 80/1.25/50) | 2021-09-19 | ETH candidate 80/1.5/30 | 1.12 / 1.27 / 1.26 | 1.33 / 1.34 / 1.29 | 1.33 | 16% / 13% / 12% |
| BTC R1 + ETH XG | 2021-09-09 | ETH XG 70/1.75/30 | 1.22 / 1.33 / 1.32 | 1.18 / 1.26 / 1.20 | 1.18 | 20% / 16% / 14% |
| All per-coin trend + dip | 2021-11-28 | BNB R1 85/1.0 | 1.23 / 1.56 / 1.37 | 0.82 / 1.30 / 1.24 | 1.18 | 28% / 5% / 7% |

Sleeve correlations inside the blends, full sample / out of sample, still the offline approximation: BTC R1 vs ETH XG 0.45 / 0.44; BTC R1 vs BNB R1 0.50 / 0.56; ETH XG vs BNB R1 0.31 / 0.33. Trend against dip: BTC 0.31 / 0.28; ETH XG vs B1 0.00 / 0.00; ETH XG vs B3 0.18 / 0.17; BNB 0.02 / 0.06.

**Across coins is the robust gain.** The three-coin blend of the in-sample representatives (BTC R1 65/1.0, ETH XG 70/1.75/30, BNB R1 85/1.0), against the single sleeve the in-sample screen would have picked (BNB R1):

- In sample, Sharpe 1.44 → 1.61 equal weight / 1.56 inverse-vol.
- Out of sample, 0.82 → 1.24 equal weight / 1.32 inverse-vol. The best single sleeve in hindsight is 1.18.
- Out-of-sample max drawdown 28% → 13% / 12%. Out-of-sample Sortino 1.30 → 2.19 / 2.30.
- Out-of-sample turnover 14.7 → 16.7 / 19.6 per year.

The incumbent three-coin set improves in-sample Sharpe (1.12 → 1.27) and does not improve out-of-sample Sharpe (1.33 for the ETH candidate alone, 1.34 blended). It does cut out-of-sample max drawdown from 16% to 13%. A realistic expectation is **about +0.1 to +0.2 Sharpe over the best single sleeve, and roughly half the drawdown**, not the +0.42 that appears when the comparison is the in-sample pick. Equal weight and inverse-vol are close, so equal weight is the simpler choice. Blending also pulls down the very high positive skew of the sparse ETH sleeve: out-of-sample skew 6.3 for XG alone, 2.3 in the three-coin blend. Sortino still improves.

**Inside one coin, trend plus dip is distinct and mostly does not help.** BTC R1 + B3 is 1.16 in sample and 0.80 out of sample, against R1 alone at 1.13 / 0.93. R1 plus the slow trend is worse. On BNB, R1 + B3 is 1.58 / 0.79 (inverse-vol 0.90), against R1 at 1.48 / 0.82 on that window, and R1 plus C1 or Dutch A lowers the out-of-sample figure. On ETH, XG + B1 is 1.54 / 1.43 against 1.20 / 1.18, with out-of-sample max drawdown 6% against 20%, but B1 made 9 in-sample trades and 7 out-of-sample trades and is in the market about 2% of days. That is a watchlist item, not a sleeve to deploy. XG + B3 (1.28 / 1.36) leans on a B3 setting whose out-of-sample neighbourhood median is 0.21.

Blending two trend variants on one coin (ETH XG + R1, correlation 0.66) lands between the two members. It is not worth running both.

## Recommendation

### One merged rule

Treat the following as **one strategy, the BTC-regime gate**:

- R1, the round-1 BTC z-score regime rule
- XG, the BTC-gate FILTER of an own Bollinger z-score, including the ETH candidate and the current BTC and BNB platform bests
- [Dutch Specs A, B, and C](dutch-algotrading-review.md#hand-off-specs)
- [PolyU A4](polyu-quant-course-methods.md#rules-that-can-be-tested-now), and on BTC the adjacent A1 and A3

The single merged rule, in the form the engine already runs. Factor 1 is the gate. Factor 2 is taken only while the gate is on. Both legs are long-only `momentum_long` on `get_bollinger_band`:

`FILTER(gate = BTC close → get_bollinger_band(wg) → momentum_long, signal = k; factor 2 = own close → get_bollinger_band(wf) → momentum_long, signal = 0)`

On BTC and BNB, drop factor 2 and run the gate alone. Offline plateau ranges below are the in-sample plateau. The centre is in bold. Every Sharpe in the last column is an offline close-only approximation, not a platform result.

| Coin | Form | Parameter range (centre in bold) | Offline plateau IS / OOS |
|------|------|----------------------------------|--------------------------|
| BTC | Single-factor BTC z(wg) > k. Factor 2 is redundant. | wg 65–85 (**75**), k 0.75–1.0 (**1.0**) | IS 1.08–1.34 / OOS 0.77–1.03. Centre 75/1.0 is 1.22 / 0.90. |
| ETH | Two-factor FILTER, as written above. | wg 70–80 (**70**), k 1.5–1.75 (**1.75**), wf 30–50 (**30**) | IS 0.68–1.22 (median 1.07) / OOS 1.14–1.33 (median 1.20). Centre 70/1.75/30 is 1.22 / 1.18. |
| BNB | Single-factor BTC z(wg) > k. Factor 2 adds nothing. | wg 75–95 (**85**), k 0.75–1.25 (**1.0**) | IS 1.04–1.46 / OOS 0.72–1.04. Centre 85/1.0 is 1.44 / 0.82. |

Merging buys lower complexity at the same turnover. On BTC and BNB, extra FILTER legs did not raise Sharpe in a robust way. On ETH, the own-trend leg is the merge that pays: against R1 alone, out-of-sample Sharpe goes from 0.85 to 1.18, time in market from 32% to 15%, and out-of-sample max drawdown from 36% to 20%.

**Retire as separate strategies:** [Dutch Specs A, B, and C](dutch-algotrading-review.md#hand-off-specs), [PolyU A1, A3, and A4](polyu-quant-course-methods.md#rules-that-can-be-tested-now), the close-only stochastic, and the [dual-RSI family](dutch-algotrading-review.md#ranked-ideas) already rejected in the Dutch review.

The platform sweeps of this rule — BTC single-factor, ETH two-factor, BNB single-factor, plus an execution-timing check — have been handed to the AlgoDaemon Quant Researcher. Results are pending. The hand-off asks the researcher to de-prioritise Dutch Specs A/B/C and PolyU A4 as standalone candidates, and to keep PolyU B1 and B3 as low-priority diversifier checks only.

### Distinct sleeves

1. **Three coin sleeves of the merged rule** (BTC, ETH, BNB), side by side. The expected gain from blending is about +0.1 to +0.2 out-of-sample Sharpe over the best single sleeve, with roughly half the drawdown. In the offline approximation that is 1.24 equal weight / 1.32 inverse-vol, against 1.18 for the hindsight-best single and 0.82 for the in-sample-chosen single, and a max drawdown of 13% against 20–28%. Inverse-vol and equal weight are close, so equal weight is the simpler choice. Scoring the combined book needs [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63). The engine cannot express that average today. Three separately capitalised single-asset strategies would approximate equal weight operationally, and that approximation has not been run on the platform.
2. **Dip-buy sleeves (PolyU B1 and B3): watchlist only.** They are genuinely distinct (correlation 0.00–0.31) and weak or thinly traded. They lowered out-of-sample Sharpe on BTC and BNB. ETH B1 (Bollinger z(50) below −1.5, and only while close is above SMA(150)) lifted the ETH blend to an offline out-of-sample Sharpe of 1.43, on 7 out-of-sample trades.
3. **The Concretum Donchian ensemble is not a diversifier.** Daily return correlation with R1 is 0.74–0.80 on each coin, full sample, in this approximation. If [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63) is built, its value would come from sizing and stops, not from a low correlation with this rule. The paper's own rule is on [Catching crypto trends](catching-crypto-trends.md).

## Caveats

!!! warning "One extra day of delay roughly halves the out-of-sample Sharpe"
    This is the largest single risk to the numbers above. In-sample Sharpe barely changes. Out of sample, the whole plateaus drop. All figures in this section are an offline close-only approximation, not platform results.

| Plateau | OOS median | OOS median with one extra day of delay |
|---------|------------|----------------------------------------|
| BTC R1 | 0.85 | 0.63 |
| ETH XG | 1.20 | 0.76 |
| BNB R1 | 0.82 | 0.61 |

In the full R1 and XG grids, the share of settings with out-of-sample Sharpe above 1 falls to 0–5% once the fill is delayed a day (ETH XG: 61% → 5%). The out-of-sample profit came mostly from the first day after each signal. That matters if live or paper execution happens later than the signal close. It is also why the hand-off prefers ETH **70/1.75/30** (out-of-sample 1.18 → 1.08 with the delay) over the incumbent **80/1.5/30** (1.33 → 0.61).

The same stress on the rules this page actually recommends:

| Rule | OOS at 10 bps | OOS at 20 bps | OOS with +1 day delay, 10 bps |
|------|---------------|---------------|-------------------------------|
| BTC R1 65/1.0 (IS pick) | 0.93 | 0.85 | 0.45 |
| BTC R1 75/1.0 (plateau centre) | 0.90 | 0.84 | 0.67 |
| ETH XG 70/1.75/30 | 1.18 | 1.12 | 1.08 |
| ETH XG 80/1.5/30 (incumbent candidate) | 1.33 | 1.28 | 0.61 |
| BNB R1 85/1.0 | 0.82 | 0.76 | 0.68 |
| Three-coin IS representatives, equal weight | 1.24 | 1.16 | 0.94 |
| Three-coin incumbents, equal weight | 1.34 | 1.27 | 0.71 |

A fee of 20 bps per side costs about 0.05–0.08 Sharpe on the trend rules and on the blends. Every recommendation still survives that haircut. The delay does not.

**One out-of-sample window.** Out of sample is 817 days, 2024-07-01 → 2026-09-25, and it is one market regime. ETH and BNB history in this cache starts in July 2021, so a long window has a shorter in-sample period. The engine behaves the same way.

**Multiple testing.** Thirteen families plus four merged families, each on a grid, on the order of 360–420 configurations per coin, and no deflated-Sharpe correction. Parameters were chosen on in-sample neighbourhoods, not on out-of-sample peaks, and some selection bias remains.

**Other limits of this approximation.**

- The replica matches the platform to about 0.03 Sharpe on the seven reference rules in the validation table. That is not a substitute for the platform re-run.
- A truncation check recomputed every recommended rule, and the inverse-vol holdings, on data cut at each of 25 random dates. All 300 checks matched the full-sample values. Indicators are trailing windows. A wrong same-bar fill (position *t* times return *t*) would show out-of-sample Sharpe of about 2.1–3.0 for the trend rules. These numbers do not.
- Fees at 10 bps per side are in every figure. Fee drag on the trend rules is about 100–190 bps a year, and about 65 bps a year for ETH B1.
- Blends assume a daily rebalance to the target fraction, fees on the netted per-coin change, and no intraday drift. The stand-in volatility for a mostly flat sleeve is a choice made for this check.
- A3, A4 (EMA comparisons), the close-only stochastic, and the unsized Concretum reference are not the platform's expressible rules. The long-and-short versions of a close-versus-SMA sign and of an EMA cross were worse than long-only on every coin in sample (for example BTC, window 100: long/short 0.55 against long-only 0.84). Stay long-only.
- The series ends on 2026-09-25 because that is the last cached daily close. No later bar was available for this check.
