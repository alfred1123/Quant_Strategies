# Microstructure, on-chain, and unusual signals

**Doc type:** strategy research  
**Status:** hypothesis — not backtested here.

These are the ideas whose Sharpe story is thinner, or whose edge is real and still a poor match for a daily spot engine. They are here so they are not forgotten and not confused with the [first five tests](sharpe-ideas-index.md#try-these-first).

---

## 1. The 24-hour roll-out effect

**Sources.**

- README of [OctopusTakopi/24h-rollout-effect](https://github.com/OctopusTakopi/24h-rollout-effect), retrieved in full. English. The README says the hourly rule comes from a public thread by Robot James and gives `https://x.com/therobotjames/status/2080281157246259663`. That post was **not** opened for this note. Figures below are the README's, unless marked as the README's paraphrase of the thread.
- 发明者量化-小小梦, FMZ, 28 August 2026, [「屏幕上的 24h 涨跌幅会影响短线价格吗？——用 FMZ Rust 实现 Roll-Out TradFi 策略」](https://www.fmz.com/digest-topic/11023). Chinese. *Does the 24h change on the screen affect short-term price? A Roll-Out TradFi strategy in FMZ Rust.* This post cites the same public replication and then refuses to use it as proof for a different market.

**Mechanism.** The displayed 24-hour change is a moving window:

```text
C(t) = P(t) / P(t − 24h) − 1
```

Tomorrow's displayed number depends on today's price, which is unknown, and on the price that is about to fall out of the window, which is already known. When a large up-candle from exactly 24 hours ago drops out, the displayed change falls even if the last price does not. The hypothesis is that some order flow trades the **number on the screen**. The edge, if it exists, should sit on that one hour and not on a placebo age of 1–23 hours.

The README's hourly rule, on completed candles, for non-stablecoin USDT perpetuals:

```text
if the candle 24h ago was the largest up-candle in the trailing 24:
    short for one hour
if it was the largest down-candle:
    long for one hour
enter at the next candle's open
```

The FMZ post splits two objects the crude rule mixes: the current 24h change is an attention filter, and the expected mechanical change in the displayed number (`Shock`) is the trigger. Their continuous version looks forward 5 and 30 minutes, requires the two shocks to share a sign, and only then takes a side. They moved the first build to Binance TradFi perps (tokenized equity, ETF, and commodity perps), not to the crypto universe the README studies.

**Data.** Hourly candles for the replication: Binance USDT perpetuals, listed and delisted, 2020-01-01 to 2026-07-22, 788 contracts, 14.46 million hourly candles, from `data.binance.vision` (snapshot 2026-07-23). A minute file for 2026 is used for the event study. The FMZ prototype wants about 25 hours of 1-minute bars, a 24h ticker, and the book, for a handful of candidates that already have a large displayed move.

**Why it might improve Sharpe.** It is a clock-time anomaly with a placebo test, which is rare in this literature. The pre-cost hourly portfolio is diversified across many contracts, so its Sharpe can look like a proper strategy rather than a single-coin trend. The README's own cost section is why it is not on the try-first list: the edge per trade is a few basis points, and this platform charges 10 bp per unit of turnover by default.

**Reported performance.** From the README, not from this repository.

The README's paraphrase of the original thread: gross edge "about 0.08% per contract per day." The replication's own per-contract figure is 0.086% per active day and 0.070% per listed day over the trailing four years, positive in every calendar year 2020–2026.

Per-trade mean return of the one-hour rule:

| Sample | Signals | Mean 1h return | Win rate |
|--------|---------|----------------|----------|
| Full, 2020–2026 | 1,165,160 | +4.75 bp | 49.9% |
| Trailing four years | 991,147 | +3.66 bp | 49.5% |

Mean basis points per trade by year: +8.2 (2020), +10.7 (2021), +10.1 (2022), +3.5 (2023), +3.9 (2024), +4.2 (2025), +2.1 (2026). The hourly portfolio t-statistic is 4.2 over the trailing four years, "an annualized Sharpe near 2.1 before costs."

Costs, as stated: **−6.3 bp per trade at a 10 bp taker round trip**, and −0.3 bp at a 4 bp maker round trip. The edge rises with the trigger candle, from +0.5 bp when the trigger is below 1% to +39 bp when it is above 20%. A 1-hour hold is +3.7 bp; a 24-hour hold is −7.3 bp. Since 2024 the short side carries nearly all of the edge.

Placebo: ages 1–23 average −0.21 bp. Age 24 is +1.87 bp with clustered t = 4.2, the only age that survives 24 comparisons.

A later, in-sample subset (short only, trigger at least 10%, lagged hourly volume at least $1 million; the README says this subset was refined with knowledge of 2026) is a different object from the raw rule. Over 202 days and 2,241 trades the README reports +23.9 bp gross and +19.9 bp after maker fees, then −3.5 bp of funding, "about +16.4 bp" net. At a capital level they call the knee ($316k, fixed capital, no reinvestment): total return +141.6% of initial capital over those 202 days, annualized Sharpe 2.38, max drawdown −52.5% of initial capital (−20.6% of the running peak). A small-capital plateau is given as 0.76% per day and an annualized Sharpe of 2.4, with full efficiency only out to about $79k and 90% of the plateau out to $316k. The worst 1% of trades cost 1.1 times the entire net profit. The README flags the 2026 subset figures as in-sample.

The FMZ author, after summarizing that literature, writes:

> 因此，这个公开结果只能证明「值得研究」，不能直接证明一个可实盘策略已经成立。
>
> So this public result can only show that the idea is worth researching. It cannot by itself prove that a live strategy already works.

And, because their build is TradFi rather than the crypto universe in the README:

> 把机制迁移到 TradFi 是新的待验证假设，不能借用原研究结果作为收益证明。
>
> Moving the mechanism onto TradFi is a new hypothesis that still has to be tested. The original results cannot be borrowed as proof of profit.

**Risks.** The README is explicit: full-capital compounding produces both ruin and four-figure equity multiples from the same signal, and one skipped −269% trade is the difference. Selection on a pooled t-statistic picked a rule that then lost out of sample; selection on an hour-clustered t-statistic did not. An earlier draft's volume filter used information unavailable at entry and inflated one cell from −6% to +864%. Capacity is shared, because every user of the signal wants the same contract in the same minute. Shorting the coin that just printed a huge up-candle is the population where the next print is also huge: the README's liquidation rates at 5× and 10× are not decorative. Funding on the short side subtracted, because crowded shorts pay.

**Fit here.** Poor. The hold is one hour, the edge dies at the default 10 bp taker round trip, and we do not have a "largest candle 24 hours ago" feature or delisted-contract history. 1-hour bars exist, but a signal that enters on the open and exits one bar later is mostly a cost test. Not a first backtest. If it is ever tried, the README's lesson for the job is the placebo (the effect should vanish at ages other than 24) and a maker fee assumption, not the 2.38 Sharpe path.

**AlgoDaemon testability:** Can't be tested as published (788 perpetuals, a one-hour hold). Daily bars cannot see a candle falling out of a 24-hour window. An hourly spot test on BTC, ETH, and BNB would be a different market, and the same README finds the edge **negative** at a 10 bp taker round trip, which matches the bot's fee. Not in the hand-off.

---

## 2. Clock-time bursts and order-book features

**Sources.**

- Peter Hansen, [arXiv:2607.09426](https://arxiv.org/abs/2607.09426), *The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures*. English. Abstract. Submitted 10 July 2026, revised 16 July 2026.
- [arXiv:2602.00776](https://arxiv.org/abs/2602.00776), *Explainable Patterns in Cryptocurrency Microstructure*. English. Abstract only. No author list was extracted from the abstract page in a reliable way, so none is stated here. No Sharpe appears in the abstract.

**Mechanism.** Hansen: volume and volatility bunch on the 1-minute, 5-minute, and 15-minute marks of six Binance perpetual contracts, and trade-size roundness drops in those bursts (more algorithmic flow). Opening returns are predictable out of sample. Opening order-flow imbalance predicts returns over the next four to twelve hours; the same relationship is weaker at the finer clocks.

The microstructure preprint engineers order-book and trade features on 1-second Binance Futures books (BTC, LTC, ETC, ENJ, ROSE; 1 January 2022 to 12 October 2025) and finds that SHAP rankings look similar across those names. The abstract says a conservative top-of-book taker backtest and a fixed-depth maker backtest were used to check tradability, and that taker and maker diverged in a flash crash in the way adverse-selection theory predicts. It does not give the backtest's Sharpe or return.

**Data.** Trades and, for the second paper, a full book at 1-second resolution. A 1-hour OHLC bar does not contain the clock-phase or the imbalance.

**Rough rules.** From Hansen's abstract, not a recipe with thresholds (none were stated):

```text
# at each quarter-hour open, on a liquid perpetual
signal from the opening return and the opening order-flow imbalance
hold on the order of 4–12 hours for the imbalance forecast
```

**Why it might improve Sharpe.** Predictable flow at a known clock is a candidate for a short-hold overlay with a higher hit rate than a daily trend. The 4–12 hour imbalance horizon is the only part that is even conceivably near this engine's 1-hour bars. The 1-second book model is not.

**Reported performance.** Not stated as a Sharpe or a return in either abstract. "Predictable out of sample" is the claim, without a magnitude.

**Risks.** Six contracts, one venue, one clock. Algo participation can move the burst earlier once the effect is known (the roll-out README makes the same capacity point). Taker costs of a few basis points erase it, by analogy with section 1, until someone shows otherwise. A flash-crash split between maker and taker is adverse selection: the fill you want is the fill that is toxic. No 1-second data is stored here.

**Fit here.** Not expressible. Noted as a reason not to expect 1-hour OHLC momentum to capture "order flow."

**AlgoDaemon testability:** Can't be tested. The signal is the order book or the trade print at a quarter-hour, and the bot has daily and hourly bars only. Hourly OHLC does not contain opening imbalance.

---

## 3. Investor attention

**Sources.** Liu and Tsyvinski, [NBER WP 24877](https://www.nber.org/papers/w24877), August 2018, the same working paper as the [time-series momentum](momentum-reversal-filters.md#1-bitcoin-time-series-momentum) section. English. PDF.

**Mechanism.** Proxies for attention forecast returns. For Bitcoin, Google searches for the word "Bitcoin" and Twitter post counts; a separate negative-attention proxy predicts lower subsequent returns. High attention in their sample was followed by higher, not lower, near-term returns — a continuation effect, not a fade-the-headline effect.

**Data.** Daily or weekly search counts and tweet counts aligned to the return calendar. The paper's Google result is strongest at one and two weeks.

**Rough rules.**

```text
z = zscore(google_searches("Bitcoin"), trailing window)
# their evidence is a regression and a quintile sort, not a published threshold
gate = 1 if z is in the top part of its history else 0
# as a FILTER this would allow the baseline long only when attention is elevated
# that translation is ours, and it may be the wrong sign out of sample
```

**Why it might improve Sharpe.** If attention marks persistent buying for one to two weeks, a gate that requires it avoids long entries nobody is searching for. Those entries may be the low-follow-through ones. Alternatively, attention is just another momentum proxy (people search after the price has already moved), in which case the gate double-counts the trend filter and adds a data vendor.

**Reported performance.** From the working paper, beside weekly means, not described there as annualized:

> A one-standard-deviation increase in the Google search for the word "Bitcoin" yields a 2.3 percent increase in the 2-week ahead Bitcoin returns. At the 1-week horizon, the average return of the top quintile is 11.20 percent per week with the Sharpe ratio of 0.48 while the average return of the bottom quintile is 1.07 percent per week with the Sharpe ratio of 0.08.

A one-standard-deviation increase in Twitter posts for "Bitcoin" "yields a 2.50 percent increase in the 1-week ahead Bitcoin returns." The same paper's weekly regression form: a one-standard-deviation increase in that week's searches lines up with +1.84 percent and +2.30 percent at the one- and two-week horizons.

**Risks.** The sample ends in 2018, and search behaviour has changed. Weekly quintile Sharpes of 0.48 are per-week ratios on a series whose weekly standard deviation the same paper puts near 16 percent for Bitcoin returns; they are not a live annualized Sharpe. Google Trends is revised, sampled, and easy to align a day too early (lookahead). Attention spikes in both bubbles and crashes. One series is a hypothesis; a dashboard of ten attention series is a fitting exercise.

**Fit here.** Only after a series is loaded as a column on the traded coin. Ranked fifth and last on the [try-first list](sharpe-ideas-index.md#try-these-first) for that reason: one series, as a FILTER, compared with the plain trend gate, and dropped if it does not help out of sample. Glassnode is the on-chain path and is a different dataset; see section 4 and [Alternative data sources](../design/alt-data-sources.md).

**AlgoDaemon testability:** Needs adapting. Trade Bybit spot BTC. Google searches for "Bitcoin", or Twitter counts, are a signal only; nothing but spot is filled. ETH and BNB were not the paper's search term, so they need their own series or they stay out. Daily bars. Hand-off row 8, after the price-only rules, and only if the series is already available. The weekly Sharpe of 0.48 is not annualized and not a target.

---

## 4. On-chain value: spent coins and a price-to-utility ratio

**Sources.** [arXiv:2308.00013](https://arxiv.org/abs/2308.00013), *Bitcoin Gold, Litecoin Silver: An Introduction to Cryptocurrency's Valuation and Trading Strategy*. English. Abstract. The abstract does not give a numeric backtest, so none is stated.

**Mechanism.** The authors treat Bitcoin as the store of value and Litecoin as the medium of exchange, following a remark by Charlie Lee, and measure that with unspent and spent outputs, weighted average lifespan, coin-days destroyed, and public transaction data. They then define trading strategies around a price-to-utility (PU) ratio: price relative to an on-chain activity measure, rather than relative to an average of past prices.

**Data.** Chain data (UTXO, STXO, lifespan, coin-days destroyed) at a frequency the abstract does not pin down, plus price. This is the family of series Glassnode sells (SOPR, MVRV, spent output, and so on). The design note already defers the paid tier.

**Rough rules.** The abstract does not give an entry threshold. The shape, written as a hypothesis rather than as their code:

```text
PU = price / on_chain_activity
# rich versus its own history: fade or stand aside
# cheap versus its own history: allow the baseline long
```

A concrete cousin that **is** standard in this literature, but was not given a performance number by a paper we opened in this pass, is MVRV (market cap over realized cap) or SOPR (spent output profit ratio) used the same way: extreme profit-taking as a risk-off gate. Those names are listed in [Alternative data sources](../design/alt-data-sources.md) as Glassnode endpoints. Citing the endpoint list is not a backtest.

**Why it might improve Sharpe.** An on-chain extreme is slow. Used as a gate it can flat the book when holders are deep in profit and realized selling picks up, which is a different clock from a 20-day Bollinger band. If it only fires a few times a year, turnover cost is negligible next to the daily signal. That is the Sharpe case: a rare veto on the worst entries. If it is just a slow price transform, it will not add anything the 200-day gate does not already add.

**Reported performance.** The abstract says the back-tests "display trading indicators for both Bitcoin and Litecoin" and support the store-of-value comparison. No return, drawdown, or Sharpe is stated.

**Risks.** On-chain metrics are revised as the chain is re-indexed, and several vendors' "realized price" definitions differ. Entity-adjusted series (removing internal exchange shuffles) are a different signal from raw ones, and the adjustment is a vendor model. Daily publication lag can be a full bar. The Professional Glassnode tier was deferred as too expensive for the current stage. Overfitting a threshold on MVRV is as easy as overfitting a Bollinger width, with less history of independent replications that we were able to read.

**Fit here.** Not until one series is in the cache as a factor column. The right experiment, if a series is ever licensed, is a FILTER gate on the existing baseline, not a new signal type. That matches rank 5 on the try-first list and should not jump ahead of the trend gate, which needs no vendor.

**AlgoDaemon testability:** Needs adapting, and only for a coin whose series you have. The position is Bybit spot. The abstract's Litecoin comparison is outside the universe. No chain transaction is executed. Same hand-off row as attention (row 8), and skip it when the file is missing. No Sharpe was stated.

---

## 5. How these interact with the baseline

| Idea | First test, if any | New code? |
|------|--------------------|-----------|
| 200-day trend gate | Already specified on the [baseline page](crypto-spot-baseline-improvements.md#6-suggested-order-if-this-is-pursued) | No |
| ETH (or similar) regime gate | FILTER, other symbol | No |
| Realized-vol flat gate | After an ATR or realized-vol indicator | Indicator only |
| Funding z-score veto | After a funding series, 8-hour normalized | Data, then a column |
| Attention or one on-chain ratio | After one licensed or free series | Data, then a column |
| 24h roll-out, quarter-hour flow, perp-spot arb, cross-sectional baskets | Not scheduled | New backtest objects |

Walk-forward and the 10 bp taker haircut are part of the test, not a follow-up. A rule that only works before costs, or only on the sample that chose its threshold, does not clear the bar the [baseline note](crypto-spot-baseline-improvements.md#4-measurement-hygiene) already sets.
