# Japanese and Korean crypto strategy sources

**Doc type:** strategy research  
**Status:** Two hand-off specs have been sent to the AlgoDaemon Quant Researcher; platform results pending.

Public Japanese and Korean pages describe a few rules that English trend write-ups tend to skip: a Bitcoin moving-average regime used as a switch for altcoins, a kimchi-premium overheat level, funding and Nasdaq state for crash entries, and a habit of not trusting the 00:00 UTC daily close. This note ranks those ideas for AlgoDaemon. The target book is Bybit spot BTC, ETH, and BNB, 10 bps, daily bars preferred and hourly allowed, a position in {−1, 0, +1}, stateless signals, and the indicators the engine already has (SMA, EMA, RSI, Bollinger z-score, stochastic). A second factor may be a `FILTER` gate. The compilation used public pages only. Nothing was signed up for, joined, or bought, and no backtest was run for this page.

Plain moving-average crosses and Donchian trend-following show up often in these sources. They are not re-ranked here. That family is already queued on [Catching crypto trends](catching-crypto-trends.md), [Methods from the PolyU quantitative trading course](polyu-quant-course-methods.md), and the [Dutch Algotrading Patreon review](dutch-algotrading-review.md).

!!! warning "Figures below are the authors' claims"
    Every performance number on this page is the author's own claim, or a figure printed on the public page named with it, for the period and market that page states. They have not been reproduced here. Do not read them as AlgoDaemon results or as expected live performance.

Tags mean the following. **Testable now** can run on AlgoDaemon as it stands, and the rule is specific enough to enqueue. **Needs backend** names a missing capability (fractional size, a calendar feature, an intraday stop, a stateful exit). **Needs external data** names a series this book does not store. The order is a judgement of the Sharpe benefit expected for BTC, ETH, and BNB daily. It is not a measured ranking.

## Ranked ideas

