# Momentum, reversal, and regime filters

**Doc type:** strategy research  
**Status:** the 200-day gate has been run on the BTC book and lost. The other ideas on this page have not.

Time-series momentum and a trend gate are the ideas on this page that match a single-coin book. Cross-sectional reversal is included because it is often confused with momentum, and because the liquid coins this platform trades do **not** follow the same pattern as the long tail of small coins.

The 200-day FILTER written up under [baseline improvements](crypto-spot-baseline-improvements.md#22-macro-trend-filter-50-200-day-sma) has been run. It lowered the hold-out Sharpe. This page is the evidence that motivated that test, plus a second gate that uses another coin.

---

## 1. Bitcoin time-series momentum

**Sources.** Yukun Liu and Aleh Tsyvinski, [NBER Working Paper 24877](https://www.nber.org/papers/w24877), *Risks and Returns of Cryptocurrency*, August 2018. English. Figures below are from that working-paper PDF, not from a later journal version.

**Mechanism.** Past Bitcoin returns forecast future Bitcoin returns at daily and weekly horizons. The paper's conclusion is that stock, currency, and commodity factors do not explain these coins, while crypto-specific momentum and attention proxies do. For a long-only spot book, the useful part is the sign: after a strong week, the next weeks were stronger than after a weak week, in their sample.

**Data.** Daily or weekly close of one coin. No order book, no funding, no cross-section.

**Rough rules.**

```text
r_t = close_t / close_{t-1} - 1          # weekly in the paper
# predictive regression (their weekly Bitcoin result):
# a 1-standard-deviation higher r_t lines up with higher r over the next 1–4 weeks

# a tradable gate, not their regression:
gate  = 1 if close > SMA_N else 0        # N around 100–200 daily bars
position = gate * baseline_signal        # baseline is already {-1, 0, +1} or long-only
```

Their grouping version, not a threshold we should copy blindly: sort weeks into quintiles of the latest return and look forward.

**Why it might improve Sharpe.** The baseline's weak spot, as the [baseline note](crypto-spot-baseline-improvements.md) already says, is long exposure in bears. A gate that is flat when recent returns are negative removes a high-variance, negative-mean slice. That usually changes Sharpe more than it changes raw return, because the denominator falls. It is the same reason a 200-day filter is the first row of the [try-first list](sharpe-ideas-index.md#try-these-first).

**Reported performance.** Quoted from the working paper, Bitcoin, weekly grouping. These Sharpe ratios sit next to **weekly** average returns. The paper does not call them annualized. Do not multiply by √52 and treat the product as their number.

> At the 1-week horizon, the average return of the top quintile is 11.22 percent per week with the Sharpe ratio of 0.45 while the average return of the bottom quintile is 2.60 percent per week with the Sharpe ratio of 0.19.

A one-standard-deviation increase in the current week's Bitcoin return "leads to increases in weekly returns of 3.16 percent, 3.66 percent, 3.49 percent, and 1.50 percent" at the 1-, 2-, 3-, and 4-week horizons. The 3.16 percent figure is their coefficient 0.19 times a weekly standard deviation of 16.64 percent. They also report a smaller but still significant effect on a sample restricted to 2013 onward, and an out-of-sample check that fixes quintile cutoffs on the first two years. Ethereum's momentum effect is "less significant" than Bitcoin's and Ripple's in the same paper.

**Risks.** The sample ends in 2018. Weekly quintile returns of 11 percent are not a live edge after fees, and a weekly Sharpe of 0.45 is a per-week ratio on a very volatile series. Momentum is regime-dependent: [Grobys and Sapkota](#3-a-published-non-result) do not find significant momentum payoffs on a 2014–2018 cross-section. In-sample quintiles overfit. A 200-day price filter is not the same object as a one-week return regression; it is the version we can express, and it can sit flat for months.

**Fit here.** The sign-of-trend gate is expressible now. `get_bollinger_band` at window 200 and threshold 0 is positive exactly when price is above its 200-day average; use it as the FILTER gate with `momentum_long`, and keep the existing Bollinger momentum recipe as the signal. A literal "past one-week return" indicator does not exist. `get_sma` returns a price level, so a threshold on SMA is not a return. Long-only signal types (`momentum_long`) already clip shorts, which matches a spot account. Walk-forward is `python -m quant.cli --walk-forward`.

**AlgoDaemon testability:** As-is. Daily Bybit spot, long or flat, BTC then ETH then BNB. Fee 10 bps per trade. Hourly is allowed and not the run to trust. Hand-off rows 1 and 2.

---

## 2. Cross-product regime gate

**Sources.** No single paper owns this rule. It is the time-series result above, applied to a second coin, using a feature this codebase already has. English note, built from [Factor list](../architecture/api.md#factor-list-single-source-of-truth).

**Mechanism.** Require a large, liquid coin other than the one being traded to be in an uptrend before taking the baseline long. The hope is that some BTC breakouts are idiosyncratic noise that fail when the rest of the complex is weak.

**Data.** Daily closes of the traded coin and one gate coin. Both series must cover the requested window; the backtest refuses a factor whose dates do not overlap the trade leg.

**Rough rules.**

```text
# trade BTC, read ETH
gate_z = bollinger_z(ETH close, window=200)
signal = bollinger_momentum(BTC close)     # existing baseline
position_BTC = signal if gate_z > 0 else 0
```

**Why it might improve Sharpe.** Same channel as the own-price trend gate: fewer trades in risk-off regimes, lower downside variance. It is ranked second, not first, because BTC and ETH co-move strongly. If the ETH gate is just a noisy copy of the BTC 200-day filter, the extra parameter is overfit. Walk-forward and a swap of the two symbols are the checks.

**Reported performance.** Not stated. This combination was not found as a published backtest in the sources read for this note.

**Risks.** Correlation makes the gate redundant. Two windows (gate and signal) multiply the search space; the optimizer will like an in-sample pair. A cross-product factor that is missing bars used to fail silently; coverage now fails the job (decision #64). The position is still only in BTC — this is not a hedge.

**Fit here.** Expressible now. Set the gate factor's `symbol` to the second coin and `conjunction` to `FILTER`. The traded venue stays on the request, not on the factor ([the name records which venue was traded](../architecture/api.md#the-traded-venue-is-required-and-the-name-says-which-one)).

**AlgoDaemon testability:** As-is, but only among BTC, ETH, and BNB. One spot position; the gate is another of those three. No other coin. Hand-off row 3.

---

## 3. A published non-result

**Sources.** Klaus Grobys and Niranjan Sapkota, [Economics Letters, 2019](https://doi.org/10.1016/j.econlet.2019.03.028), *Cryptocurrencies and momentum*. English. Abstract only.

**Mechanism.** They implement "the popular momentum strategy" on 143 cryptocurrencies, 2014–2018.

**Reported performance.** The abstract states the result and does not give a Sharpe:

> Contrary to earlier studies our findings do not indicate any evidence of significant momentum payoffs, supporting the view that the cryptocurrency market is far more efficient than suggested in earlier studies.

**Why it is here.** It is the check on section 1 and on the cross-sectional factors on the [next page](volatility-and-cross-section.md). Momentum is not a settled fact across samples and constructions. A FILTER that helps on 2017–2021 and fails on a later bear market should be rejected, not re-tuned.

**Fit here.** No new rule. Use their sample split as a reason to insist on walk-forward before trusting a trend gate.

**AlgoDaemon testability:** Not a strategy. It is the reason to walk-forward rows 1 and 2 on each of the three coins instead of trusting one in-sample window.

---

## 4. Daily reversal in the cross-section, momentum in the liquid names

**Sources.**

- Adam Zaremba, Mehmet Huseyin Bilgin, Huaigang Long, Aleksander Mercik, and Jan Jakub Szczygielski, [International Review of Financial Analysis, 2021](https://doi.org/10.1016/j.irfa.2021.101908), *Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets*. English. Abstract only.
- Stjepan Begušić and Zvonko Kostanjčar, [arXiv:1904.00890](https://arxiv.org/abs/1904.00890), *Momentum and liquidity in cryptocurrencies*. English. Abstract; the HTML full text does not contain the word "Sharpe".

**Mechanism.** On a universe of thousands of coins, yesterday's losers outperform yesterday's winners. Zaremba and coauthors argue this is illiquidity: the handful of largest, most tradable coins show **daily momentum**, not reversal. Begušić and Kostanjčar form momentum-liquidity portfolios and also find momentum concentrated in the most liquid coins. They propose two long-only books — illiquid losers, and liquid winners — with better risk-adjusted performance than a cap-weighted market, without stating a number.

**Data.** Daily returns and a liquidity measure (volume or a spread proxy) for a wide universe. Delisted names matter; a universe of survivors flatters reversal and momentum alike.

**Rough rules.**

```text
# each day, across coins with a price yesterday
score = return_1d
# illiquid universe: long low score, short high score (reversal)
# liquid universe (BTC, ETH, and other names we would actually trade):
#   long high score, short low score (momentum)
# long-only variant from Begušić: hold liquid winners, or hold illiquid losers
```

**Why it might improve Sharpe.** A reversal book is closer to market-neutral, so its volatility can be much lower than a long-only coin. That is a Sharpe story only if the mean survives costs. For **this** book the useful implication is negative: do not bolt a one-day reversal onto BTC. The liquid-name evidence points back at momentum and at the trend gate.

**Reported performance.** Not stated as a Sharpe in either abstract. Zaremba et al. say the last-day reversal "is not subsumed by a broad range of other return predictors" and that the pattern "is cross-sectionally dependent on liquidity."

**Risks.** Most of the reversal lives in coins we cannot trade in size. Bid-ask and the 10 bp taker haircut dominate a one-day hold. Shorts on thin perps are an exchange-risk trade (squeeze, delisting, funding) that the spot engine does not model. Survivor bias.

**Fit here.** Not expressible. There is no cross-sectional rank, no liquidity sort, and no basket. A one-day RSI reversion on BTC alone would be the wrong translation of this paper. Ranked off the [try-first list](sharpe-ideas-index.md#try-these-first) for that reason.

**AlgoDaemon testability:** Can't be tested as published (thousands of coins, a short leg, an illiquid book). The liquid-name conclusion is already rows 2 and 5: daily momentum on BTC, ETH, and BNB, long or flat. A one-day reversal on those three is the wrong translation, and an hourly version fights the 10 bp fee.

---

## 5. What not to copy from a trend-following preprint

**Sources.** Duc Bui and Thanh Nguyen-Van, [arXiv:2602.11708](https://arxiv.org/abs/2602.11708), *Systematic Trend-Following with Adaptive Portfolio Construction* (AdaptiveTrend), 12 February 2026. English. Abstract only. Category `cs.CE`. Not peer-reviewed. Code was not audited.

**Mechanism.** The abstract describes 6-hour trend-following, a trailing stop tied to an intraday volatility regime, monthly selection by rolling Sharpe with a market-cap filter, and a fixed 70/30 long-short split motivated by crypto's positive drift.

**Reported performance.** The abstract states, for a 36-month out-of-sample window 2022–2024 across "150+ cryptocurrency pairs":

> AdaptiveTrend achieves an annualized Sharpe ratio of 2.41, a maximum drawdown of -12.7%, and a Calmar ratio of 3.18.

Those figures are the authors' claim. They are not reproduced here, and a drawdown of −12.7% on a 70/30 crypto book over 2022 is an extraordinary path. Treat the paper as a description of ingredients (trailing stop, vol regime, rolling-Sharpe selection), not as a target.

**Fit here.** 6-hour bars, a trailing stop, and a 150-name long-short book are all outside the engine. The ingredient we can test without new code is still the trend gate in section 1.

**AlgoDaemon testability:** Can't be tested as published. Six-hour bars, a 150-pair long-short book, and a trailing stop are outside the bot. The trend gate in row 1 is the piece that can be tested. Do not target the abstract's Sharpe of 2.41.
