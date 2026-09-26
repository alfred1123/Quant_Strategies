# Methods from the PolyU quantitative trading course

**Doc type:** strategy research  
**Status:** Testable rules have been handed to the AlgoDaemon Quant Researcher; platform results pending.

This page paraphrases a review of the Hong Kong Polytechnic University (PolyU) quantitative and algorithmic trading course. The question was which ideas in those notes are worth trying on AlgoDaemon for **BTC, ETH, and BNB**, daily Bybit spot, at 10 bps, with a position in {−1, 0, +1} and only SMA, EMA, RSI, Bollinger, and stochastic.

Figures printed in the notes come from equities, futures, or classroom simulations. None of them are crypto results, and none of them are AlgoDaemon results. Where a number appears below, the sentence says which course-notes example it came from. No figure was filled in.

Two-condition rules use `FILTER(primary, gate)`: the primary signal is taken only while the gate is true, and the position is flat otherwise. A long-only AND on this engine currently scores as an OR ([bug B1](../design/2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors)). Crypto trades every calendar day, so annualise with √365. The notes use about 250 or 261 trading days.

## What the course covers

The notes move from foundations to a short machine-learning close:

1. Calculus, linear algebra, and probability, including Bayes.
2. Estimation, confidence intervals, hypothesis tests, and maximum likelihood versus a posterior mode.
3. Random walks, the efficient-market claim, and geometric Brownian motion.
4. ARMA, historical and exponentially weighted volatility, ARCH and GARCH, integration, and cointegration tests.
5. Momentum: a plain past return, time-series momentum as in Moskowitz, Ooi, and Pedersen, and a velocity-and-acceleration rule fitted on US stocks.
6. Pairs: distance, Engle–Granger, an Ornstein–Uhlenbeck spread, a Kalman-filter version, band re-entry, the Hurst exponent, and periodic re-fitting.
7. Hidden Markov models, a two-state trend filter, a turbulence (Mahalanobis-distance) regime, and jump or change-point alarms.
8. Mean-variance and maximum-Sharpe portfolios, then CAPM-style regression and a principal-component market factor.
9. Wavelet smoothing, and a limit-order-book discussion that does not apply to daily bars.
10. Kelly sizing, including half Kelly and an extended form that reserves room for a crash.
11. Options, Greeks, and the gap between implied and realised volatility.
12. A development loop: backtest, a later test window, paper, live, and occasional re-optimisation, with Sharpe, Treynor, and the information ratio.
13. A brief reinforcement-learning example, and a warning about multiple testing.

The notes do not contain a deflated Sharpe ratio, White's reality check, or Hansen's SPA. They also do not specify Bollinger, RSI, stochastic, or Donchian trading rules. The only multiple-testing correction written down is a Šidák threshold, used for jump detection. There is no full anchored walk-forward procedure, only a generate-then-test split and periodic re-optimisation. Risk parity is mentioned in passing in a survey article, not as a method.

## Top five ideas for BTC, ETH, and BNB daily

The order is a judgement about how strong the evidence in the notes is, and how well the idea fits a daily spot book. It is not a forecast of crypto Sharpe.

| Rank | Idea | Tag | Rule, in one line |
|------|------|-----|-------------------|
| 1 | Time-series momentum, long or flat | Testable now on AlgoDaemon | Long when close is above SMA(N), for N from 100 to 365; otherwise flat. An EMA crossover is the smoothed variant. |
| 2 | The same trend, sized by a volatility target or by half Kelly | Needs backend | Scale the sign of close versus SMA(N) by a target volatility over an exponentially weighted volatility (about a 60-day centre of mass), and clip the weight to [−1, 1]. Half Kelly sizes by estimated edge over variance, at half the full fraction. |
| 3 | Buy a dip only inside an uptrend | Testable now on AlgoDaemon | `FILTER` a lower-band dip with a slow trend gate. A single-asset stand-in for a pairs band rule. |
| 4 | Regime-switching trend | Needs backend | Long when a bull-state probability rises through an upper threshold, and flat when it falls through a lower one. The stateless stand-in is rule A4. |
| 5 | ETH/BTC and BNB/BTC cointegrated spreads | Needs backend | Enter on a wide spread z-score, exit toward the mean, and drop the pair when cointegration, the Hurst exponent, or distance fails. |

**Why this order.**