| Rank | Idea | Source | Tag | Rule, in one line |
|------|------|--------|-----|-------------------|
| 1 | Volatility-targeted "super uptrend" | [TenMillionQuant](https://tenmillionquant.tistory.com/34), from Kang Hwan-guk (KR) | Needs backend | Long only while close is above SMA(3), SMA(5), SMA(10), and SMA(20). Size is at most 1, and at most 2% divided by a 5-day average of (previous high − previous low) / open. |
| 2 | BTC-regime gate for alts | [Busan Ilbo interview](https://www.busan.com/view/busan/view.php?code=2025060213362646803) with Kang Hwan-guk (KR) | Testable now, if the gate can read BTC closes while the trade is ETH or BNB. Otherwise needs a small backend change. | `FILTER` the alt's own trend with BTC close above its 120-day average. |
| 3 | Kimchi-premium regime | Kang's overheat list, plus [Capital Noted](https://capitalnoted.com/is-the-korean-kimchi-premium-still-front-running-bitcoin-price/) (EN, on Korean data) | Needs external data | Flat when the Upbit premium is at least 10%. Optionally allow a new long only after the premium has recently crossed up through zero. |
| 4 | Nasdaq "risk-on" plus a funding state, for BTC crash-buys | [tikeda123 on Qiita](https://qiita.com/tikeda123/items/c38b1dbc85d02f99c32c) (JP) | Needs external data | Buy a crash only when the Nasdaq 5-day return is positive. Skip the buy when funding is in its top fifth and that Nasdaq return is negative. |
| 5 | Funding-rate contrarian | [りょうP on note](https://note.com/ryo_bitbank/n/ndd379b02ace0) (JP) | Needs external data, and a stateful exit | Long when funding is negative. Flat once funding reaches +0.01%. |
| 6 | Noise-ratio chop filter, in a close-only form | [TenMillionQuant](https://tenmillionquant.tistory.com/44), from the same Kang book (KR) | Testable now | `FILTER` a trend rule with RSI(N) at or above 50 × (1 + e), so the book only trades when directional efficiency is high. |
| 7 | Anchor-free daily rules | [퀀트픽](http://coinpick.com/daily_quant/14308) (KR) and a [Qiita shifted-bar note](https://qiita.com/pip_pip_pip_p/items/839b90222ae7cc969422) (JP) | Testable now, on hourly bars | Re-run a daily rule on 1-hour closes with every window multiplied by 24, so the result does not depend on the 00:00 UTC close. |
| 8 | Weekday and month seasonality | [Money Partners](https://www.moneypartners.co.jp/mplab/column/column_bitcoin-weekday-anomaly.html) (JP) and a [Kang seasonality summary](https://firelife.tistory.com/50) (KR) | Needs backend | Flat on Thursdays, or a long bias only from November through April. |
| 9 | Larry Williams volatility breakout, Korean variants | [WikiDocs Bitcoin autotrade](https://wikidocs.net/book/1665) and many Upbit bots (KR) | Needs backend | Buy when price reaches today's open plus k times the previous high-low range. Sell at the next open. Often only if the open is above a short average. |
| 10 | Opening-range breakout ("Doten-kun") | [UKI](https://note.com/uki_profit/n/nad33f21ede74), rule checked by [nehori](https://nehori.com/nikki/2022/02/13/post-38010/) (JP) | Needs backend | On 2-hour bars, go long the next bar when high − open is at least 1.6 times the average range of the last five bars. Reverse on the opposite signal. |
| 11 | Heikin-Ashi as momentum that drops the last day, plus a one-day reversal | [richmanbtc](https://note.com/btcml/n/n6198a3714fe5) (JP) | Testable now as an approximation. Overlaps the queued dip family. | Long when a short momentum measure that excludes today is positive and today was down. |
| 12 | Minute-of-hour reversal | [Hoheto](https://note.com/hht/n/nc0caf98477db) (JP) | Not applicable | At one minute past the hour, fade the prior five-minute move and exit after about half an hour. Needs minute data. |

**How to read the top of the list.**

Rank 1 is evidence for sizing, not a new signal. The stateless piece is short-horizon trend-following: long when close is above the highest of SMA(3), SMA(5), SMA(10), and SMA(20), otherwise flat. With only two conditions that is approximately `FILTER(close > SMA(3), close > SMA(20))`. The reported drawdown is low because a fixed 2% daily-range target often leaves BTC only partly invested. Fractional weights and a volatility scale are [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) and [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight) of the [backend proposal merged in PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63). TenMillionQuant, replicating Kang's book on Bithumb BTC from January 2014 to March 2022 at a 0.2% cost, claims a cumulative 169× against about 70× for buy and hold, with a maximum drawdown of −16.7%. That test is one coin and in sample. The same author's replications of the breakout variants were large losses; those are in [Korean volatility-breakout replications](#korean-volatility-breakout-replications). A related Excel book from SugangLive (noise-scaled breakout, a moving-average score, and volatility sizing, on BTC, ETH, XRP, DOGE, and LTC, January 2017 to January 2022, cost 0.2%) claims a portfolio return of 31093% and a maximum drawdown of −0.0819292. SugangLive's version of the range target is 5%, not 2%.

Rank 2 is the idea worth a platform run. Kang's public statement of the rule is that a cross above the 120-day average is an uptrend, a cross below it is a downtrend, and alts should be sold together with Bitcoin when Bitcoin falls under that average. A dual-momentum variant in a book summary holds the top three of the top twenty alts by one-week return, one third each, and only on Tuesdays when BTC is above the 120-day average; otherwise cash. That sleeve is cross-sectional, so this engine cannot run it. The public pages give no numeric results, only that the return is good. The book's tables are paywalled, and 120 days was likely chosen in sample. The spec that was sent is [below](#btc-regime-gate-for-eth-and-bnb).

Rank 3 needs a Korean premium series. Capital Noted, on 2025 data only, claims that zero-crossings from a discount to a premium were followed by an average return of +1.7% after seven days and +6.2% after thirty days, with win rates of 67% and 70%. The same note says the correlation between the premium's level and forward returns is slightly negative, about −0.06, and that Coinbase-premium flips lead to roughly flat returns. That is one year and a small number of crossings. The 10% "overheat" level shows up in manias (2017–18, 2021, and October 2025, when a 52-week Upbit Data Lab range ran from 8.08% to −3.29%). A 90-day mean on KIMP Radar for 17 June 2026 to 14 September 2026 was −0.018%, so the premium is usually near zero and the extreme gate almost never fires. A Korean academic paper finds the premium mean-reverts with the exchange rate (Upbit versus Binance, 26 September 2017 to 6 April 2023). That is an arbitrage result, not a direction. Usable inputs, once someone loads them, are Upbit's public daily candles for KRW-BTC (from October 2017) and KRW-USDT, or FRED dollar-won (`DEXKOUS`) with a forward-fill, against a USDT close. Upbit Data Lab's own premium series starts only on 19 June 2024. CryptoQuant's longer Korea Premium Index is a paid API. The rule to test after the data exists is an exit overlay `gate = premium < 10%`, swept at 5%, 8%, 10%, and 15%, on the existing trend rules, and optionally an entry that requires a cross up through zero within the last 5, 10, or 20 days.

Rank 4 is an event study, gross of costs, on 4-hour bars from May 2017 to June 2026. The author calls a crash a 4-hour return below its rolling 180-bar mean minus two standard deviations, enters at the next 4-hour open, and exits after 24 or 48 hours with a 24-hour cooldown. Author's claims: all crashes, held 48 hours, average +0.603%, profit factor 1.368, n = 201; the risk-on subset, +1.431%, profit factor 2.375, t-statistic 3.024, n = 88; funding in its top fifth and Nasdaq down over five days, held 24 hours, −0.242%, profit factor 0.837, n = 26. The author also says the interaction term is not statistically significant. The headline cell is small (n = 15 in the write-up's tightest cut), and 2022 contributes n = 4. A daily translation, if a second factor could read an external close, would be `FILTER` of a queued dip rule with Nasdaq close above its close five days earlier. Nasdaq daily (`NASDAQCOM` on FRED) and Bybit funding history are both free. Neither is wired in.

Rank 5, on Binance USD-M hourly bars, long only, full size, 0.06% per side: enter when funding is negative (lagged one bar) and exit when funding reaches +0.01%. The author's claim for ETH/USDT from December 2020 to December 2025 is 75 trades and a total return of 399.09%. Other coins in the same note: SOL 123.29%, AVAX −31.45%, DOGE −32.66%. There is no buy-and-hold number and no Sharpe. The author describes the book as close to holding. The entry and exit thresholds differ, so a faithful port is stateful. A stateless stand-in, long while an 8-hour average of funding is below a threshold, still needs the funding series.

Rank 6 is a filter on trend rules, not a new return. The book's noise ratio is 1 minus the absolute open-to-close move divided by the high-low range, averaged over 20 days, and the book uses that average as the breakout coefficient. The stated logic is that low noise means the bar is trending and high noise means it is prone to reverse. The original needs intraday open, high, and low. A close-only translation, derived for this note and not claimed by the author: Kaufman's efficiency ratio over N bars equals the absolute value of 2 × RSI/100 − 1 when RSI is a simple average of up and down moves, so RSI(N) at or above 50 × (1 + e) means up-direction efficiency of at least e. Wilder's RSI is the same idea with an exponential weight. The two public replications of the original disagree: TenMillionQuant's noise-scaled breakout plus a moving-average score, on BTC, LTC, ETC, and XRP, Bithumb from June 2017 to March 2022 at 0.2% cost, printed a return of −48.69878948390697 and a maximum drawdown of −69.87742425708808; SugangLive's Excel version of a similar rule is the 31093% portfolio above. This row was not sent as its own sweep. Drop it if the queue already gates trend entries on RSI.

Rank 7 is the second spec that was sent. See [Hourly re-run of daily rules](#hourly-re-run-of-daily-rules). The Korean post moved a volatility-breakout anchor to 10:00 Korea time. On a short sample from 1 January 2019 to 10 November 2020, with a 0.5% round trip, the author claims an annual compound return of 80.55% and a maximum drawdown of −16.87% on BTC, and an annual compound return of 140% with a maximum drawdown under 15% on ETH. Those figures are anchor-optimised, the sample is short, and the author sells a program. The Qiita note built 24 hour-shifted daily bars and reports that the same Heikin-Ashi rule stops working on a bar shifted by 12 hours. The author's suggestion is that technical rules work on the standard daily close because that is the close everyone watches. That cuts both ways: the 00:00 UTC edge may be real microstructure, and a daily Sharpe may be partly luck of the anchor. Clock-time effects already on this wiki are in [Microstructure, on-chain, and unusual](microstructure-onchain-unusual.md#2-clock-time-bursts-and-order-book-features).

Rank 8, from a broker column on Dukascopy BTC/USD daily open-to-close returns, 1 January 2021 to 31 December 2025: Monday 0.19%, Tuesday 0.04%, Wednesday 0.44%, Thursday −0.18%, Friday 0.02%, Saturday 0.07%, Sunday 0.18%. The column calls Wednesday a consistent rise and Thursday a consistent fall. Five years, no significance test, and a marketing page. Kang's seasonality chapter, via a public summary, says Bitcoin is mostly strong from November through April and weak from May through October. A month effect has about ten independent observations per calendar month. A day-of-week or month feature does not exist on the engine. If it is added, "flat on Thursday (UTC)" is a cheap overlay on a queued trend rule and a high multiple-testing risk.

Rank 10 is one month of leveraged profit on bitFlyer BTC-FX in March–April 2018: the author's claim is 20 million yen to 100 million yen in about a month. A later port of the same shape to Japanese stocks, 2000–2022, printed a profit factor of 1.09 and an average annual return of 6.47%. That is a different market, so it is not evidence for BTC. The rule needs high, low, and a stop-and-reverse. A close-only cousin, a short-window Bollinger z-score above about 1.5, is just short-term momentum.

Rank 11 has charts and no costs. A follow-up says the rule worked reasonably well through the first half of 2021 and fails when the daily bar is shifted by 12 hours. A long-only approximation is `FILTER(RSI(2) below 30, 40, or 50, with EMA(3) above EMA(10))`. That overlaps the dip rules already queued from the PolyU notes, so it was not sent as a separate hand-off.

Rank 12 is minute data and a hold of about 28–30 minutes, strongest at 09:00 Japan time, which is 00:00 UTC. The sample is one-minute BitMEX index data from July 2019 to June 2020, charts only, gross of costs. The author says implementing the published strategy on its own will not make money, because of costs and hourly turnover. The only takeaway for this book is that the 00:00 UTC daily close is a real microstructure event. Korean volatility-breakout bots sell just before 09:00 Korea time and buy after it, and Upbit's daily candle resets at 00:00 UTC, which is a plausible source of that print.

## Hand-offs sent to the researcher

Two specs were sent. Both avoid a plain trend cross and the RSI or Bollinger dip family already in the queue. The other ideas above need a series or a backend this engine does not have. Rank 6 is testable and was not part of the send: it is a quality filter on rules the queue already has.

### BTC-regime gate for ETH and BNB

From Kang Hwan-guk's 120-day Bitcoin average, rank 2.

**Hypothesis.** Alt drawdowns are driven by the Bitcoin regime. Gating ETH and BNB on Bitcoin's trend should cut whipsaw that belongs to the alt, and should cut deep alt drawdowns, more cleanly than the alt's own trend does.

**Prerequisite.** The gate has to read BTCUSDT closes while the traded symbol is ETHUSDT or BNBUSDT. If a second factor can only see the traded symbol, this needs one backend change, a cross-symbol close, and it should not be forced into a same-symbol stand-in.

**Variants.** Daily bars, long only, positions in {0, +1}, 10 bps per side.

- V0, the published rule with no extra filter: ETH or BNB is long when BTC close is above SMA(BTC close, L_btc), and flat otherwise.
- V1, the gate on the alt's own trend: `FILTER(primary = own close > SMA(own close, L_own), gate = BTC close > SMA(BTC close, L_btc))`.
- V2, the same gate on a dip rule already in the queue: `FILTER(primary = the queued ETH or BNB dip, gate = BTC close > SMA(BTC close, L_btc))`.

**Sweep.** L_btc in {60, 90, 120, 150, 200}. 120 is the author's value. Repeat the same lengths with an EMA. L_own in {20, 50, 100, 120, 200}.

**Benchmarks.** ETH and BNB buy and hold. The own-asset rule close > SMA(close, 120). V1 with the gate removed.

**What would count as a success.** V1 Sharpe at least 0.1 above the own-trend Sharpe, with a lower maximum drawdown, on both ETH and BNB. The result has to hold across L_btc from 90 to 150, not at a single length. Split the sample into 2018–2021 and 2022–2026.

**Watch.** BNB's Bybit spot history is shorter than BTC and ETH; check the listing date before reading a long window. BTC and ETH are highly correlated, so the gain may be small on ETH and larger on BNB.

A separate, already-run question — whether the z-score form of a BTC gate is the same strategy as several other trend candidates — is on [Which candidate strategies to merge vs run as separate sleeves](merge-vs-distinct-candidates.md). That page's merged rule is a Bollinger threshold, not this SMA(120) gate. Do not treat the two as the same sweep.

### Hourly re-run of daily rules

From the Korean practice of spreading a daily signal across bar anchors, and from the Japanese check that a shifted daily bar can erase a rule. Rank 7.

**Hypothesis.** A daily rule's Sharpe on 00:00 UTC bars includes luck of the anchor. Running the same rule on 1-hour closes, with every window multiplied by 24, does not depend on that anchor. It shows whether the edge is the rule or the clock.

**Test.** Hourly bars, 10 bps. For each daily rule R(L) already queued, for example close above SMA(L), or a fast EMA above a slow EMA, run the same rule with every window times 24. An SMA of 50 daily closes becomes an SMA of 1,200 hourly closes. EMA(12) and EMA(26) become EMA(288) and EMA(624).

Turnover on an hourly signal can be high. Without a stateful hold, keep it in check with a slower gate: `FILTER(close > SMA(24 × L), close > SMA(24 × L_slow))`, with L_slow in {1.5 L, 2 L}. Report turnover and the fees paid, not only Sharpe.

Compare Sharpe, maximum drawdown, turnover, and fee drag with the daily rule R(L).

**Sweep.** L is whatever daily length is already queued for that rule. The slow-gate multiplier is 1.0 (no extra gate), 1.5, or 2.0.

**How to read it.** Hourly Sharpe close to the daily Sharpe means the edge survives the anchor, and the hourly form can be used to diversify anchors. Hourly Sharpe clearly worse, before fees, means part of the daily edge is the 00:00 UTC print. Keep the daily bars, and treat the daily Sharpe as optimistic.

Shifting the daily anchor itself (06:00, 12:00, and 18:00 UTC, against 00:00) would be a cleaner four-way comparison. That is a small backend item. It is not required for the hourly check.

## Korean volatility-breakout replications

The volatility breakout is the workhorse of Korean retail crypto bots, and the public replications are the reason it stays low on the list. The shape is Larry Williams: today's target is the open plus a coefficient times the previous day's high-low range; buy if price trades through the target during the day; sell at the next day's open. On Upbit that open is 09:00 Korea time, which is 00:00 UTC. Common filters are an open above a 5-day average (the WikiDocs book), price above a 15-day average (a widely copied Upbit bot), a coefficient set to the 20-day average noise ratio, and a moving-average score used as a size. The engine cannot express an intraday stop at `open + k × range`, and it cannot see that range from close-only SMA, EMA, RSI, Bollinger, or stochastic. On hourly bars the same rule would also need the session's open and the previous day's range as features.

Author's claims, none of them reproduced here:

| Replication | Sample and cost, as stated | What the author printed |
|-------------|----------------------------|-------------------------|
| [wellsw](https://wellsw.tistory.com/132), best coefficient per coin on Upbit | About the last 200 days into December 2021. Fees plus slippage 0.3%. | KRW-BTC at k = 0.30: period return 1.30×, maximum drawdown 14.06%, buy-and-hold 1.31×. ETH: period return 1.26× against 1.51× for holding. No better than holding BTC, and worse than holding ETH. |
| [TenMillionQuant](https://tenmillionquant.tistory.com/41), the book's uptrend-plus-breakout-plus-vol-sizing recipe | BTC, LTC, ETC, and XRP on Bithumb, June 2017 to March 2022, cost 0.2%. | Return −79.82112310880937, maximum drawdown −79.90856361952895. |
| mintchoco-jelly, Upbit BTC, K = 0.5 | 1,000 days. **No fees.** | Cumulative return 5.767873637615697, maximum drawdown 26.98. |

Two independent replications show either no edge or a large loss. The no-fee result does not survive a strategy that can trade every day: two sides at this platform's 10 bps is 20 bps on a trade day, and many of the published tests ignore that. Coefficients are also chosen per coin, on the same sample that is reported. The rule is tied to the 09:00 Korea open and to Upbit's retail flow, which is not Bybit's daily close. Low priority even after an intraday stop exists.

The noise-scaled variant of the same breakout is the contradictory pair in rank 6: one replication lost about half the capital, and another Excel sheet printed a five-digit percentage. That disagreement is another reason not to promote the family on a headline.

## Paid communities

Of the paid Japanese and Korean products surveyed for this note, only Kang Hwan-guk's books are worth considering. The useful pair is *Bitcoin: Ride the Explosive Rise* (2024) and *The Magic Formula for Cryptocurrency Investment* (2018). They are where the 120-day gate, the volatility-breakout variants, the seasonality chapter, and the volatility sizing are written out with the author's own backtests. A Kyobo listing for the 2024 book was ₩25,200 in print and ₩20,160 for the ebook, about US$15. Buy the ebook if the gated tables are the point. The independent breakout replications above failed, and the published results are in sample, so the purchase is for the rules, not for a track record.

The rest of the list is not worth paying for. Quantus is another backtester. Paid notes derived from richmanbtc, and paid Donchian bot code, are intraday or old trend code outside this use case. A pump-alert Discord, generic mentoring courses, and a volatility-breakout program sold off anchor-optimised claims are a reject. bitbank's botter Discord is free, and it is a place to hear what is working, not a product to buy.
