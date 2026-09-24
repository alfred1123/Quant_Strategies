# Funding, basis, and carry

**Doc type:** strategy research  
**Status:** hypothesis — not backtested here.

Perpetual futures do not expire. The instrument that pulls the perpetual toward the spot is a **funding payment**, usually from longs to shorts when the perpetual is rich, and the other way when it is cheap. Two trades get talked about as if they were one:

1. **Carry.** Hold spot against a short perpetual (or the reverse) and collect funding while the hedge is on. The bet is that funding stays on your side and the hedge does not break.
2. **Deviation / convergence.** Trade when the perpetual-spot gap leaves a no-arbitrage band, and close when it comes back. Funding is part of the pricing, but the PnL is mostly the gap closing.

This engine marks neither funding nor a second leg. The piece worth stealing first is narrower: use an extreme funding reading as a **filter on a single coin**, once the series exists.

The platform already records that funding is not in the backtest. See [Transaction costs](../guides/indicators-strategies.md#transaction-costs): daily bars hide most 8-hour funding, and a hourly hold that spans a settlement does not.

---

## 1. What the funding rate is

**Sources.**

- Damien Ackerer, Julien Hugonnier, and Urban Jermann, [NBER Working Paper 32936](https://www.nber.org/papers/w32936), *Perpetual Futures Pricing*. English. Abstract.
- Songrun He, Asaf Manela, Omri Ross, and Victor von Wachter, [arXiv:2212.06888](https://arxiv.org/abs/2212.06888), *Fundamentals of Perpetual Futures*. English. This draft September 2026; first draft December 2022.

**Mechanism.** Ackerer, Hugonnier, and Jermann: the perpetual has no expiry, and "the anchoring of the futures price to the spot price is ensured by periodic funding payments from long to short." They derive no-arbitrage prices for linear, inverse, and quanto perpetuals. He, Manela, Ross, and von Wachter put the same object in trading language: unlike a dated future, a perpetual is not guaranteed to converge; longs periodically pay shorts a rate proportional to the gap, to shrink it. Their no-arbitrage price in a frictionless market, and bounds when trading costs are positive, are the benchmark the strategy in section 3 trades against.

**Reported performance.** Not a trading Sharpe, in the Ackerer-Hugonnier-Jermann abstract. The He et al. Sharpe ratios are in section 3, and they belong to the convergence trade, not to "funding is positive, therefore short."

**Fit here.** Background. No code change follows from the pricing papers alone.

---

## 2. Normalize the clock before you rank funding

**Sources.** Both FMZ posts below, Chinese. The interval counts are the author's, at the time of the post, not an exchange specification we re-checked.

- ianzeng123, [FMZ, 31 August 2026](https://www.fmz.com/digest-topic/11029).
- 小小梦, [FMZ APFF, 7 September 2026](https://www.fmz.com/digest-topic/11035). The APFF post points at FMZ `GetFundings` for the current window and at Binance `GET /fapi/v1/fundingRate` (`fundingTime`, `fundingRate`) for history.

**Mechanism.** A funding print of 5 bp is not the same economic object on a 4-hour contract and an 8-hour contract. The 4-hour contract settles twice as often, so the daily cost is about twice as large. Ranking raw prints pushes 4-hour contracts systematically to one side of the book.

The 31 August post says that of 768 contracts with a `fundingInfo` record, 440 settled every 4 hours, 324 every 8 hours, and 4 every 1 hour. 「牛来」 itself was a 4-hour contract. APFF does the same rescaling and then takes a time-series z-score over about 30 days, and it refuses a stale or short history rather than inventing a number.

**Rough rules.**

```text
fund_8h = funding_rate * (8 / funding_interval_hours)
z = (fund_8h - mean(fund_8h, ~30d)) / stdev(fund_8h, ~30d)

# single-name filter, the version aimed at this repo:
# do not add a new long when z is extremely high
# (longs are crowded and paying)
position = 0 if (signal > 0 and z > z_hi) else signal
```

APFF's cross-sectional version flips the sign on purpose (`−Z`): high funding versus a name's own history is a reason to be short that name, as a hypothesis. The author of that post says the hypothesis can be wrong for a long time, because crowded trades persist. The 31 August author went further and **estimated** the sign: a Fama-MacBeth coefficient is allowed to come out negative, and a fixed +0.6 weight on funding was rejected as arbitrary. The same author reports that the funding factor changed sign when the universe and the window changed (44 names / 41 days versus 35 names / 31 days).

**Why it might improve Sharpe.** For a long-only BTC book, the plausible channel is drawdown control, not carry collection. Adding longs when funding is already stretched stacks the position into the crowd that is paying the short. Skipping those entries cuts a left tail if the crowd later unwinds. That is a lower-volatility path through the same mean, which is a Sharpe claim only if the skipped trades were not the right tail as well. It has to be tested. It is not the same claim as "short rich funding and earn the payment."

**Reported performance.** Neither post states a Sharpe for a funding filter on one coin. The inverse-vol figures on the [cross-section page](volatility-and-cross-section.md#4-risk-balance-inside-a-long-short-basket) are about position weights, not about this gate. He et al. (section 3) are about the gap, not about a z-score of funding.

**Risks.** Sign instability is the main one, and it is reported by the person trading it. Interval metadata can be wrong or can change mid-sample; a backtest that assumes 8 hours for every contract is a biased rank. Funding is a price of leverage, so it spikes in the same crashes a trend filter would also flat — the two gates can be the same trade counted twice. Exchange outages and premium-index definition changes break the series. Capacity of a crowded-funding fade is limited because everyone sees the same print.

**Fit here.** Not yet. Nothing in `REFDATA.DATA_COLUMN` is a funding rate, and the PnL line does not add funding. Ranked fourth on the [try-first list](sharpe-ideas-index.md#try-these-first) because the *signal* is a filter we already understand: store `fund_8h` (or its z-score) as a series on the traded coin, point a factor at that column, and FILTER the baseline. That is a data task plus an indicator if the z-score is not precomputed. It is not a new position algebra, and it is not a hedge.

---

## 3. Random-maturity arbitrage around the no-arbitrage bound

**Sources.** He, Manela, Ross, and von Wachter, [arXiv:2212.06888](https://arxiv.org/abs/2212.06888), HTML full text of the September 2026 draft. English.

**Mechanism.** When the futures-spot spread is outside the band implied by a trading-cost tier, open the side that bets on a return to the band, and close when the spread is back inside the no-cost relationship. The hold is hours, not a fixed horizon ("open-to-close" times in their Table 5 are on the order of 3–11 hours for BTC). They call this random-maturity arbitrage. Deviations are larger in crypto than in traditional currency markets, move together across coins, and have shrunk over time.

**Data.** Perpetual price, spot (or index) price, a cost tier, and enough history to know the band. Bid-ask if the spread-adjusted numbers are the ones you care about. Funding enters the pricing bound; it is not a separate overlay in the headline backtest.

**Rough rules.**

```text
rho = perpetual / spot - 1          # their deviation, up to scaling and the clamp
if rho > band(cost_tier):  short perpetual, long spot
if rho < -band(cost_tier): long perpetual, short spot
exit when rho returns to the no-cost benchmark
```

**Why it might improve Sharpe.** The position is hedged, the hold is short, and the edge is a gap that the contract design tries to close. Volatility of a hedged book is a few percent a year in their zero-cost table, so even a modest mean produces a large Sharpe. That arithmetic is why the ratios below look nothing like a long-only BTC Sharpe near 1.5. They are not comparable, and they are not available to a one-leg spot strategy.

**Reported performance.** All figures in this section are the authors', from the September 2026 draft, and are not reproduced here.

Prose, Bitcoin, with costs:

> For example, for Bitcoin perpetual futures, the strategy generates a Sharpe ratio of 3.35 under high trading costs typical of retail investors, and up to 11.65 for highly active market makers who pay no such fees. After additionally accounting for effective bid-ask spreads, the corresponding Sharpe ratios remain 3.27 and 10.46.

Table 5 is the **zero-trading-cost** version. The caption describes Sharpe ratios, annualized returns (%), standard deviations (%), maximum drawdowns (%), and average open-to-close time in hours. Bitcoin, all years in that table:

| | BTC, zero trading cost, full sample in Table 5 |
|--|--|
| Sharpe ratio | 11.65 |
| Annualized return | 52.55% |
| Annualized volatility | 4.51% |
| Max drawdown | −3.82% |
| Mean open-to-close | 4.92 hours |
| N (hourly observations, as printed) | 36,578 |

Year columns for BTC Sharpe in the same table: 7.18 (2020), 12.36 (2021), 37.85 (2022), 15.37 (2023), 11.84 (2024). The 2024 column has N = 1,682, so it is not a full year in the draft. Ether's full-sample zero-cost Sharpe in the same table is 12.77. The authors say the strategy's alpha is significant against the three-factor model of Liu, Tsyvinski, and Wu (2022) and against a five-factor model of Cong, Karolyi, Tang, and Zhao (2022b). That five-factor paper was not retrieved for this note; only the citation is recorded.

A Sharpe of 37 in one calendar year, on a zero-cost assumption, is a reason to read the table as an upper bound on a closing gap, not as a capacity-ready track record. The cost-aware Bitcoin figure they lead with is 3.35, not 11.65.

**Risks.** Two legs, two venues or two margin pools, and a failure mode where the gap widens instead of closing. Latency: the edge is a few hours. Fees and the bid-ask are the difference between 11.65 and 3.35 in their own numbers. The common factor in deviations, which they document, means the "idiosyncratic" gaps are not fully idiosyncratic — a book of five coins is one trade in a stress week. Exchange failure, automatic deleveraging, and index dislocation are not in a frictionless bound. Capacity shrinks as the deviation itself shrinks, which they say has been happening. None of this is a spot signal.

**Fit here.** Not expressible, and not on the first-five list. A research spike would be a new backtest object (two series, a spread, an exit on convergence, funding cashflows), which is platform design, not a FILTER. Until that exists, quoting 3.35 as a goal for the Bollinger baseline is a category error.

---

## 4. Cash-and-carry as a holding strategy

**Sources.** The pricing papers in section 1, plus the practitioner warning in section 5. A standalone audited carry backtest with a stated Sharpe was **not** retrieved in this pass. Binance and OKX research pages that might have contained one did not return article text (see the [access log](sharpe-ideas-index.md#sites-that-were-inaccessible-paywalled-or-empty)).

**Mechanism.** When the perpetual is persistently rich, buy spot, short the perpetual in the same notional, and collect funding each settlement. Delta is near zero if the hedge ratio is maintained. PnL is funding minus fees, minus basis slippage, minus any borrow or margin cost. When funding is persistently negative, the sides flip: short spot (if borrow exists) and long the perpetual.

**Rough rules.**

```text
if fund_8h > entry and basis > 0:
    long spot, short perp, matched notional
    rebalance when hedge drift exceeds a band
exit when fund_8h < exit or the basis inverts through the cost
```

**Why it might improve Sharpe.** The residual is a financing spread, not the coin's return. Variance collapses relative to long-only spot if the hedge holds. The Sharpe is then the spread divided by hedge-error volatility. That is attractive exactly when the spread is stable and the hedge does not gap.

**Reported performance.** Not stated by a source we could read. Do not borrow the section 3 ratios; those include active entries and exits around a bound, not a passive carry book.

**Risks.** Funding can flip and stay flipped (the short then pays). Liquidation of the perp leg while the spot leg is fine turns a carry into an unhedged long. Delisting, collateral coins, and negative-funding squeezes are exchange risk. On a single-venue unified account the legs share margin; that cuts liquidation risk and couples their failure. Capacity is the open interest willing to pay the rich funding. Fees on rebalance matter if the hedge is adjusted often; the Russian fee note in section 5 is the practitioner version of that point.

**Fit here.** Not expressible. Same gap as section 3: one position, no funding cashflow.

---

## 5. Two practitioner warnings

**Sources.** Russian, Habr.

- Alex-ok, 20 May 2025, [«Арбитраж криптовалют — или переливаем из пустого в порожнее»](https://habr.com/ru/articles/911056/). The title translates as *Crypto arbitrage — or pouring from one empty vessel into another*.
- negrbluad, 30 August 2025, [«Комиссии криптобирж в алготрейдинге: подводные камни, сравнение и практические выводы»](https://habr.com/ru/articles/942400/) (*Crypto-exchange fees in algo trading: pitfalls, a comparison, and practical conclusions*).

**What they actually say.** The first post is not a carry strategy. It says public Telegram channels selling crypto arbitrage are often fraudulent, that a search turns up scam projects before research, and that marketing pages show fake profit testimonials. The fee post argues that designing on raw prices, ignoring maker versus taker, is the usual way a bot dies. The author writes that in practice the commission is the first filter that kills strategies before a real launch. That sentence is the author's judgment, not a measured failure rate we should quote as a statistic.

**Why it is here.** Carry and "arbitrage" are the words those channels use. A reported Sharpe from an anonymous screenshot is not a source. The fee point matches a result we *can* cite with a number, from the [roll-out replication](microstructure-onchain-unusual.md#1-the-24-hour-roll-out-effect): the same hourly signal is positive before costs and negative at a 10 bp taker round trip.

**Fit here.** No strategy to add. Keep the default 10 bp taker haircut honest when anyone proposes a hold shorter than a day. Live apply is a market order (decision #38), so the haircut is taker, not maker.
