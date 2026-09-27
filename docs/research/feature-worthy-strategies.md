# Strategies worth new platform features

**Doc type:** strategy research  
**Status:** hypothesis — offline approximations only, not platform results. Nothing on this page has been run on AlgoDaemon.

The three finalists are really one strategy: a BTC Bollinger-band trend regime traded on three coins (ETH A2, BNB, and BTC; see [merge vs distinct](merge-vs-distinct-candidates.md)). The overfitting check in the [Chin Shum review](chinshum-review.md#overfitting-check-on-the-three-finalist-families) put the probability of backtest overfitting at 0.4–0.8, and ETH A2 lost money out of sample over the last year. Another variant of the same BTC trend adds little. What the book is missing is a return stream that does **not** move with the BTC trend.

This page ranks the **new backend features** that would unlock such streams, and gives the evidence for each strategy behind them. It does not repeat proposals that already exist. Those are linked instead:

- Fractional weights, an averaging combiner, hysteresis with a ratcheting stop, and a close-only Donchian: the [fractional sizing and stateful exits proposal](../design/2026-09-26-fractional-sizing-stateful-exits.md) (PR #63).
- ETF NAV premium, ETF flows, treasury-company holdings, a funding-rate crowding veto, on-chain TVL, and stablecoin supply: the [external-data specs](chinshum-review.md#external-data-specs-for-a-backend-proposal) E1–E6.
- Funding z-score filters and perp-spot convergence: [Funding, basis, and carry](funding-basis-carry.md).
- Vol targeting and cross-sectional factors: [Volatility and the cross-section](volatility-and-cross-section.md).
- Kimchi premium, weekday seasonality, and Korean breakout rules: [Japanese and Korean sources](japanese-korean-sources.md).

!!! warning "Two kinds of numbers on this page"
    **Author-reported** figures are quoted from the named source, with that source's sample and cost assumption. We have not reproduced them.

    **Offline approximation** figures come from a short Python check run for this page. It uses Binance public data as a stand-in for Bybit, daily UTC closes, 10 bp per side per leg, and a **next-day fill**: the position decided at close *t* is filled at close *t+1*. That is one bar slower than the platform's [same-close fill](../design/2026-09-27-bug-verification-round3-4.md#4-a-signal-is-filled-on-the-same-close). Train is up to 2023-12-31 and test is 2024-01-01 to 2026-08-31. Sharpe uses √365. **These are not platform results.** Each is labelled "offline approximation" where it appears.

---

## Summary

- **The only low-correlation stream with real size is carry.** Holding spot against a short perpetual earned about 7–8% a year on BTC and ETH notional from mid-2021 to August 2026, with a daily correlation to the finalist blend of about 0.0–0.1 (offline approximation). Carry has compressed, though: BTC funding summed to 1.7% over January–August 2026. BNB funding was negative in four of the last five years, so carry does not work on BNB.
- **"Carry when the trend is flat" is the most useful combination we found.** It puts idle trend capital into the carry trade and raised the BTC sleeve's test Sharpe from 1.29 to 1.53 and ETH A2's from 1.68 to 1.88 (offline approximation, next-day fill, parameters not re-fitted). This needs a perpetual leg with a funding cashflow. The engine has neither today.
- **A generic derived or external series column comes second.** One feature lets a rule read a ratio, a spread, or a premium. That covers the Coinbase premium, spot-perp basis, ETH/BTC, and the kimchi premium, and it is also the base E1–E6 need. The Coinbase premium was the most promising gate we tested, but its evidence is mixed.
- **Most "alternative" signals failed at 10 bp or out of sample.** That includes the 21:00–23:00 UTC hour, weekday effects, daily taker-flow imbalance, the ETH/BTC ratio (trend or mean reversion), DVOL gates, and MVRV. Their features rank low.
- **Nothing new is worth a backtest on AlgoDaemon today.** The one idea the engine can express, a one-day capitulation bounce, was flat to negative offline. The details are under [Testable on AlgoDaemon today](#testable-on-algodaemon-today).

## Ranked features

"Diversification value" is our estimate of how much the unlocked strategy would add to the BTC-trend book, based on the offline correlation and the strength of the evidence. "Effort" is S, M, or L for the backend alone.

| Rank | Feature | Strategies it unlocks | Diversification value | Data cost and availability | Effort | Priority |
|---|---|---|---|---|---|---|
| 1 | **F1. Perpetual leg with funding cashflow** (a two-leg delta-neutral position: long spot plus short perp, marked with funding income and both legs' fees) | [S1 carry sleeve](#s1-spot-perp-carry-and-carry-when-the-trend-is-flat), carry-when-flat inside each trend sleeve; later the He et al. convergence trade in [funding-basis-carry](funding-basis-carry.md#3-random-maturity-arbitrage-around-the-no-arbitrage-bound) | **High.** Correlation to the blend was about 0.0–0.1 offline. Returns are small now (about 2–3% a year in 2026). | Free: Bybit and Binance publish funding history and perp klines. | L | **P1** |
| 2 | **F2. Derived and external daily series** (a column that is an expression of two loaded series, such as a ratio, a difference, or a spread, plus a loader for an outside daily close such as Coinbase BTC-USD) | [S3 Coinbase premium](#s3-coinbase-premium-gate), [S2 basis as a regime signal](#s2-basis-and-funding-level-as-a-regime-signal), [S6 ETH/BTC ratio](#s6-ethbtc-and-bnbbtc-ratio-trades); also the kimchi premium and E1 | **Medium.** The Coinbase premium gate correlated about 0.4 with the blend offline. | Free: Coinbase Exchange public candles, perp klines. Kimchi needs Upbit plus FX. | M | **P1** |
| 3 | **F3. Hold-for-N-bars exit** (after an entry event, stay long for N bars regardless of the signal; this extends the state in [Proposal C](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-c-hysteresis-and-a-stop-that-remembers)) | [S7 capitulation reversal](#s7-capitulation-volume-reversal-with-a-time-stop), [S8 OI-flush rebound](#s8-open-interest-flush-and-leverage-events), and event studies generally | **Medium in correlation, low in evidence.** Offline correlation was about 0.0–0.2, but there are only 7–10 events per coin in the test window. | None (uses existing data) | S (once Proposal C exists) | **P2** |
| 4 | **F4. Extra kline fields and scale-free volume indicators** (taker-buy volume, quote volume, and trade count as data columns, plus ratio or share indicators; this is part of [B26](../design/2026-09-27-bug-verification-round3-4.md#7-b26-volume-limited-to-a-raw-input-column)) | [S4 taker-flow imbalance](#s4-taker-flow-imbalance-on-daily-bars), the volume leg of S7 | **Low.** Offline flow mostly restated price; correlation was about 0.3–0.5. | Binance klines carry taker-buy volume. Bybit's kline endpoint returns only volume and turnover, so Bybit would need aggregation from its public trade archive. | M | **P3** |
| 5 | **F5. Implied-vol series (Deribit DVOL) and vol-target sizing** (sizing needs [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights)) | [S5 DVOL sizing and VRP gates](#s5-implied-volatility-dvol-sizing-and-vrp-gates) | **Low as a signal.** It is a risk tool: it cut the train-period drawdown offline but did not raise Sharpe. | Free: Deribit public API, BTC and ETH from March 2021. There is no BNB DVOL. | S (data) plus Proposal A | **P3** |
| 6 | **F6. Open-interest series in coin units** | [S8](#s8-open-interest-flush-and-leverage-events) | **Low.** Published evidence is null to weak. | Free on Bybit and Binance. Neither the history depth nor the Bybit endpoint was checked from here. | M | P4 |
| 7 | **F7. Calendar and time-of-day factor** (hour, weekday, month-turn) | [S9 seasonality](#s9-time-of-day-and-weekday-seasonality) | **None at 10 bp.** The 21:00–23:00 UTC hour was deeply negative after fees offline. | None | S | P4: build only if fees fall below about 4 bp |
| 8 | **F8. Spread or long-short position across two coins** | S6 as a market-neutral ratio trade | **Low.** Offline the ratio trades earned close to nothing in the test window. | Free (cross pairs ETHBTC and BNBBTC exist on Binance) | L | P5 |

Not ranked: HMM regime switching, a portfolio drawdown brake, and short options. See [Considered and not ranked](#considered-and-not-ranked).

---

## How the offline check was set up

- **Data.** Binance public data dumps: spot daily klines for BTCUSDT, ETHUSDT, BNBUSDT, ETHBTC, and BNBBTC; hourly BTCUSDT; USDⓈ-M perpetual daily klines and funding history for the three coins. Also the Deribit DVOL index (BTC), Coinbase Exchange daily candles (BTC-USD and USDT-USD), and Coin Metrics community MVRV. Data ends 2026-08-31. The Bybit and Binance REST APIs were geo-blocked from our network, so Binance's archive stands in for Bybit.
- **Engine.** Daily P&L = held position × close-to-close return − |change in position| × 10 bp, with the next-day fill described above. Carry P&L = spot return − perp return + funding settled that UTC day, with 10 bp on each leg on entry and exit.
- **Finalist replica.** The same engine gives the three finalist rules (BTC z60 > 2.25; ETH A2 = BTC z65 > 2.25 and ETH z100 > −1.0; BNB = BTC z100 > 0.5) and an equal-weight blend. Test Sharpe was 1.29 for BTC, 1.68 for ETH A2, 1.24 for BNB, and 1.85 for the blend. Over the last 12 months (2025-09-01 to 2026-08-31) it was 0.27, 0.20, 0.75, and 0.66. These parameters were chosen on data that includes the test window, so the test figures are **not** out of sample and overstate the edge. Use them only as the baseline for correlation and for "adds to the sleeve" comparisons. Our last-12-month ETH A2 figure (+0.20) differs from the platform's −0.16 because the venue, the window, and the fill all differ.
- **Correlations** are daily, against that blend, over the full sample and over the test window.

---

## S1. Spot-perp carry, and carry when the trend is flat

**Rule in plain words.** Buy one unit of spot and sell one unit of the perpetual. The position has almost no price exposure, and it collects funding while funding is positive. Two versions:

1. **Carry sleeve.** Hold the pair all the time, or only while trailing funding is above a threshold.
2. **Carry when flat.** Inside each trend sleeve, put the capital into the pair whenever the trend rule is flat. Unwind both legs on the day the trend turns long.

**Parameters.** Funding gate: trailing 7-day funding, annualized, above 0%, 5%, or 10%. Coins: BTC and ETH only (see below).

**Sources.**

- Schmeling, Schrimpf, and Todorov, *Crypto Carry*, [BIS Working Paper 1087](https://www.bis.org/publ/work1087.htm) (English; later in *Management Science*). Abstract and summary only; the PDF did not load from our network.
- CoinDesk, [3 August 2026](https://www.coindesk.com/markets/2026/08/03/the-bitcoin-futures-yield-collapse-once-over-20-now-less-than-treasury-notes), citing Glassnode (English).
- takurot, [Qiita, 29 July 2026](https://qiita.com/takurot/items/1e1b64e702ac07704228), a NautilusTrader test of funding-rate arbitrage (Japanese).
- FMZ, [资金费率策略近况和推荐操作](https://www.fmz.com/digest-topic/8469) ("Where funding-rate strategies stand", December 2021) and [币本位做空资费套利策略的量化实现](https://www.fmz.com/digest-topic/10578) ("A coin-margined short-perp funding strategy", January 2025) (Chinese).

**Author-reported evidence.**

- Schmeling et al.: carry averaged more than 10% a year and at times reached 40–60%. They tie it to trend-chasing small investors and to limits on arbitrage capital. High carry precedes crashes. The launch of spot ETFs lowered carry by several percentage points. (Sample and costs as in the paper; we read only the abstract.)
- CoinDesk / Glassnode: the 3-month BTC basis was about 3% a year against about 3.8% on the 2-year US Treasury, and had stayed below Treasuries for 157 days since February 2026. The only earlier stretch like it, August 2022 to January 2023, ended at the cycle low.
- takurot (Japanese): over 66 days (May–July 2026) average funding was about 3.1% annualized, and all 32 parameter sets lost money at a 0.02% maker fee. His break-even was average funding above about 7.5% annualized. His best setting entered above 10%, held at least 168 hours, and exited below 0%. This is a short in-sample test.
- FMZ (Chinese, paraphrased): in the 2021 bull market the site's public funding strategy briefly ran above 100% annualized. By December 2021 entry premiums had fallen from about 0.5% to about 0.1%, fees and slippage were eating frequent trades, and the long-hold yield had become "very low". The 2025 post shows cumulative BTC coin-margined funding of about 50% over five years (2020 to early 2025), and notes that BNB's cumulative funding was negative.

**Offline approximation** (BTC, per unit of spot notional, next-day fill, 10 bp per leg):

| Version | Train Sharpe | Train CAGR | Test Sharpe | Test CAGR | Last 12m CAGR | Max DD, train / test | Corr. to blend, full / test |
|---|---|---|---|---|---|---|---|
| BTC, carry always on | 8.9* | 15.9% | 11.9* | 7.3% | 3.4% | −2.3% / −0.4% | 0.10 / 0.02 |
| BTC, carry while 7-day funding > 5% a year | 5.5* | 10.9% | 2.3* | 2.5% | — | −4.8% / −3.2% | 0.10 / 0.02 |
| ETH, carry always on† | 7.0* | 7.0% | 11.3* | 7.4% | 2.4% | −1.8% / −0.6% | — |
| BNB, carry always on† | −4.7 | −8.9% | −1.1 | −1.5% | 1.9% | −21.4% / −5.9% | — |

\* These Sharpe ratios are an artefact of daily marking. The pair's daily P&L had an annualized volatility of only 1.4%, and its worst day was −107 bp. The ratios ignore intraday basis moves, margin calls, exchange risk, and the extra capital the short perp needs. Read the CAGR, not the Sharpe.  
† The ETH and BNB rows start on 2021-07-01. The BTC rows start with the first perp data in September 2019, so their train window includes the 2020–2021 high-funding years. From 2021-07-01, BTC always-on earned 7.9% a year in train.

Funding summed by calendar year (offline, Binance): BTC 17.2% (2020), 30.6%, 4.2%, 7.9%, 12.0%, 5.1%, and 1.7% for January–August 2026. ETH 27.5%, 37.5%, 0.8%, 8.3%, 13.0%, 4.9%, and 1.0%. BNB 2.3%, 21.7%, −12.6%, −8.3%, −3.3%, −2.1%, and 1.8%.

**Carry when flat** (offline approximation, same capital, 20 bp to unwind both legs when the trend enters):

| Sleeve | Train Sharpe, trend → trend + carry | Test Sharpe | Test CAGR | Last 12m Sharpe |
|---|---|---|---|---|
| BTC (z60 > 2.25) | 1.41 → 1.68 | 1.29 → 1.53 | 18.0% → 22.0% | 0.27 → 0.33 |
| ETH A2 | 1.41 → 1.62 | 1.68 → 1.88 | 34.7% → 39.6% | 0.20 → 0.23 |
| BNB (BTC z100 > 0.5) | 0.96 → 0.69 | 1.24 → 1.11 | 46.9% → 40.1% | 0.75 → 0.70 |

Adding always-on BTC carry as a fourth equal-weight sleeve to the three-sleeve blend moved test Sharpe from 1.85 to 1.98 and test max drawdown from −12.3% to −8.8%, but cut test CAGR from 34.8% to 27.7% (offline approximation). Gating carry on funding above 5% did **worse** than leaving it on: the extra switching costs more than the gate saves.

**Plausibility at 10 bp.** Good for a slow, always-on or when-flat sleeve: a round trip costs 40 bp across two legs, which about two months of 2024-level funding covers. Poor for anything that switches often. At 2026 funding (about 2–3% a year) the edge is thin, and a spot sleeve that sits in cash earns nothing either, so carry when flat is still an improvement.

**Correlation to the BTC-trend sleeves.** About 0.0–0.1 daily. Schmeling et al. warn that carry and crash risk are linked, so the tail correlation may be higher than the daily one.

**New platform capability needed.**

1. A **perpetual instrument** (Bybit USDT perps for BTC and ETH) with daily klines and 8-hour funding history.
2. A **two-leg position**: long spot plus short perp, charged fees on both legs.
3. **Funding as a cashflow** in `performance`'s P&L, credited per settlement.
4. For carry when flat, a way for a sleeve to say "when this rule is flat, hold the carry pair". That is either a mode on the sleeve or a job for the [multi-sleeve combiner](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight).
5. A capital or margin assumption for the short leg, so returns are not quoted per unit of notional only.

None of this exists: [funding-basis-carry §4](funding-basis-carry.md#4-cash-and-carry-as-a-holding-strategy) already records cash-and-carry as not expressible, and no backend proposal covers it.

**AlgoDaemon testability:** Can't be tested. There is no perpetual, no second leg, and no funding cashflow.

---

## S2. Basis and funding level as a regime signal

**Rule in plain words.** Use the size of the basis or funding as information about the spot market, not as a trade in itself. Two directions have been argued:

- **Crowding veto** (already specified as [E4](chinshum-review.md#e4-funding-rate-crowding-veto)): do not open a new long while funding is extremely high.
- **Capitulation or regime floor** (new here): when the annualized basis falls below the risk-free rate for a long stretch, the leveraged longs have left, and that has marked cycle lows (CoinDesk / Glassnode above). K33 found that CME days with rising open interest and a rising basis were followed by a better next day than days with rising open interest and a falling basis.

**Parameters.** Basis measure: perp premium over spot, or the annualized 7-day funding sum. Thresholds: basis minus the 2-year Treasury yield below 0 for at least N days (N = 30, 60, 90). K33's version is the sign of the daily change in CME basis and in open interest.

**Sources.** CoinDesk, [3 August 2026](https://www.coindesk.com/markets/2026/08/03/the-bitcoin-futures-yield-collapse-once-over-20-now-less-than-treasury-notes) (English). K33 Research, [*Paying attention to CME traders can pay off*](https://k33.com/research/articles/paying-attention-to-cme-traders-can-pay-off), September 2023 (English). Schmeling et al. (above) on carry predicting crashes.

**Author-reported evidence.** K33: after a CME day with rising open interest and a rising basis, BTC averaged +0.65% the next day (median +0.39%). After rising open interest with a falling basis, it averaged −0.54% (median −0.31%). Their sample is the CME history to September 2023. There is no cost model, and it is a one-day conditional mean, not a strategy. Glassnode's basis-below-Treasuries observation rests on **two** episodes.

**Offline approximation.** Not tested here. We had no Treasury series loaded, and the two-episode history would not support a backtest. The crowding direction is E4's, and [funding-basis-carry §2](funding-basis-carry.md#2-normalize-the-clock-before-you-rank-funding) already specifies how to normalize the funding clock.

**Plausibility at 10 bp.** As a slow regime gate that trades rarely, yes. As K33's one-day rule, no: 0.65% on the good days minus a 20 bp round trip is thin, and it needs CME data.

**Correlation.** Unknown. A basis floor would likely fire near trend bottoms, when the trend sleeves are flat, which is the useful kind of low correlation.

**New platform capability needed.** F1's perp klines and funding history as a **data column** (without trading the perp), a basis column built with **F2** (perp close over spot close minus one), and an outside daily series for the Treasury yield (for example FRED `DGS2`).

**AlgoDaemon testability:** Can't be tested. There is no perp or funding series and no external data.

---

## S3. Coinbase premium gate

**Rule in plain words.** Be long BTC only when US spot buyers on Coinbase are paying more than offshore USDT buyers, relative to recent history. Otherwise stay flat.

**Parameters.** Premium = Coinbase BTC-USD daily close ÷ Binance (or Bybit) BTCUSDT close − 1. Smooth it with an N-day mean, N in {3, 5, 7, 10, 14, 21}, then take a Z-day z-score, Z in {60, 90, 180}. Go long when the z-score is above 0. Optionally divide by USDT-USD to strip out Tether's own premium.

**Sources.** TradeWize, [*Coinbase Premium: what 9 years of hourly data say it actually measures*](https://tradewize.io/blog/how-to-read-the-coinbase-premium) (English). The premium is also mentioned in passing in the [Japanese and Korean page](japanese-korean-sources.md#ranked-ideas), rank 3, where a Korean note found that premium flips were followed by roughly flat returns.

**Author-reported evidence.** TradeWize: the premium ranged from −37 to +518 bp in 2017 and from −16 to +3 bp in 2026, and it is mostly a Tether-price artefact. Top-decile days follow a month that gained 14.6% and precede +3.8% a month, against +0.3% for the bottom decile. Once Tether is adjusted out, the two deciles are the same. The author reads it as descriptive, not predictive.

**Offline approximation** (BTC, long or flat, next-day fill, 10 bp; the window starts 2021-07-01, so buy and hold is Sharpe 0.42 in train, 0.73 in test, and −0.51 over the last 12 months):

| Variant (18 grid cells each) | Median train Sharpe | Median test Sharpe | Median last-12m Sharpe | Cells beating buy and hold in test | Time in market | Corr. to blend |
|---|---|---|---|---|---|---|
| Raw premium | 0.74 | 0.94 | 0.60 | 14 of 18 | about 48% | 0.31–0.42 |
| USDT-adjusted premium | 0.18 | 1.04 | 0.41 | 15 of 18 | about 47% | 0.35–0.39 |

The 7-day / 90-day raw cell by year (buy and hold in brackets): 2019 0.57 (1.31), 2020 1.19 (2.25), 2021 0.75 (0.98), 2022 −0.36 (−1.29), 2023 2.84 (2.35), 2024 1.65 (1.76), 2025 0.28 (0.05), 2026 January–August 1.24 (−0.12). Most of the gain comes from sitting out bad years, not from beating good ones. The USDT-adjusted version is weaker in the train period, which supports TradeWize's point that much of the raw signal is the price of USDT offshore, not US demand. Mean premium from mid-2021: +0.2 bp raw, +0.4 bp adjusted.

**Plausibility at 10 bp.** Moderate. The rule is in the market about half the time and switches every few days on short smoothing windows. Longer windows (14–21 days) switch less and held up about as well.

**Correlation.** About 0.3–0.4 with the blend. That is lower than another trend variant, but not low.

**New platform capability needed.** **F2**: an outside daily series (Coinbase BTC-USD and, for the adjusted version, USDT-USD, both from free Coinbase Exchange candles) and a **ratio expression** against the traded BTCUSDT close, usable as a factor column. The existing Bollinger z-score then serves as the z-score.

**AlgoDaemon testability:** Can't be tested. There is no external series and no ratio column.

---

## S4. Taker-flow imbalance on daily bars

**Rule in plain words.** Be long when aggressive buyers (the taker-buy share of volume) have been unusually active over the last N days. A variant first strips out the part of the flow explained by same-day returns.

**Parameters.** Taker-buy share = taker-buy base volume ÷ total volume. Smooth over N days (7 or 30), then take a 180-day z-score. Go long when it is above 0.

**Sources.** Anastasopoulos et al., [*Order flow and cryptocurrency returns*](https://www.sciencedirect.com/science/article/pii/S1386418126000029), *Journal of Financial Markets* 2026 (English, abstract and summary). QuantScopeX, [*We tested 3.08 billion BTC order-flow records*](https://www.quantscopex.com/research/strategy/bitcoin-order-flow-statistical-evaluation) (English).

**Author-reported evidence.** The journal paper reports that world order flow has explanatory and predictive power for crypto returns and says the result survives transaction costs. In the version we read, flow predicts daily and weekly returns only after lagged returns are controlled for (t = 2.58), and lagged returns themselves predict with a negative sign (t = −3.25). QuantScopeX finds that most order-flow signals, including cumulative volume delta, explain the present bar and not the next one.

**Offline approximation** (next-day fill, 10 bp):

| Coin, variant | Train Sharpe (2019–2023) | Test Sharpe | Buy-and-hold train / test |
|---|---|---|---|
| BTC, 7-day share | 0.86 | 0.16 | 1.06 / 0.73 |
| BTC, 30-day share | 1.14 | 0.40 | 1.06 / 0.73 |
| BTC, 7-day residual | 0.73 | −0.15 | 1.06 / 0.73 |
| ETH, 30-day share | 0.82 | 0.92 | 1.10 / 0.38 |
| ETH, 7-day residual | 0.87 | 0.27 | 1.10 / 0.38 |
| BNB, 30-day share | 1.22 | 0.29 | 1.29 / 0.83 |

Only ETH on the 30-day share beat buy and hold in the test window. The rest decayed, and correlation to the blend was about 0.3–0.5.

**Plausibility at 10 bp.** Low as a stand-alone rule. The flow restates price, which the trend sleeves already hold.

**Correlation.** About 0.3–0.5.

**New platform capability needed.** **F4**: native taker-buy volume as a data column, plus a share indicator (a column over a column, which is also **F2**). Bybit's kline endpoint does not split taker volume, so the platform would need Binance klines or its own aggregation of Bybit's public trade archive. We did not verify the Bybit archive from our network.

**AlgoDaemon testability:** Can't be tested. Taker-buy volume is not a column (only `Volume` is, per [B26](../design/2026-09-27-bug-verification-round3-4.md#7-b26-volume-limited-to-a-raw-input-column)).

---

## S5. Implied volatility (DVOL): sizing and VRP gates

**Rule in plain words.** Three ways to use Deribit's 30-day implied-vol index:

1. **Size** the position as target ÷ DVOL, capped at 1.
2. **Gate**: stay flat when DVOL is in the top 10–20% of its past year.
3. **Variance risk premium (VRP) gate**: stay long only while DVOL is above trailing realized vol.

**Parameters.** Target vol 40% or 60%. Percentile gate 0.8 or 0.9 over 365 days. VRP = DVOL − 30-day realized vol, used either as sign > 0 or as its 90-day z-score > 0.

**Sources.**

- Penev, TradeWize, [*How to read implied volatility: scoring 5 years of Bitcoin's DVOL*](https://tradewize.io/blog/how-to-read-implied-volatility), September 2026 (English).
- Amberdata, [*Bitcoin options: finding edge in four years of volatility regimes*](https://insights.deribit.com/industry/bitcoin-options-finding-edge-in-four-years-of-volatility-regimes/), on Deribit Insights (English).
- [arXiv:2410.15195](https://arxiv.org/abs/2410.15195), *Risk premia in the Bitcoin market* (English).
- Alexander and Imeraj, [SSRN 3383734](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3383734), a Bitcoin VIX (English).
- Moreira and Muir's vol-managed portfolios are already on [Volatility and the cross-section](volatility-and-cross-section.md#1-volatility-managed-portfolios-the-mechanism).

**Author-reported evidence.**

- TradeWize (2021–2026): DVOL was above the next 30 days' realized vol on 72% of days, by a median 10 points. The premium shrank from 21 points in 2021 to 5 in 2026. Top-decile DVOL said nothing about direction: 49% of subsequent months were up, against 50% for the bottom decile. From the top decile, DVOL fell about 14 points a month, and the biggest misses started from **low** DVOL.
- Amberdata (2019–2022): the options term structure was in contango 77.5% of the time, with a VRP of about +15 points in contango. Systematic short straddles earned well at mark prices. That needs options, which are out of scope here.
- arXiv 2410.15195: the BTC variance risk premium is larger than the S&P 500's and, unlike in equities, is negatively related to BTC returns.

**Offline approximation** (BTC, window from 2021-04-15, next-day fill, 10 bp; buy and hold over this window: train Sharpe 0.07 with max DD −76.6%, test 0.73 with −53.0%):

| Variant | Train Sharpe | Train max DD | Test Sharpe | Test max DD | Corr. to blend |
|---|---|---|---|---|---|
| Size = min(1, 40% ÷ DVOL) | 0.17 | −55.2% | 0.60 | −51.8% | 0.39 / 0.40 |
| Size = min(1, 40% ÷ 30-day realized vol) | 0.17 | −64.7% | 0.70 | −50.9% | 0.41 / 0.42 |
| Size = min(1, 60% ÷ DVOL) | 0.08 | −71.2% | 0.73 | −52.8% | 0.39 / 0.41 |
| BTC trend sleeve × min(1, 60% ÷ DVOL) | 1.41 | −8.7% | 1.28 | −6.3% | 0.59 / 0.62 |
| Flat when DVOL percentile > 0.8 | 0.31 | −75.9% | 0.74 | −50.8% | 0.34 / 0.33 |
| Long when VRP z-score > 0 | −0.03 | −69.2% | 0.69 | −31.0% | 0.31 / 0.33 |

The mean gap between DVOL and the next 30 days' realized vol was 8.7 points, close to TradeWize's median. DVOL sizing cut the train drawdown but did not beat realized-vol sizing and did not improve the trend sleeve (1.29 → 1.28 in test).

**Plausibility at 10 bp.** Fine for sizing, since DVOL moves slowly. There is no directional edge to trade.

**Correlation.** As a sizing layer it inherits the sleeve's correlation. It does not diversify.

**New platform capability needed.** **F5**: the Deribit DVOL daily series (BTC and ETH; no BNB index exists) as an external column. Using it for sizing depends on [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights). A realized-vol version needs only Proposal A and existing prices, which makes DVOL low priority.

**AlgoDaemon testability:** Can't be tested. There is no external series and no fractional weight. A realized-vol gate in binary form is already [hand-off row 5](sharpe-ideas-index.md#algodaemon-hand-off).

---

## S6. ETH/BTC and BNB/BTC ratio trades

**Rule in plain words.** Trade the ratio of two coins instead of either coin in dollars. Either follow its trend (hold ETH while ETH/BTC is above its moving average, otherwise hold BTC or the short side of the ratio), or fade its extremes (mean reversion on a z-score).

**Parameters.** Trend: SMA 20, 50, or 100 on the ratio. Mean reversion: a 30-day z-score at ±1.5 or a 60-day z-score at ±2.0.

**Sources.**

- 百亿财经 (baiyi.com), [如何用 ETH/BTC 比率制定双币轮动交易策略](https://www.baiyi.com/market/6797fb6691994173b82a497662baa9fb.html) ("How to build a two-coin rotation on the ETH/BTC ratio") (Chinese; describes the SMA-50 rotation).
- Validated Strategies, [*Pairs trading ETH/BTC cointegration backtest: why it failed (2018–2026)*](https://validatedstrategies.com/strategy/PAR) (English).
- Fil and Kristoufek, [*Pairs trading in cryptocurrency markets*](https://ieeexplore.ieee.org/document/9200323), *IEEE Access* 2020 (English).

**Author-reported evidence.**

- Validated Strategies: profit factor 0.69, Sharpe 0.10, max drawdown −93%. Sign-flipped placebos beat the real rule 58% of the time. ETH/BTC was cointegrated in only 7.6% of rolling windows, with a spread half-life of about 486 days.
- Fil and Kristoufek (26 Binance coins, January 2018 to September 2019): daily pairs trading mostly failed. Higher frequencies did better but were very sensitive to costs.
- baiyi.com gives the rule without a backtest table that we could verify.

**Offline approximation** (next-day fill, 10 bp per unit via the cross pair; train 2019–2023):

| Rule | ETH/BTC train → test Sharpe | BNB/BTC train → test Sharpe |
|---|---|---|
| Long/short the ratio, SMA 20 | 0.26 → −0.09 | 0.97 → −0.13 |
| Long/short the ratio, SMA 50 | 0.00 → 0.09 | 1.17 → 0.22 |
| Long ratio or flat, SMA 50 | 0.28 → −0.18 | 1.17 → 0.38 |
| Mean reversion, z60 at ±2.0 | −0.74 → 0.13 | −0.91 → 0.17 |

Correlation to the blend was about 0 for ETH/BTC and about 0.1–0.5 for BNB/BTC. Nothing survived into the test window, which agrees with the published failures.

**Plausibility at 10 bp.** Low. The ratios trend for long stretches (BNB/BTC before 2022) and then stop.

**Correlation.** Near zero, the one attractive property.

**New platform capability needed.** **F2** (a ratio column as a signal source), plus **F8** (a spread position: long one coin and short the other, or trading a cross pair such as ETHBTC) to trade the ratio itself. A rotation between ETH and BTC also needs a rule that holds one of two coins, which the one-instrument engine cannot do.

**AlgoDaemon testability:** Can't be tested. There is no ratio column and no second instrument per strategy.

---

## S7. Capitulation-volume reversal with a time stop

**Rule in plain words.** After a day that falls much more than usual on much heavier than usual volume, buy the next close and hold for a fixed number of days, whatever the signal says in between.

**Parameters.** Event: daily return below −2 × its 60-day standard deviation, and quote volume above 2 × its 20-day average. Hold 3 or 7 days.

**Sources.** Gate Research, [*Can deleveraging predict a rebound?*](https://www.gate.com/research/article/gate-research-can-deleveraging-predict-a-rebound-a-time-series-analysis-of-btc-price-oi-funding-and-liquidation-volume), September 2026 (English; the Chinese Gate academy mirror was blocked). MarketTrace, [*What does open interest indicate? We tested 136,000 hours*](https://markettrace.ai/blog/open-interest-analysis), September 2026 (English). Both concern the related OI-flush events in S8. The volume-spike definition is ours.

**Author-reported evidence.** Gate Research (January 2025 to August 2026): deleveraging alone did not predict a rebound. Only events confirmed by a green close had positive forward returns: an OI flush with a green close (13 events) averaged +0.38%, +2.00%, +1.45%, and +2.10% at 1, 3, 7, and 14 days. None survived their multiple-testing correction.

**Offline approximation** (next-day fill, 10 bp):

| Coin | Events, train / test | Hold 3 days, train → test Sharpe | Hold 7 days, train → test Sharpe | Corr. to blend |
|---|---|---|---|---|
| BTC | 12 / 9 | −0.83 → 0.61 | 0.06 → 0.51 | about 0.0 |
| ETH | 17 / 7 | −0.42 → 0.38 | 0.22 → 0.50 | about 0.0 |
| BNB | 15 / 10 | −0.63 → 0.49 | 0.07 → 0.84 | 0.02–0.19 |

The sign flips between train and test on 7–17 events per window. This is noise until more events accumulate.

**Plausibility at 10 bp.** Fine per trade: one round trip per event against multi-percent moves. The problem is sample size.

**Correlation.** About zero, because the rule fires when the trend sleeves are flat.

**New platform capability needed.** **F3** (hold for N bars after an event; the engine's signals are stateless and cannot remember the entry day), plus a return-over-volatility indicator on the price column. The existing Bollinger z-score is close enough. The volume leg works today through `data_column: "Volume"`.

**AlgoDaemon testability:** Needs adapting. Only a one-day version can run today; see [below](#testable-on-algodaemon-today).

---

## S8. Open-interest flush and leverage events

**Rule in plain words.** Buy after a sharp drop in open interest (leverage flushed out), ideally only when the same day closes green. Read open interest in coin units, not dollars.

**Parameters.** 24-hour OI change ≤ −8% (MarketTrace). Price confirmation: a green close (Gate Research). Hold 3–14 days.

**Sources.** MarketTrace, [*What does open interest indicate?*](https://markettrace.ai/blog/open-interest-analysis), 16 September 2026 (English). Gate Research (above).

**Author-reported evidence.** MarketTrace (136,000 hours of Binance BTC, ETH, and SOL): the four OI-and-price quadrants did not predict direction. Continuation ran 43–53%, and the sign flipped from year to year. Rising OI predicted a **wider** next-day range (on BTC, about +16% range per +10 percentage points of OI), not a direction. An OI flush of 8% or more was followed by a higher close 72 hours later 57% of the time (median +0.92%, p = 0.045), which the authors call a lean, not a rule. Dollar OI is mostly price, so they measure OI in coin units. Gate Research's figures are under S7.

**Offline approximation.** Not tested. Binance's API was geo-blocked, and we did not load its archive's OI files.

**Plausibility at 10 bp.** Per-trade costs are fine. The published edge is marginal.

**Correlation.** Probably low, as with S7.

**New platform capability needed.** **F6** (an OI series in coin units per coin) and **F3** (hold for N bars).

**AlgoDaemon testability:** Can't be tested. There is no OI series.

---

## S9. Time-of-day and weekday seasonality

**Rule in plain words.** Hold BTC only during the hours or days that have historically been strongest. Quantpedia's version buys at 21:00 UTC and sells at 23:00 UTC every day.

**Parameters.** Hour window 21:00–23:00 UTC. Weekend-only or single weekdays.

**Sources.**

- Padyšák and Vojtko, Quantpedia, [*Are there seasonal intraday or overnight anomalies in Bitcoin?*](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/) (English).
- Mueller, [*Revisiting seasonality in cryptocurrencies*](https://www.sciencedirect.com/science/article/pii/S1544612324004598), *Finance Research Letters* 2024 (English).
- The [Chin Shum review](chinshum-review.md#overnight-seasonality) already rejected a US-overnight hold offline (out-of-sample Sharpe −0.66 at 10 bp). Weekday and month effects from Money Partners are on the [Japanese and Korean page](japanese-korean-sources.md#ranked-ideas).

**Author-reported evidence.** Quantpedia (Gemini data, October 2015 to February 2022): the 22:00 and 23:00 UTC hours had the most significant returns. The 21:00–23:00 hold earned about 33% a year with 20.9% volatility and a −22.45% max drawdown, and an update to June 2023 gave 40.64% a year with a Calmar of 1.79. Costs are not clearly included. Mueller (500 coins): return seasonality is not robust, the BTC Monday effect did not persist after 2015, and the only stable weekend pattern is lower activity.

**Offline approximation** (Binance BTCUSDT hourly):

| Variant | Train Sharpe | Test Sharpe | Corr. to blend |
|---|---|---|---|
| Hold 21:00–23:00 UTC, 0 bp | 1.76 | 2.13 | 0.06–0.08 |
| Same, 5 bp per side | −0.27 | −0.69 | — |
| Same, 10 bp per side | −2.31 | −3.52 | — |
| Weekend only, 10 bp | −0.04 | −0.25 | 0.15–0.18 |

The two hours average about +3.8 bp each in both train and test, so the effect is real before costs. At 10 bp per side, one round trip a day costs 20 bp against about 7.6 bp of gross edge. Weekday means flipped sign between train and test (Tuesday +8.3 bp → −25.4 bp, for example).

**Plausibility at 10 bp.** None. It would need a maker fee below about 4 bp per side, or a way to hold only on days with a large expected move.

**Correlation.** About 0.1, the lowest of anything here, which is why it keeps coming back.

**New platform capability needed.** **F7** (an hour-of-day or weekday column usable as a gate), on the existing hourly bars.

**AlgoDaemon testability:** Can't be tested. There is no calendar factor, and the fee kills it anyway.

---

## Considered and not ranked

- **MVRV and other on-chain valuation.** Already on [Microstructure, on-chain, and unusual](microstructure-onchain-unusual.md#4-on-chain-value-spent-coins-and-a-price-to-utility-ratio). Offline, "flat when MVRV > 3.0" never triggered in the test window (the peak was 2.78), so it matched buy and hold. At > 2.5 it cut test Sharpe from 0.73 to 0.54. Low value.
- **HMM or machine-learning regime allocation.** Bysik and Ślepaczuk, [arXiv:2606.00060](https://arxiv.org/abs/2606.00060) (English, hourly BTC 2018–2025, walk-forward): naive ML strategies collapsed at 10 bp. A filter that trades only when the forecast beats the cost restored a long-only Sharpe above 1, but bootstrap tests did not show it beating buy and hold. Large build, weak case.
- **Short options and VRP harvesting.** Amberdata's straddle results need an options instrument. Out of scope for a spot platform.
- **Cross-sectional momentum or reversal on a wider universe.** Covered on [Volatility and the cross-section](volatility-and-cross-section.md#2-cross-sectional-size-momentum-volume-volatility). It needs dozens of coins and a long-short basket, which is a bigger change than anything above.
- **Portfolio drawdown brake.** Needs the multi-sleeve combiner first ([Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight)). No outside evidence was found that it adds Sharpe, as opposed to cutting drawdown.

---

## Testable on AlgoDaemon today

None of the new ideas is both expressible and promising. The one that is expressible:

**Capitulation bounce, one-day hold.** On the traded coin, daily bars, `fee_bps` 10, conjunction **FILTER** (two factors only, so [B1](../design/2026-09-27-algodaemon-bug-report.md#b1-two-factor-and-behaves-like-or-for-long-only-factors) does not apply):

- Factor 1: `get_bollinger_band` on `price`, signal `reversion_long`, window 20–60 (step 10), signal 2.0–3.0 (step 0.25). Long when the price z-score is below −signal.
- Factor 2: `get_bollinger_band` on `Volume`, signal `momentum_long`, window 20–30 (step 5), signal 1.5–3.0 (step 0.5). Long when the volume z-score is above +signal.

Because signals are stateless, this holds for one bar only. **Offline approximation:** over a 54-cell grid per coin from 2021-07 to 2026-08, there were about 14 long days in five years. Median full-sample Sharpe was 0.11 (BTC), −0.18 (ETH), and 0.05 (BNB) with same-close fill, and −0.14, −0.11, and −0.26 with next-day fill. Only run it as a negative control, or as a baseline to compare against once F3 lets it hold 3–7 days.

---

## Sources that were blocked or not read

- Zhihu (知乎) answers and columns: HTTP 403.
- ScienceDirect full texts (a CEX/DEX funding-arbitrage paper, the order-flow paper): Cloudflare challenge; abstracts only.
- The Chinese Gate academy (Gate 学院) article on deleveraging: access denied. The English Gate Research version was read.
- The BIS *Crypto Carry* PDF: an HTML challenge instead of the file. The abstract page was read.
- The Binance REST API (HTTP 451) and the Bybit REST API (HTTP 403): geo-blocked from our network. The Binance public data archive, Deribit, Coinbase Exchange, and Coin Metrics community APIs worked.
- JoinQuant (聚宽) and Xueqiu (雪球) were not examined in the time available. Paid communities were not accessed.