1. Time-series momentum is the result the notes lean on hardest. The course's futures example, drawing on Moskowitz, Ooi, and Pedersen for roughly 1985–2009, reports a diversified annual Sharpe above 1, about two and a half times an equity index, about 1.58% alpha per month, and a lecture-slide out-of-sample Sharpe around 1.1. In that study, lookbacks of about a year or less stayed positive, and the payoff was strongest in extreme markets. Those are futures figures, not crypto. The sign of an N-day return is close to "close above its moving average," which this engine already has. Long or flat avoids a spot short. A slow window keeps turnover down, so 10 bps is a small cost. The practical hope on these coins is missing a long bear. A 200-day gate in this same family has already been run on the stored BTC book and lowered hold-out Sharpe; that result is on [Momentum, reversal, and filters](momentum-reversal-filters.md). A1 is still the hand-off, because the grid is wider than that one window, and that loss is why the untouched 2024 window below is required.

2. The published time-series-momentum book did not hold a unit position. It scaled exposure to a volatility target: about 40% annualised, divided by an ex-ante volatility. Kelly sizing points the same way. Size falls as variance rises, and a half-Kelly fraction keeps most of the growth while cutting the chance of a large loss. The course's worked binary example (win probability 0.6, payoff odds 0.8) gives a full-Kelly fraction of 0.1. The Thorp reading in the notes says half Kelly keeps about three quarters of the growth rate, and about an 8/9 chance of doubling before halving. Crypto volatility clusters, so a constant unit long takes its worst drawdowns in the high-vol spells. With no leverage, the scaler mostly cuts exposure there. A multi-asset study assigned in the course (Kritzman, Page, and Turkington) also found that a defensive tilt improved results mainly by lowering volatility. In that course-notes multi-asset example, the information ratio went from 0.72 to 1.01, volatility from 8.37% to 6.83%, and maximum drawdown from −41.48% to −32.69%, with a break-even cost of 133 bps per two-way trade. This rank sits below the unit trend rule because the engine cannot hold a weight in (0, 1] yet. Fractional weights and a volatility scale are [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) and [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight) of the [backend proposal merged in PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63).

3. A dip bought only while a slow trend is up is a different return from rank 1, so the two sleeves should be only weakly related. The band comes from a pairs lecture: re-enter after a ratio has stretched about two standard deviations and is coming back. The regime split comes from a Hurst discussion: trend when the exponent is above one half, revert when it is lower. The notes have no single-asset crypto test of this combination. Holding only while price stays outside the band makes very short trades, so fees matter. Leaving the trade at the mean, after the entry, needs a position that remembers it is in a trade ([Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers)).

4. A two-state bull/bear filter, from Dai, Zhang, and Zhu as assigned in the course, is the notes' sharper trend rule. Buy when the filtered bull probability crosses up through a high threshold, and sell when it crosses down through a lower one. That memory is not a stateless threshold. The course's US-equity example, at a small per-trade cost, shows trend-following terminal wealth well above buy-and-hold on three indices: NASDAQ 1991–2008, 8.82 versus 4.24 (66 trades on the trend book); S&P 500 1962–2008, 64.98 versus 33.5; Dow, 26.03 versus 12.11. At a 1% cost the NASDAQ trend-following figure in the notes falls to 4.64. The same notes describe the thresholds as insensitive to small moves, and list S&P 500 thresholds near 0.69–0.74 and 0.90–0.91, and NASDAQ thresholds near 0.43–0.45 and 0.67–0.69. Those are equity terminal-wealth multiples, not Sharpes, and not crypto. The recursive filter itself is not in PR #63. The hold between two thresholds is the hysteresis in [Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers). Rule A4 is the piece that can run today.

5. A market-neutral ETH-versus-BTC or BNB-versus-BTC spread would diversify a trend book if the spread actually mean-reverts. The notes' own checks say the relationship dies: suspend the pair when a cointegration test fails, when the Hurst exponent rises through one half, or when the distance becomes extreme, and re-fit about every 100 days. AlgoDaemon has no ratio leg, and a spot short is a poor match for the short side. PR #63 does not add a spread.

