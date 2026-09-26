# Volatility scaling and the cross-section

**Doc type:** strategy research  
**Status:** hypothesis — not backtested here.

Two different Sharpe levers are easy to mix up.

- **Volatility targeting** changes the *size* of one position so that risk stays near a constant. The mean need not rise. The denominator of Sharpe falls when high-volatility periods are sized down, provided expected return does not fall in proportion.
- **Cross-sectional factors** choose *which* coins to be long and short. The published spreads are large. They are also zero-investment portfolios over hundreds of names, gross of the costs that would hit a small-cap leg, and they are not a signal on BTC alone.

This page records both, and a practitioner attempt to combine factors with volatility weights.

---

## 1. Volatility-managed portfolios (the mechanism)

**Sources.** Alan Moreira and Tyler Muir, [Journal of Finance, 2017](https://doi.org/10.1111/jofi.12513), *Volatility-Managed Portfolios*. English. Abstract. The assets are the equity market and equity factors, plus the currency carry trade. This is **not** a cryptocurrency backtest.

**Mechanism.** Take less risk when recent volatility is high.

> Managed portfolios that take less risk when volatility is high produce large alphas, increase Sharpe ratios, and produce large utility gains for mean-variance investors. … Volatility timing increases Sharpe ratios because changes in volatility are not offset by proportional changes in expected returns.

**Data.** A return series and a trailing variance estimate. No cross-section required.

**Rough rules.**

```text
rv_t = stdev(log returns over L bars)       # they use variance; L is a month in the equity paper
scale_t = min(cap, target_vol / rv_t)       # cap = 1 for a spot book that cannot lever
position_t = sign_or_signal_t * scale_t

# smaller version that does not need a sizing layer:
gate_t = 1 if rv_t < threshold else 0
position_t = signal_t * gate_t
```

**Why it might improve Sharpe.** Crypto volatility clusters. A unit long through a crash dominates the standard deviation of the whole backtest. Scaling down, or going flat, in those windows cuts the denominator. Moreira and Muir's condition is the part to test rather than assume: if expected return falls one-for-one with volatility, scaling does nothing for Sharpe. The equity evidence says it does not. That has to be re-estimated on BTC, not imported.

**Reported performance.** The abstract says Sharpe ratios increase. It does not state a cryptocurrency Sharpe, and none is inferred here.

**Risks.** A target-vol rule levers up in quiet markets. Quiet crypto markets have ended in gaps; a cap at 1× (spot) avoids that leverage but also gives away the "buy calm" side of the equity result. Thresholds on `rv` overfit. Realized vol is itself noisy on daily bars. The strategy takes less risk in the periods that look like recessions, which Moreira and Muir flag as contrary to a simple risk-premium story — the same pattern in crypto may be a bull-market artifact.

**Fit here.** Not expressible. Positions are {−1, 0, +1} and the PnL line has no size multiplier (`quant/strategy/performance.py`). The binary gate is the version to build first: one realized-vol or ATR indicator, used as a FILTER, leaving the baseline signal untouched. Continuous sizing also changes turnover fees and live order quantity, which is why the [baseline note](crypto-spot-baseline-improvements.md#6-suggested-order-if-this-is-pursued) ranks full ATR targeting as a large change. Ranked third on the [try-first list](sharpe-ideas-index.md#try-these-first) as the gate, not as the scaler.

Bollinger z-score is not a substitute. The z-score divides price distance by volatility, so a threshold on it is a price extreme, not a volatility level. Bandwidth `(upper − lower) / middle` would be closer, and it is also missing.

**AlgoDaemon testability:** The binary gate is as-is on daily spot BTC, ETH, or BNB: flat when trailing realized vol is high, else the inner long. That uses closes the bot already has. Continuous scaling is as-is only if the bot accepts a weight in `(0, 1]`; spot cannot lever. Hand-off row 5. The equity paper's Sharpe is not a target.

---

## 2. Cross-sectional size, momentum, volume, volatility

**Sources.**

- Yukun Liu, Aleh Tsyvinski, and Xi Wu, [NBER Working Paper 25882](https://www.nber.org/papers/w25882), *Common Risk Factors in Cryptocurrency*, May 2019. English. Weekly magnitudes below are from this working-paper PDF.
- Same authors, [Journal of Finance, 2022](https://doi.org/10.1111/jofi.13119). English. Abstract only. The published abstract says **ten** characteristics form successful long-short strategies. The 2019 working paper says **nine**. Do not treat the weekly percentages as Journal of Finance figures.

**Mechanism.** Each week, sort coins with market cap above one million dollars into quintiles on a characteristic known at the sort, and hold the quintiles for the next week. The coin market, a size factor, and a momentum factor span the strategies that worked. The working paper's universe grew from 109 such coins in 2014 to 1,583 in 2018. The market factor itself is a cap-weighted index of 1,707 coins.

The nine strategies with statistically significant zero-investment returns in the working paper are: market capitalization, end-of-week price, maximum price during the week, one- through four-week momentum, dollar volume, and the standard deviation of dollar volume.

**Data.** Weekly market cap, price, dollar volume, and returns for every coin above the cap cutoff, including names that later died. A point-in-time cap is part of the signal. Using today's top-30 list for 2016 is lookahead.

**Rough rules.**

```text
# each week, among coins with cap > $1m
long  = bottom quintile of market cap          # small
short = top quintile                           # large
# momentum: long the highest past 1–4 week return, short the lowest
# volume:   long the lowest dollar volume, short the highest
# hold one week, equal-weight within the quintile, dollar-neutral
```

**Why it might improve Sharpe.** A dollar-neutral book cancels the coin-market move, which is most of a single-name variance. If the long-short mean is positive and stable, Sharpe rises because the book is no longer just long beta. The working paper's second result cuts the other way for *implementation*: the three-factor model drives the alphas of these nine strategies to insignificance. Once you are long the market, long small, and long momentum, the extra sorts do not add a separate premium in their sample. Stacking many characteristics on top of momentum is unlikely to be five independent Sharpes.

**Reported performance.** From the May 2019 working paper, excess weekly returns of the zero-investment quintile spreads. Not annualized, and not net of costs. The paper describes them as "about 3 percent" except where a tighter figure is given:

| Strategy | Construction | Excess weekly return |
|----------|----------------|----------------------|
| Market cap | Long smallest, short largest | 3.4% |
| End-of-week price | Long lowest price, short highest | 3.9% |
| Highest price of the week | Long lowest, short highest | 4.1% |
| 1-week momentum | Long winners, short losers | 2.7% |
| 2-week momentum | same | 3.3% |
| 3-week momentum | same | 4.1% |
| 4-week momentum | same | 2.5% |
| Dollar volume | Long lowest volume, short highest | 3.2% |
| Volatility of dollar volume | Long lowest, short highest | "about 3 percent" |

The working paper does not state a Sharpe ratio for these weekly spreads in the prose that was extracted. It does discuss a squared Sharpe ratio later, in a hedging exercise, without a single headline Sharpe for the tradable book. None is invented here.

The Journal of Finance abstract (2022) states the spanning result without those percentages:

> We find that three factors—cryptocurrency market, size, and momentum—capture the cross-sectional expected cryptocurrency returns. … Ten cryptocurrency characteristics form successful long-short strategies that generate sizable and statistically significant excess returns, and we show that all of these strategies are accounted for by the cryptocurrency three-factor model.

**Risks.** Capacity on the small, low-price, low-volume leg is poor; that leg is where the spread comes from. Weekly rebalance across hundreds of names is not free, and these returns are not shown net of a 10 bp taker fee. The sample is 2014–2018. [Grobys and Sapkota](momentum-reversal-filters.md#3-a-published-non-result) do not find significant momentum on 143 coins over a similar window, so construction and universe matter. Shorting small coins is an exchange and borrow risk. A three-factor explanation means the "nine alphas" are not nine separate strategies.

**Fit here.** Not expressible as a portfolio. There is no universe sort and no second leg. The implication for the coins we do trade is the one in [momentum and liquidity](momentum-reversal-filters.md#4-daily-reversal-in-the-cross-section-momentum-in-the-liquid-names): BTC is the large, liquid leg, which these sorts **short** in the size and volume strategies. Copying the size factor onto a BTC-only book would mean fading BTC, which is the opposite of the baseline. Ranked off the first-five list on purpose.

**AlgoDaemon testability:** Can't be tested as published (hundreds of coins, dollar-neutral shorts, a small-cap leg). Do not fade BTC for being large. The testable adaptation is hand-off row 6: long-only rank of BTC, ETH, and BNB.

---

## 3. Factor momentum

**Sources.** Christian Fieberg, Gerrit Liedtke, Daniel Metko, and Adam Zaremba, [Quantitative Finance, 2023](https://doi.org/10.1080/14697688.2023.2269999), *Cryptocurrency factor momentum*. English. Abstract via OpenAlex. Full text was not retrieved.

**Mechanism.** They replicate 34 cross-sectional anomalies on more than 3,900 coins, 2014–2022, and find that anomaly portfolios that won recently keep winning. The abstract says the autocorrelation is not widespread: it "primarily stems from size and volatility anomalies." Unlike stocks, "cryptocurrency factor momentum originates from price momentum, which subsequently transfers to the factor level."

**Rough rules.**

```text
# each formation date:
#   compute trailing return of each anomaly long-short
#   long the anomaly portfolios with high trailing return
#   short the anomaly portfolios with low trailing return
```

**Why it might improve Sharpe.** If factor premia themselves trend, a static weight on "momentum plus size" is dominated by a weight that follows the recent winners. The abstract's last sentence is the caution for us: this may just be price momentum showing up again at the factor level. Adding it on top of a price trend gate can double-count one effect.

**Reported performance.** Not stated as a Sharpe in the abstract. "Its magnitude parallels that of its stock market counterpart" is the strongest quantitative claim retrieved, and it is not a number.

**Risks.** Thirty-four anomalies on 3,900 coins is a multiple-testing factory. The result is concentrated in size and volatility anomalies, which are the least tradable legs. Overfit weights. Regime dependence if the post-2022 sample differs.

**Fit here.** Not expressible. No anomaly library and no portfolio of portfolios. Useful as a warning against a large FILTER stack of correlated price signals.

**AlgoDaemon testability:** Can't be tested. Thirty-four anomalies on thousands of coins do not fit three spot names. Treat it as a warning not to stack several price signals and call them independent.

---

## 4. Risk balance inside a long-short basket

**Sources.** ianzeng123, FMZ 文库, 31 August 2026 (updated 3 September 2026), [「牛来上了币安合约，恐高也恐低，于是我去做了一个不赌方向的策略」](https://www.fmz.com/digest-topic/11029). Chinese. Practitioner post, not a journal article. The title's coin is the Binance USDT perpetual 「牛来」; the strategy the author ends up describing is a **cross-sectional** book of meme perps, not a single-name trade in that coin.

**Mechanism.** The author argues that a high-volatility meme perpetual is a momentum asset, not a mean-reversion asset. Grid, dip-buying, and fading the funding print all bet on a snapback. The replacement is a dollar-neutral basket: price momentum plus a funding-rate score, long the strongest names and short the weakest, with weights inverse to volatility and a gross cap when estimated residual vol is high.

Original, then translation:

> 高波动的meme永续是动量型资产，不是均值回归型资产。
>
> A high-volatility meme perpetual is a momentum asset, not a mean-reversion asset.

> 价格动量告诉你「它涨了」，资金费率告诉你「有人愿意为这个方向付成本」。
>
> Price momentum tells you it went up. The funding rate tells you someone is willing to pay the cost of holding that direction.

Weights are not fixed. Each period the author runs a cross-sectional regression of the next return on the two z-scores, averages coefficients Fama-MacBeth style over 120 bars of 4-hour data (about 20 days), and shrinks a coefficient whose t-statistic is weak. Refit every 12 hours. The sign is allowed to flip if the regression says the factor changed sign.

**Data.** 4-hour bars, funding rate, and each contract's funding interval, for a pool of liquid meme perps (the post discusses pools of 44 and 35 names). Binance `fundingInfo` for the interval. Mark price for the hedge leg. A unified (cross) margin account, not isolated margin.

**Rough rules.**

```text
fund_8h = funding_rate * (8 / funding_interval_hours)   # see the carry note
z_mom   = zscore(price momentum)
z_fund  = zscore(fund_8h)
# weights = shrunk Fama-MacBeth betas, refit every 12h
score   = w_mom * z_mom + w_fund * z_fund
long the top slice, short the bottom slice, equal dollar gross
within a side: weight_i ∝ 1 / sigma_i
scale gross down if estimated residual vol > target
```

**Why it might improve Sharpe.** Inverse-vol weights stop two wild names from being the whole book. A vol cap stops the gross from ballooning when the complex is violent. Both act on the denominator. Market-neutral dollars cancel a common meme-sector move, so the mean only has to come from the spread between strong and weak names. The author also treats cross margin as survival, not as alpha: isolated legs liquidate even when the book is up.

**Reported performance.** The post does **not** state a Sharpe ratio for the full strategy. It does state the author's own before/after for the inverse-vol weight, on "the full sample," with three metrics moving together:

> 中位数从36.5个基点提到68.0、胜率从53%提到57%、单次最差从-2021收窄到-1422。
>
> The median went from 36.5 basis points to 68.0, the win rate from 53% to 57%, and the worst single outcome from −2021 to −1422.

The post does not define the unit of "2021" in the excerpt (it is the author's worst-trade statistic, not a return in percent that we can annualize). These are in-sample figures from the author who chose the change. They are not an independent backtest.

The same post says the funding factor's sign flipped when the pool went from 44 contracts to 35 and the window from 41 days to 31 days. That is a reported instability, not a performance claim.

**Risks.** 4-hour bars and a 10- to 20-name short book are outside this engine. Sign-flip of the funding factor is overfitting waiting to happen; shrinking by t-statistic reduces it and does not remove it. Meme perps delist, gap, and have funding intervals that change. Inverse-vol still needs a borrowable short. Cross margin reduces liquidation risk and increases the chance that one bad leg drains the account. The author's earlier failures (grid, fade-the-wick, funding-settlement scalp) are a reminder that mean reversion was the losing prior on this universe.

**Fit here.** The dollar-neutral basket does not fit. Two pieces do, later: the funding-interval normalization (next page), and the idea of a volatility **gate** rather than a volatility weight (section 1). Fama-MacBeth weights across two factors are not something AND/OR/FILTER can represent; those conjunctions do not estimate betas.

**AlgoDaemon testability:** Can't be tested as published (meme perps, 4-hour bars, a short book). The inverse-vol idea reduces to the flat-when-vol-is-high gate in hand-off row 5. Funding as a spot veto, not as a second leg, is row 8.

---

## 5. Adaptive weights across a perpetual universe

**Sources.** 发明者量化-小小梦, FMZ 文库, 7 September 2026, [「让因子接受持续考核：在 FMZ 实现 APFF 多品种永续合约策略」](https://www.fmz.com/digest-topic/11035). Chinese. APFF is the author's name for Adaptive Perpetual Factor Factory (多品种永续合约自适应因子工厂策略). Version cited in the post: v0.1.0, build 20260905-05. Practitioner post.

**Mechanism.** Five seed factors on a universe of about 30 Binance USDT linear perps, each turned into a cross-sectional rank, then combined with weights that are updated from each factor's later realized payoff. New candidate formulas have to sit in an observation window and then earn a small weight. BTC is reserved as a hedge leg and pulled out of the alpha ranking.

The post's own question, then a translation:

> 写一个动量因子并不难，写一个反转因子也不难。真正让人犹豫的是：两个因子今天给出了相反的意见，资金应该听谁的？
>
> Writing a momentum factor is not hard, and writing a reversal factor is not hard either. The real hesitation is: when the two factors disagree today, which one does the capital listen to?

Seed hypotheses, as stated (these are hypotheses, and the author says so):

| Factor | Sketch | Intended sign |
|--------|--------|----------------|
| Momentum | `(RET_7D − RET_4H) / RV_7D`, skipping the last 4h bar. 7 days = 42 bars of 4h | Continuation after removing the last shock |
| Reversal | `−RET_4H / RV_24H` | Snapback of the last 4h move |
| Funding crowding | `−Z` of the funding rate, scaled onto an 8-hour clock, over about 30 days | High funding versus own history, then weaker subsequent return |
| Premium | `−Z` of the premium series versus its own history | Rich premium mean-reverts |
| Open interest | sign of the 24h return times `Z` of the 24h log change in OI notional | Build in OI confirms the price direction |

Ranks are winsorized at 5% and 95% and mapped to a cross-sectional score. A factor must cover 80% of the names that round, and a name must have 80% of the live factor weight, or it is dropped. Volatility scaling, a per-name cap, and a limited BTC beta hedge sit on top of the rank. The universe is the top names by 24h quote volume, with a buffer so that a name just inside the top 40 can stay. At least 15 non-BTC names must pass the data checks. Weights move slowly; the post warns that recomputing weights on every book tick turns a medium-frequency book into a noise chaser.

**Data.** 4h completed bars (not the live bar), mark price, best bid and ask, funding history, premium index, open interest in quote notional, listing age (the post wants 90 days; the author says missing listing time means the code cannot prove that). Production premium history and the simulator's accumulated premium are not the same series, and the author says simulator factor results must not be read as production results.

**Why it might improve Sharpe.** Disagreeing factors are the interesting part. A fixed 50/50 weight between momentum and reversal pays for both and earns neither when they cancel. A weight that shrinks the factor whose recent forward return was poor is a crude version of the factor-momentum result in section 3, applied on-line. Vol scaling is section 1 again. The BTC hedge is there because equal long and short notionals do **not** remove market risk when the long leg is the high-vol names.

**Reported performance.** Not stated. The author writes:

> 目前的运行和模拟测试验证了主要工程流程，长期收益效果仍需后续样本检验。
>
> Runs and simulation tests so far have checked the main engineering path. Long-run performance still needs a later sample.

A numerical example in the post (long basket +4%, short basket +1%, on 3,000 USDT a side, before fees and funding, PnL = 90 USDT) is an illustration of spread PnL, not a backtest.

**Risks.** The author lists unfinished filters: 30-day average volume, point-in-time membership, continuous history, and book depth are not fully implemented. Simulator versus production premium is a silent bias. Five factors plus a weight learner on 30 names will overfit a short sample. Funding and premium factors can stay "wrong" for a long time; the post says a high funding rate does not mean the price falls soon. 4h bars, a 30-name book, and a BTC hedge are all outside this engine. Exchange risk on the short leg remains.

**Fit here.** Not as a portfolio. The design lesson that does transfer: if we ever add a second factor, give it a job (gate versus signal) instead of averaging two conflicting {−1, 0, +1} series with a hand-picked weight. FILTER already does that. Learning the weight from trailing factor PnL would be a new objective, not a new indicator, and it is a research idea rather than something to build on this evidence.

**AlgoDaemon testability:** Can't be tested. The book is about thirty perpetuals on 4-hour bars, with open interest and a BTC hedge. There is no Sharpe here to chase. Funding as a filter on spot BTC, ETH, or BNB is the only fragment that can be adapted, and only when that series is supplied (hand-off row 8).
