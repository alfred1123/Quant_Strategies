# Catching crypto trends (Donchian ensemble)

**Doc type:** strategy research  
**Status:** hypothesis — not backtested here. The figures below are the authors' or, where marked, a separate calculation. Nothing here is scheduled for live.

This is the closest published daily, long-only trend rule to the coins and the fee the AlgoDaemon bot actually uses. It is a Donchian breakout with a ratcheting mid-line stop and a volatility target, averaged across nine lookbacks. It is not expressible with the indicators in this repository today. It is the first row of the [AlgoDaemon hand-off](sharpe-ideas-index.md#algodaemon-hand-off).

## Sources

| Item | Link |
|------|------|
| Paper | Carlo Zarattini, Alberto Pagani, and Andrea Barbon, *Catching Crypto Trends: A Tactical Approach for Bitcoin and Altcoins*, Swiss Finance Institute Research Paper. First version 4 April 2025. The PDF used for this note says "This Version: April 9, 2025". |
| SSRN | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907> |
| Public PDF | <https://concretumgroup.com/wp-content/uploads/2026/02/Catching-Crypto-Trends.pdf> (38 pages). The tables and the gaps below are from a review of that PDF. |
| Author summary | <https://concretumgroup.substack.com/p/catching-crypto-trends> (6 May 2025). It restates the Bitcoin net figures: CAGR 30%, Sharpe 1.56, max drawdown 19%. |

Labels used below: **[PAPER]** is in the PDF. **[UNSTATED]** is not. **[SUGGESTION]** is the reviewer's choice, not the authors'. **[MY CALC]** is a separate calculation on Binance data, not a result from the paper.

## Mechanism

A close that prints a new *n*-day closing high goes long that lookback. A close at or below a mid-channel stop that only ratchets up goes flat. Each lookback is then scaled to a 25% annualized volatility target, capped, and the nine weights are averaged. The bet is the usual trend bet: cut the long bear, keep the upside, and stop the position's volatility from dominating the Sharpe denominator. Because the target is 25% and these coins are usually much more volatile than that, the paper's book is often only partly invested. That is a feature of the sizing, not of the breakout.

## Data

**[PAPER]** §3 and §4.1. CoinMarketCap daily OHLCV, aggregated across exchanges, January 2010–March 2025, described as a survivorship-bias-free panel. Signals use the **close**, not the high or the low. Bitcoin results run from 1 January 2015 to 19 March 2025. Other coins start at January 2015 or the listing date, whichever is later.

**[UNSTATED]** The UTC cut-off of the daily close. Bybit spot closes will not match a CoinMarketCap aggregate. Warm-up for the 360-day channel is not discussed; the panel starts in 2010, so pre-2015 history was presumably available for Bitcoin.

## Rules

**[PAPER]** §4.1–§4.3. For each lookback *n* in {5, 10, 20, 30, 60, 90, 150, 250, 360}, equal-weighted (*N* = 9):

```text
DonchianUp_n(t)   = max(Close[t], Close[t-1], ..., Close[t-n+1])   # includes today's close
DonchianDown_n(t) = min(Close[t], Close[t-1], ..., Close[t-n+1])
DonchianMid_n(t)  = 0.5 * (DonchianUp_n(t) + DonchianDown_n(t))

Pos_n(t) = 1           if Close[t] == DonchianUp_n(t)     # new n-day closing high
         = 0           if Close[t] <= TrailingStop_n(t)   # at or below the stop
         = Pos_n(t-1)  otherwise

TrailingStop_n(t+1) = max(TrailingStop_n(t), DonchianMid_n(t))   # never moves down
```

The stop used on day *t*+1 is the higher of day *t*'s stop and the mid-line at the end of day *t*. Footnote 3 sets the initial stop, on a new entry, to the mid-line at entry. The stop only exists while the lookback is long. Resetting it on the next entry follows from that footnote; treating it as irrelevant while flat is **[SUGGESTION]**.

Volatility σ_t is "the 90-day annualized volatility of the returns of the underlying asset computed on day *t*" (§4.2). §4.3 calls the same object "3-month annualized volatility". It is the asset's volatility, shared by every lookback, not the strategy's volatility.

```text
w_n(t)     = min(0.25 / σ_t, 2.00) × Pos_n(t)    # 25% vol target, 200% cap
w_Combo(t) = (1/9) × Σ w_n(t)
ret_Combo(t) = w_Combo(t-1) × ret_asset(t)       # weight at t earns the next day's return
```

The paper does not allow the allocation to exceed 200%. Weights are averaged, not voted. The weight is known at the end of day *t* and earns day *t*+1, which is execution at the signal close.

**[PAPER]** §5.1. Rebalance only when the gap between current and target allocation is more than 20%, and that threshold applies **only** to volatility-driven changes. A new breakout or a trailing-stop exit is traded immediately. After §5.1, reported results are net of 10 bps plus that threshold. The authors say Bitcoin exchange costs are "generally below 5 bps". At 50 bps the threshold recovers about 100 bps/year of CAGR (Fig. 3). Sensitivity is shown at 0, 10, 25, and 50 bps.

**[PAPER]** Table 2, gross, Bitcoin trade counts from 2015 to March 2025, as a check that a short lookback really does trade: 5d 292, 10d 156, 20d 78, 30d 49, 60d 28, 90d 20, 150d 15, 250d 9, 360d 5.

## What the paper does not state

Do not fill these in and then call the result a reproduction.

| Gap | Note |
|-----|------|
| Return type, std, and annualization of σ | Simple or log returns, sample or population standard deviation, and √365 or √252 are all **[UNSTATED]**. **[SUGGESTION]** Simple close-to-close returns, sample std of the last 90 daily returns, √365. |
| Same-bar entry and exit | If the close is both a new high and at or below the stop, precedence is **[UNSTATED]**. The paper lists entry first. **[SUGGESTION]** Exit an existing position first. If that leaves the lookback flat, allow a new entry on the same bar only when `Close == Up_n` and `Close > Mid_n`. Test the other order. |
| The 20% band | Absolute percentage points of NAV, or relative to the target weight? Per lookback, or on the combo? Is "current" the weight after price drift? All **[UNSTATED]**. **[SUGGESTION]** On the combo, relative gap `|w_current − w_target| / w_target > 0.20`, with `w_current` drifted. Also test an absolute 0.20 gap. |
| What 10 bps multiplies | Per side on traded notional, per round trip, or on `|Δw|` is **[UNSTATED]**. **[SUGGESTION]** Charge 10 bps × `|Δw|` × NAV, which is the natural reading of a 10 bp cost on a sized book. |
| Signal day vs vol drift | On a breakout or stop, it is **[UNSTATED]** whether the trade goes to the full new combo target (absorbing any vol drift) or only the lookback's own change. **[SUGGESTION]** Test both. The hand-off recipe trades to the full target. |
| Slippage, risk-free rate, close time | Slippage is not mentioned. The risk-free rate inside Sharpe and Sortino is **[UNSTATED]**. So is the daily close time. |

## Reported performance

Buy-and-hold Bitcoin drawdown is described as ">80%" (**[PAPER]** §5). No figure below has been rerun here.

### Bitcoin, gross, no costs and no threshold

**[PAPER]** Table 1. January 2015–March 2025.

| Model | CAGR | Vol | Sharpe | Sortino | MDD | MAR | Alpha | Beta |
|-------|------|-----|--------|---------|-----|-----|-------|------|
| 5d | 36% | 19% | 1.66 | 1.87 | 25% | 1.41 | 19% | 0.16 |
| 10d | 32% | 18% | 1.55 | 1.64 | 27% | 1.19 | 18% | 0.15 |
| 20d | 34% | 18% | 1.60 | 1.60 | 26% | 1.32 | 19% | 0.16 |
| 30d | 34% | 19% | 1.61 | 1.61 | 24% | 1.41 | 19% | 0.16 |
| 60d | 28% | 19% | 1.30 | 1.25 | 19% | 1.46 | 13% | 0.17 |
| 90d | 27% | 20% | 1.20 | 1.15 | 24% | 1.12 | 11% | 0.18 |
| 150d | 21% | 20% | 0.99 | 0.97 | 29% | 0.74 | 7% | 0.19 |
| 250d | 25% | 20% | 1.13 | 1.15 | 33% | 0.76 | 9% | 0.20 |
| 360d | 29% | 20% | 1.28 | 1.27 | 34% | 0.83 | 12% | 0.18 |
| Combo | 30% | 17% | 1.58 | 2.03 | 19% | 0.88 | 14% | 0.17 |

### Net of 10 bps and the 20% threshold

**[PAPER]** Table 3. These three rows are the ones that match the bot's universe. The same table also reports, for coins the bot cannot trade, SOL 27% CAGR / Sharpe 1.68 / max drawdown 12%, XRP 18% / 1.00 / 14%, and DOGE 24% / 1.20 / 15%. The full table has 40 coins.

| Coin | From | CAGR | Vol | Sharpe | Sortino | MDD | MAR |
|------|------|------|-----|--------|---------|-----|-----|
| BTC | Jan-2015 | 30% | 17% | 1.56 | 1.23 | 19% | 1.15 |
| ETH | Aug-2015 | 27% | 16% | 1.51 | 1.22 | 15% | 0.96 |
| BNB | Jul-2017 | 17% | 15% | 1.06 | 0.99 | 17% | 0.77 |

**[PAPER]** §7, Table 4, not a single-coin test and not in the hand-off: a top-20 book by 30-day median volume, equal capital, reconstituted monthly, net of 10 bps, reports CAGR 18%, vol 9%, Sharpe 1.57, Sortino 1.97, max drawdown 11%, alpha 10.8%, beta 0.08. Eligibility is at least 365 days listed and 30-day median daily volume at least $2M. Removal is 30-day median volume below $1M, or 30-day median absolute daily price change below 0.5%.

## Internal inconsistencies

Flagged and left as printed. Do not "correct" a table to match CAGR/MDD.

- **MAR.** Table 1 gives the combo MAR as 0.88. Table 3 gives Bitcoin MAR as 1.15. CAGR/MDD = 30/19 ≈ 1.58 in both. Single-lookback rows are roughly consistent (the 5-day row is 36/25 = 1.44 against a printed MAR of 1.41), so the combo MAR cells look wrong or use another definition.
- **Sortino.** Bitcoin combo Sortino falls from 2.03 gross to 1.23 net, while Sharpe barely moves (1.58 to 1.56). The paper does not explain that.
- **5-day CAGR.** §5.1 says the 5-day model's CAGR falls "from 34% to 18%" at 50 bps. Table 1 lists the 5-day gross CAGR as 36%.

## A 1× cap (our calculation, not the paper's)

**[PAPER]** The only cap in the paper is 200%. A 1× cap is not tested and not discussed.

**[MY CALC]** On Binance spot daily closes (BTC and ETH from 2017-08-17, BNB from 2017-11-06, all through 2026-09-26), `0.25 / σ_90` was computed from simple returns and a sample standard deviation. Binance's public API was used because a Bybit fetch returned 403. This is not the authors' sample and not a reproduction of their backtest.

| Coin | Annualization | Days with raw weight > 1 | Median raw weight | Max raw weight |
|------|----------------|---------------------------|-------------------|----------------|
| BTC | √365 | 0.0% | 0.43 | 0.90 |
| BTC | √252 | 1.3% | 0.52 | 1.09 |
| ETH | √365 | 0.0% | 0.32 | 0.82 |
| ETH | √252 | 0.0% | 0.38 | 0.99 |
| BNB | √365 | 0.0% | 0.35 | 0.96 |
| BNB | √252 | 0.9% | 0.42 | 1.15 |

On that window, a 1× cap barely binds for these three coins at a 25% target and √365. A spot book capped at 1× should be close to the paper's sized book **on these coins and this later sample**. The 200% cap could still have mattered in quieter years the calculation does not cover (Bitcoin 2015–2016 was not in the file). The median raw weights sit near 0.3–0.5, so at a 25% target the strategy is usually under-invested. Raising the target is what makes the 1× cap bind. That last sentence is **[SUGGESTION]**, not a paper result.

## Xueqiu: daily Turtle holds up, faster bars do not

A later manual browser pass could read public [Xueqiu (雪球)](https://xueqiu.com/8237101817/408838461) posts. This one is supporting evidence for **daily** breakout trend, not a second specification to sweep.

| | |
|--|--|
| Title | 「同一套策略，换个周期就失灵？我用9年BTC数据把这事跑明白了」 (*The same strategy, dead on a different bar size? Nine years of Bitcoin data.*) |
| Author | Not exposed in the readable header |
| Date | Modified 2026-09-10 21:56 |
| Rules | Classic Turtle, long-only, no parameter optimization: 20-period breakout entry, 55-period breakout add-on, 10-period and 20-period reverse-breakout exits, stop at 2×N. The post distinguishes close-confirmation from intrabar touch. |
| Sample | Bitcoin public OHLCV, 2017-08 through 2026-09. Fee 0.1% one way (10 bps). No leverage. A daily run is also shown at 0.02%. No Sharpe. Venue not stated. |

Author-reported figures, as printed:

| Variant | Result |
|---------|--------|
| Daily, close-confirmation | Annualized +33.5%, max drawdown −47.2%, 112 trades, win rate 42% |
| Daily, intrabar touch | Annualized +24.8%, max drawdown −52.8%, 180 trades, win rate 25% |
| 4-hour, intrabar touch | Annualized −25.3%, max drawdown −95.8%, 832 trades |
| 1-hour, intrabar touch | Principal 「几乎归零」 (*almost back to zero*), 3,169 trades, win rate 13% |

The post's summary is that the same rules run from about 33% annualized down to near zero as the bar shrinks. Cutting the daily fee from 0.1% to 0.02% moves the intrabar-touch daily result only from 24.8% to 26.7% annualized, and the drawdown barely changes. That is the author's sample, not an independent rerun, and it is a different rule from Donchian-on-closes (it pyramids, and N is the Turtle volatility unit, which this post does not redefine). The part that transfers is the frequency result: a daily breakout still has a positive author-reported CAGR after a 10 bp one-way fee, and the 4-hour and 1-hour versions do not. AlgoDaemon should not promote this rule onto hourly bars to "get more trades." The 55-period add-on can push gross exposure above 1× if the first unit was already the whole account; the bot's spot cap does not allow that, so the add-on is not in the hand-off.

### Rejected on the same pass

- [BlockBeats, 10 April 2020](https://xueqiu.com/1913130572/146524359), 「你相信，即使你不会编程，也可以做量化策略吗？」: an FTX spot-versus-perp basis example (`BTC-PERP` above 9000 and premium above 1). No performance figures. Rejected: it needs a short perpetual, and the venue is gone.
- [老湾python量化交易, modified 19 July 2025](https://xueqiu.com/4727061301/343192402), 「爆仓出局？你是不是误解马丁策略？」: double the stake after each liquidation, with a 5× example. No backtest, no Sharpe. Rejected: leveraged martingale, not a spot long/flat test.

## Fit here

Not expressible. There is no Donchian, no stop that ratchets, and no weight in `(0, 1]`. A 200-day Bollinger gate is a coarser trend filter and remains the thing this codebase can run without new indicators. Adding Donchian, a trailing stop, and a size multiplier would be platform design, not a parameter change.

**AlgoDaemon testability:** As-is as a **long/flat daily** book on Bybit spot BTC, ETH, and BNB, with the paper's 200% cap replaced by **1×**. This is not a rerun of the 200-day Bollinger FILTER already tried on the stored BTC book in this repository, which lowered hold-out Sharpe from 1.185 to 0.964 ([try-these-first](sharpe-ideas-index.md#try-these-first)). That gate is a z-score sign, not this ensemble. That needs three things the binary z-score signal does not have: a Donchian channel on closes, a trailing stop, and a volatility weight. If the bot can only hold 0 or 1, run that binary Donchian (no 0.25/σ scaling) as a fallback and do not compare its Sharpe to Table 3, which is the sized combo. Hourly is an out-of-sample stress test only; the paper is daily, and the Xueqiu Turtle above loses money at 4-hour and 1-hour after fees. The hand-off row states the sweeps, including which of them are **[SUGGESTION]** rather than the paper's grid.