Runners-up that did not make the five: a Hurst gate on the trend and dip rules (the indicator is not in PR #63); going flat for a few days after a detected downward jump (a custom statistic plus a cool-down); and the velocity-and-acceleration stock rule, whose only runnable piece is the weak proxy C1.

## Rules that can be tested now

**AlgoDaemon testability:** as-is for A1–A4, B1–B3, and C1, on Bybit spot daily bars. A2 is a diagnostic, because a spot short is not a realistic fill. B3 uses oscillators the bot has; it is not a rule from the notes.

The same settings apply to every row:

| Setting | Value |
|---------|--------|
| Venue | Bybit spot |
| Symbols | BTCUSDT, ETHUSDT, BNBUSDT, each on its own |
| Bars | Daily |
| Fees | 10 bps per side, charged when the position changes |
| Timing | Signal from the close of bar t; that position earns bar t+1 |
| Price | Close for every indicator |
| Combiner | `FILTER` when a rule has two conditions. See [bug B1](../design/2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors). |
| Warm-up | At least the longest lookback |
| Split | Choose parameters on data through 2023-12-31. Leave 2024-01-01 onward untouched. Also run a rolling re-optimisation, described under validation. |

On this engine, "close versus an SMA" is a Bollinger z-score against zero: z > 0 means close is above the average. A band k standard deviations away is the same z-score against ±k. Stochastic inside a two-factor run is a separate failure ([bug B3](../design/2026-09-27-algodaemon-bug-report.md#b3-stochastic-in-a-multi-factor-run-fails-on-high)); use RSI until that is fixed.

| Id | Idea | Signal | Sweep |
|----|------|--------|-------|
| A1 | Time-series momentum, long or flat | +1 when close > SMA(N), else 0. One condition, so there is no combiner. | N ∈ {50, 100, 150, 200, 250, 365}. A 12-month lookback is about 365 crypto days; 3–9 months is about 90–270. |
| A2 | Same rule, long and short (diagnostic) | +1 when close > SMA(N); −1 when close < SMA(N); 0 on an exact tie. | Same N grid as A1. Report it apart from A1. |
| A3 | Smoothed momentum, EMA cross | +1 when EMA(f) > EMA(s), else 0. The long/short variant is −1 when the fast average is below the slow one. | f ∈ {10, 20, 50}; s ∈ {100, 150, 200, 365}; keep s at least 3f. |
| A4 | Two-horizon confirmation. Stateless stand-in for a regime filter. | `FILTER(primary = +1 when close > EMA(N1), else 0, gate = close > SMA(N2))` | N1 ∈ {10, 20, 50}; N2 ∈ {100, 150, 200, 365}. Alternate gate: EMA(50) > SMA(200). Long only. A short-side check, run separately: `FILTER(primary = −1 when close < EMA(N1), gate = close < SMA(N2))`. |
| B1 | Dip to the lower band, only in an uptrend | `FILTER(primary = +1 when close is below the lower Bollinger band (n, k), else 0, gate = close > SMA(M))` | n ∈ {20, 50, 130}; k ∈ {1.5, 2.0, 2.5}; M ∈ {100, 150, 200}. The position is on only while price stays below the band, so the trades are short. Exiting at the mean needs [Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers). |
| B2 | Pullback toward the mean, only in an uptrend | `FILTER(primary = +1 when close < SMA(n), else 0, gate = close > SMA(M))` | n ∈ {10, 20, 50}; M ∈ {100, 200}; keep M at least 5n. |
| B3 | Oscillator form of the dip. An adaptation, not a course rule. | `FILTER(primary = +1 when RSI(n) < L, else 0, gate = close > SMA(M))` | n ∈ {2, 3, 5, 14}; L ∈ {10, 20, 30}; M ∈ {100, 200}. A stochastic %K(14, 3) below 10 or 20 can replace RSI once [bug B3](../design/2026-09-27-algodaemon-bug-report.md#b3-stochastic-in-a-multi-factor-run-fails-on-high) is fixed. |
| C1 | Weak price-only stand-in for a short-horizon velocity band | `FILTER(primary = +1 when close is above the upper Bollinger band (n, k), else 0, gate = RSI(m) < R)` | n ∈ {5, 10, 20}; k ∈ {1.0, 1.5, 2.0}; m ∈ {5, 14}; R ∈ {75, 80, 85}. |

C1 is low priority. The course rule also wanted a volume surge, a cap on acceleration, and a stop plus a profit target. The upper band only stands in for "the short-horizon push is large enough," and the RSI cap stands in for "it is not already extended." Run it after the A and B grids.

The notes' US-equity fit of that velocity rule, from a 2010 stock sample, used a two-day price change of about 2.5% to 7.5% and a wider acceleration band, plus volume bands. The 2011 out-of-sample stock test in the notes had 158 trades, a 43.04% share of trades with profit of at least 30%, and a 31.65% share that also kept drawdown to at most 10%. That is a course-notes US-equity example, not a parameter set for BTC.

Sleeve combination is offline. AlgoDaemon stores one position per asset. Averaging the daily returns of the best A rule and the best B rule, on one coin and then across the three, is a step after the single-asset runs.

## Validation practices

These come from the notes' development lecture, the momentum slides' generate-then-test split, and a pairs re-optimisation note. They apply to the grids above.

1. **Generate, then test.** Pick parameters on the generate window, through 2023-12-31. Score them once on the later window, from 2024-01-01. Also re-optimise on a rolling basis: about every 100 days in the pairs note, or quarterly. Trade the next block with the parameters chosen on the trailing window, and record how far the chosen point moves. The notes do not go beyond that split and the periodic refit.

2. **Multiple testing, as far as the notes go.** The only correction written down is Šidák, in the jump-detection material: the per-test level is one minus (one minus the family level), raised to one over the number of tests. A1 alone is six windows per coin. A1 through C1 is several hundred cells. A family-wise line on that many cells is strict, which is the point of using it.

3. **Deflated Sharpe and White's reality check are not in the notes.** Bring them in from outside. The deflated Sharpe ratio is Bailey and López de Prado. White's reality check, and Hansen's SPA, apply to the whole grid. A machine-learning survey in the reading list warns about multiple testing and post-selection bias, and it does not supply either statistic. A Šidák threshold is not a substitute.

4. **Prefer a plateau.** The regime-switching paper assigned in the course checked that nearby thresholds behaved alike. Keep a parameter whose neighbours score similarly. Drop an isolated peak.

5. **Break-even cost.** For each rule, find the two-way cost that removes the excess return over buy-and-hold, following the break-even exercise in the turbulence paper. Compare that cost with a 20 bp round trip (10 bps a side). Also rerun at 20 bps and at 30 bps per side.

6. **Trade diagnostics from the development lecture.** Dispersion of trade P&L, costs as a share of gross profit, whether losses cluster, and how deep and how long the drawdowns are.

7. **Metrics.** Sharpe with √365. Treynor and the information ratio against BTC buy-and-hold, with the information ratio as alpha over residual volatility from a regression on BTC. For a forecasting model, out-of-sample R² against the historical mean, as in the hidden-Markov reading.

8. **Hurst caveat, if a Hurst gate is ever built.** The notes include a warning that the exponent is biased on short or jumpy samples. Use windows of about 250 days or longer, and compare with shuffled or random-walk surrogates. One equity example in the reading, a local Hurst threshold near 0.4, reports a gap of 0.055 versus a random baseline on that paper's own score. That is not a crypto result. The indicator does not exist here. One lecture suggestion was to run the trend rules when a 250-day Hurst exponent is above 0.5, the dip rules when it is below about 0.45, and to cut risk when it falls below about 0.4. That gate is needs-backend, not part of A1–C1.

## What still needs a backend

| Gap | What the notes describe | Where it is specified |
|-----|-------------------------|------------------------|
| A weight in (0, 1] and a volatility estimate | Target-volatility or half-Kelly scaling of the trend sign. After the sizer exists, a target around 20–60% annualised and an exponential centre of mass around 20–60 days is the range the review suggested. | [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) and [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight) |
| Hold, then exit on a different condition | Leave a band trade at the mean. Hysteresis between two bull-probability thresholds. | [Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers) |
| Two legs, or a ratio | ETH/BTC and BNB/BTC spreads, with cointegration and Hurst suspension. | Not part of PR #63 |
| Custom series | Hidden-Markov state probabilities, Mahalanobis turbulence of the three-coin return vector, Hurst, bipower jumps, wavelets, and volume velocity or acceleration. | Not part of PR #63 |
| External option data | Implied versus realised volatility as a filter. Spot AlgoDaemon cannot trade the option. | Not part of PR #63 |

An offline combination of the three single-asset equity curves can stand in for a portfolio weight until fractional multi-asset weights exist. The notes' classroom minimum-variance sketch (correlation 0.2, volatility 14.54% at weights 0.8 and 0.2) is a two-asset illustration, not a crypto allocation.

**AlgoDaemon testability:** A1–A4, B1–B3, and C1 are the hand-off. Rank 2 and the stateful exits wait on the backend proposal. Rank 5 and the custom indicators wait on work that proposal does not include.
