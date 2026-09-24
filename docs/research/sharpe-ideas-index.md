# Sharpe-oriented crypto research — where to start

**Doc type:** strategy research  
**Status:** hypothesis — not backtested here. Nothing on these pages is scheduled for live.

This note ranks outside ideas that might raise the **Sharpe ratio** of a crypto book, and says which of them this platform can express today. The same pages stay broad: a perp arbitrage is still written up. Separately, the [AlgoDaemon hand-off](#algodaemon-hand-off) lists only what a Bybit spot backtest on BTC, ETH, and BNB can run, most promising first. This note sits next to [Crypto spot — baseline improvements](crypto-spot-baseline-improvements.md), which already covers a BTC daily Bollinger momentum long (reported Sharpe about 1.48 in that thread) and three variants of it. These pages do not repeat that recipe. They add cross-sectional evidence, carry and basis, volatility scaling, and a few unusual effects, then map each one onto the current engine.

!!! warning "Figures below are other people's results"
    Every number is quoted from the named source, with the sample and cost assumption that source states. They have not been reproduced in this repository. Do not read them as expected live performance. Measurement rules that already apply here (crypto annualization with √365, the 10 bp default taker haircut, the 60-bar floor) are in [Measurement hygiene](crypto-spot-baseline-improvements.md#4-measurement-hygiene).

## What "fit this repo" means

The engine trades **one product** with a position in {−1, 0, +1}. A second factor can be a gate ([FILTER](../guides/indicators-strategies.md#conjunction-modes-multi-factor)), and that factor may be computed on a **different symbol** than the one being traded ([Factor list](../architecture/api.md#factor-list-single-source-of-truth)). It does not:

- scale size continuously (no volatility-targeting layer; fees are `|Δposition| × fee` on a unit position),
- hold a long-short basket, a spot-versus-perpetual hedge, or a funding cashflow,
- see 4-hour bars (`REFDATA.TM_INTERVAL` is daily and 1-hour), order-book events, or a funding-rate history,
- path-depend (no trailing stop inside the signal).

Indicators today are SMA, EMA, RSI, Bollinger z-score, and stochastic %D (`quant/strategy/indicators.py`). `Ryan/` has no strategy research. There is no `results/` tree of external backtests. On-chain access is the Glassnode client; most useful metrics are deferred on cost grounds in [Alternative data sources](../design/alt-data-sources.md).

`docs/design/multi-strategy-netting.md` is about **netting orders** when several strategies trade the same asset. It is not a cross-sectional portfolio.

## Try these first

Ordered by usefulness **given what we can run**, not by the largest Sharpe printed elsewhere. A market-neutral arbitrage with a reported Sharpe above 10 is real research and a poor first job for a spot, unit-position, daily engine.

| Rank | Idea | Why it is early | Expressible now? |
|------|------|-----------------|------------------|
| 1 | Trend gate on the existing BTC daily Bollinger momentum long | Drops bear-market variance, which is the usual way this baseline's Sharpe moves. Time-series momentum in Bitcoin is documented below. The gate itself is already specified on the [baseline page](crypto-spot-baseline-improvements.md#22-macro-trend-filter-50-200-day-sma). | **Yes.** FILTER: gate = `get_bollinger_band` window 200, threshold 0, `momentum_long`; signal = the baseline recipe. |
| 2 | Cross-product regime gate | Same idea, but the gate is a second large coin (ETH is the obvious first test) rather than a longer window of BTC. Uses the cross-product factor that already exists. | **Yes.** FILTER, gate symbol ≠ traded symbol. Walk-forward it: BTC and ETH are highly correlated, so the gate can be a disguised BTC trend filter. |
| 3 | Realized-volatility gate, before continuous sizing | Volatility timing raises Sharpe when volatility moves more than expected return ([Moreira and Muir](volatility-and-cross-section.md#1-volatility-managed-portfolios-the-mechanism)). A binary "flat when recent vol is high" gate is a much smaller change than resizing the PnL line. | **No.** No indicator returns a volatility. Bandwidth / ATR are the same gap already listed on the baseline page. |
| 4 | Funding-rate crowding as a single-name filter | Extreme positive funding means longs are paying to hold. Refusing those longs can cut left tail without a hedge book. A Chinese practitioner implementation normalizes mixed 1h/4h/8h funding intervals before ranking — that detail is easy to get wrong. | **No**, until a funding series is stored as a factor column. The position algebra does not need to change. |
| 5 | One attention or on-chain series as a gate | A 2018 working paper finds Google-search and Twitter intensity forecast 1–2 week Bitcoin returns. Worth one series, not a data-vendor programme. | **Only if** the series is already affordable and loaded like a price. Glassnode Professional is explicitly deferred. |

Do **not** schedule these as the next backtest, even though the write-ups are more exciting:

- Cross-sectional long-short books (size, momentum, low-volume). The large weekly spreads in [Liu, Tsyvinski, and Wu](volatility-and-cross-section.md#2-cross-sectional-size-momentum-volume-volatility) are zero-investment portfolios across hundreds of coins. This engine holds one name. The same literature says the **liquid** names, which are the ones we trade, behave differently from the small-coin leg.
- Perpetual-versus-spot "random maturity" arbitrage. [He, Manela, Ross, and von Wachter](funding-basis-carry.md#3-random-maturity-arbitrage-around-the-no-arbitrage-bound) report a Bitcoin Sharpe of 3.35 under retail trading costs. The trade is two legs plus a convergence exit. We cannot mark funding or a hedge.
- The 24-hour roll-out scalp. The public replication finds an annualized Sharpe near 2.1 **before costs**, then a **negative** per-trade result at a 10 bp taker round trip — which is this platform's default haircut. See [microstructure](microstructure-onchain-unusual.md#1-the-24-hour-roll-out-effect).

## AlgoDaemon hand-off

These candidates are for a backtesting bot on AlgoDaemon. Limits, as given for that bot:

| Limit | Consequence |
|-------|-------------|
| Bybit **spot** only | Long or flat. No short leg, no perpetual, no basis hedge, no funding payment in the PnL. |
| **BTC, ETH, BNB** only | No other coin, listed or delisted. |
| **10 bps per trade** | Entry and exit each cost 10 bps unless the bot defines "per trade" as a round trip. Prefer rules that do not flip every bar. |
| **Daily** bars, hourly allowed | Daily is the run to trust. Use hourly only as a check, and not for a one-bar scalp. |
| Backtests only | No live orders. |

"As-is" means spot OHLCV of those three coins is enough. "Needs adapting" means the bot still trades that spot book, but some other series is only a signal. Sweep grids below are **proposed for the bot**. They are not optima published by the sources. Fix one coin at a time unless the rule is the three-coin rank. Report Sharpe with √365 and with the 10 bp cost on, not a pre-cost figure.

### 1. Trend-gated Bollinger momentum (as-is)

Best first job: low turnover, daily, one coin, no extra data. Run BTC, then ETH, then BNB.

| | |
|--|--|
| Rules | `z` = Bollinger z-score of close. Signal is long when `z > threshold`, else flat. Gate is on when `close > SMA(gate)`. Position is the signal when the gate is on, else flat. No shorts. |
| Indicators | Bollinger z-score `(close − SMA) / rolling stdev`. SMA on close. |
| Sweep | Signal window 10, 20, 40. Threshold 0.5, 1.0, 1.5, 2.0. Gate window 50, 100, 200. |
| Bars | Daily. |
| Source | Gate: [baseline §2.2](crypto-spot-baseline-improvements.md#22-macro-trend-filter-50-200-day-sma). Why a trend gate can raise Sharpe: [Liu and Tsyvinski, NBER WP 24877](https://www.nber.org/papers/w24877). |

### 2. Time-series momentum, long or flat (as-is)

The same evidence, without a Bollinger threshold. One coin at a time.

| | |
|--|--|
| Rules | `r(N) = close / close[N] − 1`. Long when `r(N) > 0`, else flat. |
| Indicators | N-day simple return. |
| Sweep | N = 7, 14, 21, 28 (the paper's 1- to 4-week horizons, on daily bars). Add 60 and 120 only as a longer check the paper did not run. |
| Bars | Daily. |
| Source | [Liu and Tsyvinski, NBER WP 24877](https://www.nber.org/papers/w24877). Their weekly Sharpe of 0.45 is **not** annualized; do not target it. |

### 3. Cross-asset regime gate (as-is)

Same position rule as candidate 1, with the SMA gate read off a **second** allowed coin. Still one spot position.

| | |
|--|--|
| Rules | Signal from candidate 1 on the traded coin. Gate is on when the other coin's `close > SMA(gate)`. Flat when the gate is off. |
| Indicators | Bollinger z-score on the traded coin. SMA on the gate coin. |
| Sweep | Pairs: trade BTC / gate ETH, trade ETH / gate BTC, trade BNB / gate BTC. Fix signal window 20 and threshold 1.0. Gate window 100 and 200. |
| Bars | Daily. |
| Source | Adaptation of candidate 1 to a second symbol. No published Sharpe for this pair list. Write-up: [cross-product regime gate](momentum-reversal-filters.md#2-cross-product-regime-gate). |

### 4. Realized-volatility flat gate (as-is)

Price-only version of volatility timing. Do not scale size above 1. Continuous sizing is optional and only if the bot already accepts a weight in `(0, 1]`; otherwise use this binary gate.

| | |
|--|--|
| Rules | Fix the inner book at candidate 1 with window 20, threshold 1.0, gate 200. `rv` = standard deviation of daily log returns over L days. Flat when `rv > k × median(rv over the trailing 180 sessions)`. Otherwise take the inner position. |
| Indicators | Trailing standard deviation of log returns. Median of that series. The inner Bollinger z-score and SMA. |
| Sweep | L = 14, 20, 30. k = 1.0, 1.5, 2.0. Keep 180 fixed. |
| Bars | Daily. |
| Source | Mechanism, not a crypto result: [Moreira and Muir, JF 2017](https://doi.org/10.1111/jofi.12513). Mapping: [volatility-managed portfolios](volatility-and-cross-section.md#1-volatility-managed-portfolios-the-mechanism). |

### 5. Three-coin relative momentum, long only (as-is)

Adaptation of cross-sectional momentum to the only universe the bot has. Not the paper's hundred-coin long-short.

| | |
|--|--|
| Rules | Each rebalance, `r_i(N) = close_i / close_i[N] − 1` for BTC, ETH, and BNB. Hold the highest `r` if it is positive, in equal notional, one coin. If the highest `r` is negative, hold cash. No shorts. |
| Indicators | N-day return on each of the three closes. |
| Sweep | N = 7, 14, 28, 60. Rebalance every day, and again every 7 daily bars (the weekly variant is the one that respects 10 bps). |
| Bars | Daily. |
| Source | [Liu, Tsyvinski, and Wu, NBER WP 25882](https://www.nber.org/papers/w25882) for the cross-sectional momentum fact. [Zaremba et al., IRFA 2021](https://doi.org/10.1016/j.irfa.2021.101908) for momentum in liquid names rather than reversal. The three-name long-only rule is ours. |

### 6. Bandwidth-squeeze breakout (as-is)

Only after 1–4. Still daily OHLC. Skip it if the bot cannot add an indicator beyond a z-score and an SMA.

| | |
|--|--|
| Rules | Bollinger bandwidth `(upper − lower) / middle` at 2 standard deviations. Long on the first bar where bandwidth is no longer the lowest of the last X bars **and** close is above SMA(50) **and** the z-score is positive. Flat otherwise. |
| Indicators | Bollinger bandwidth, Bollinger z-score, SMA(50). |
| Sweep | Band window 15, 20, 30. X = 60, 120, 180. SMA fixed at 50. |
| Bars | Daily. |
| Source | [Baseline §2.1](crypto-spot-baseline-improvements.md#21-squeeze-bandwidth-breakout). No Sharpe was stated for this variant. |

### 7. Funding-rate veto (needs adapting)

Trade spot only. Funding is a signal, not a position and not a cashflow. Skip the whole candidate if the series is not already available. Do not fetch a perp book.

| | |
|--|--|
| Rules | Inner book fixed as in candidate 4 (trend-gated Bollinger, 20 / 1.0 / 200). At each settlement, `fund_8h = funding_rate × (8 / interval_hours)`. The daily value is the **last settlement at or before that day's close**. `z` is the trailing z-score of `fund_8h`. If the inner signal is long and `z > z_hi`, stay flat. Never short. |
| Indicators | 8-hour-normalized funding z-score, joined to the spot close. Inner Bollinger z-score and SMA. |
| Sweep | z window 30 and 60 daily values. `z_hi` = 1.0, 1.5, 2.0. One coin at a time, and only coins whose funding you actually have. |
| Bars | Daily. |
| Source | Interval normalization and the "high funding is crowded" hypothesis: [FMZ, 31 Aug 2026](https://www.fmz.com/digest-topic/11029) and [FMZ APFF, 7 Sep 2026](https://www.fmz.com/digest-topic/11035). The author of the first post reports the factor's sign flipping across nearby samples. Write-up: [normalize the clock](funding-basis-carry.md#2-normalize-the-clock-before-you-rank-funding). |

### 8. Attention or on-chain gate (needs adapting)

Last. BTC only for the Google result. ETH or BNB only if that coin has its own series. The series is a signal; the fill is Bybit spot.

| | |
|--|--|
| Rules | Inner book as in candidate 4. Let `a` be a weekly attention or on-chain reading known before the week's trades (Google searches for "Bitcoin", or one level such as MVRV or SOPR). Long only when the inner signal is long and the trailing z-score of `a` is above the threshold. Flat otherwise. |
| Indicators | Trailing z-score of the external series. Inner Bollinger z-score and SMA. |
| Sweep | z window 4, 8, 12 weeks. Threshold 0 and 1.0. These cutoffs are a translation of the paper's quintile sort, not the sort itself. |
| Bars | Daily positions, weekly signal updates. |
| Source | Attention magnitudes: [NBER WP 24877](https://www.nber.org/papers/w24877). On-chain shape, with no Sharpe stated: [arXiv:2308.00013](https://arxiv.org/abs/2308.00013). |

Not handed to the bot: perp-versus-spot convergence, cash-and-carry, any short basket, the 24-hour roll-out (hourly and negative at 10 bps), quarter-hour order flow, and books that need coins other than BTC, ETH, and BNB. Reasons are on each strategy's AlgoDaemon note.

## Page map

| Page | What it covers |
|------|----------------|
| [Baseline improvements](crypto-spot-baseline-improvements.md) | BTC daily Bollinger momentum, squeeze, 200-day filter, ATR sizing, StochRSI, pairs |
| [Momentum, reversal, and filters](momentum-reversal-filters.md) | Time-series momentum, daily reversal versus liquid momentum, trend and cross-asset gates |
| [Volatility and the cross-section](volatility-and-cross-section.md) | Vol targeting, size / momentum / volume factors, factor momentum, risk-balanced baskets |
| [Funding, basis, and carry](funding-basis-carry.md) | Funding as a factor, 8-hour normalization, perp-spot bounds, cash-and-carry |
| [Microstructure, on-chain, and unusual](microstructure-onchain-unusual.md) | Screen-number roll-out, clock-time order flow, attention, on-chain value, adaptive factor weights |

## Sources consulted, by language

Dates are publication or post dates as stated by the source. "Read" means the abstract or the full text was retrieved in this pass. "Listed only" means a bibliographic record was found and the body was not.

### English

| Source | What was read |
|--------|----------------|
| [Liu and Tsyvinski, NBER WP 24877](https://www.nber.org/papers/w24877) (August 2018), *Risks and Returns of Cryptocurrency* | Working-paper PDF. Time-series momentum and investor attention. |
| [Liu, Tsyvinski, and Wu, NBER WP 25882](https://www.nber.org/papers/w25882) (May 2019) and [Journal of Finance, 2022](https://doi.org/10.1111/jofi.13119) | WP PDF for the weekly long-short magnitudes. JF abstract for the published three-factor claim. The WP says nine successful strategies; the JF abstract says ten. Magnitudes below are attributed to the WP only. |
| [Moreira and Muir, Journal of Finance, 2017](https://doi.org/10.1111/jofi.12513), *Volatility-Managed Portfolios* | Abstract. Equity and factor evidence, cited for the mechanism, not as a crypto backtest. |
| [Zaremba, Bilgin, Long, Mercik, and Szczygielski, IRFA, 2021](https://doi.org/10.1016/j.irfa.2021.101908) | Abstract. |
| [Grobys and Sapkota, Economics Letters, 2019](https://doi.org/10.1016/j.econlet.2019.03.028) | Abstract. A negative momentum result. |
| [Begušić and Kostanjčar, arXiv:1904.00890](https://arxiv.org/abs/1904.00890) | Abstract. No Sharpe figure in the abstract or the HTML full text. |
| [Fieberg, Liedtke, Metko, and Zaremba, Quantitative Finance, 2023](https://doi.org/10.1080/14697688.2023.2269999), *Cryptocurrency factor momentum* | Abstract via OpenAlex. |
| [He, Manela, Ross, and von Wachter, arXiv:2212.06888](https://arxiv.org/abs/2212.06888), *Fundamentals of Perpetual Futures* (this draft September 2026) | HTML full text, including Table 5. |
| [Ackerer, Hugonnier, and Jermann, NBER WP 32936](https://www.nber.org/papers/w32936), *Perpetual Futures Pricing* | NBER page abstract. Pricing theory, not a Sharpe. |
| [Fang et al., Financial Innovation, 2022](https://doi.org/10.1186/s40854-021-00321-6), *Cryptocurrency trading: a comprehensive survey* | Abstract. Map of the literature, not a strategy. |
| [Bui and Nguyen-Van, arXiv:2602.11708](https://arxiv.org/abs/2602.11708), *AdaptiveTrend* | Abstract only. Preprint claim; not audited. |
| [Hansen, arXiv:2607.09426](https://arxiv.org/abs/2607.09426), *The Quarter-Hour Effect* | Abstract. |
| [arXiv:2602.00776](https://arxiv.org/abs/2602.00776), *Explainable Patterns in Cryptocurrency Microstructure* | Abstract. No performance figure in the abstract. |
| [arXiv:2308.00013](https://arxiv.org/abs/2308.00013), *Bitcoin Gold, Litecoin Silver* | Abstract. No performance figure. |
| [OctopusTakopi/24h-rollout-effect](https://github.com/OctopusTakopi/24h-rollout-effect) README | Full README retrieved. The README attributes the original hourly rule to a public X thread (`https://x.com/therobotjames/status/2080281157246259663`). That post's body was **not** retrieved here. |
| SSRN 3913263 (Dobrynskaya, *Cryptocurrency Momentum and Reversal*) and SSRN 4322637 (Drogen, Hoffstein, and Otte, *Cross-sectional Momentum in Cryptocurrency Markets*) | **Listed only.** SSRN returned a Cloudflare challenge. No claims from these papers are used below. |

### Chinese (中文)

| Source | What was read |
|--------|----------------|
| [FMZ 文库, 小小梦, 2026-09-07](https://www.fmz.com/digest-topic/11035), 「让因子接受持续考核：在 FMZ 实现 APFF 多品种永续合约策略」 (*Let factors face continuous review: an APFF multi-asset perpetual strategy on FMZ*) | Full post. Author states long-run performance still needs more sample. No Sharpe is stated. |
| [FMZ 文库, ianzeng123, 2026-08-31](https://www.fmz.com/digest-topic/11029), 「牛来上了币安合约，恐高也恐低，于是我去做了一个不赌方向的策略」 (*A Binance perp I would neither chase nor short, so I built a direction-neutral strategy*) | Full post, including the author's own before/after figures for volatility scaling. |
| [FMZ 文库, 小小梦, 2026-08-28](https://www.fmz.com/digest-topic/11023), 「屏幕上的 24h 涨跌幅会影响短线价格吗？」 (*Does the on-screen 24h change affect short-term price?*) | Full post. Explicitly refuses to treat the crypto replication as proof for the TradFi variant. |

### Russian

| Source | What was read |
|--------|----------------|
| [Хабр, Alex-ok, 2025-05-20](https://habr.com/ru/articles/911056/), «Арбитраж криптовалют — или переливаем из пустого в порожнее» (*Crypto arbitrage — or pouring from one empty vessel into another*) | Full post. A warning that public "arbitrage" Telegram channels are often scams, not a strategy with a track record. |
| [Хабр, negrbluad, 2025-08-30](https://habr.com/ru/articles/942400/), «Комиссии криптобирж в алготрейдинге» (*Crypto-exchange fees in algo trading*) | Opening sections. Practitioner argument that fees, and maker versus taker, decide whether a bot survives. |

### Japanese, Korean, and other

No citable primary write-up was retrieved. note.com's search page loaded but article bodies did not; its search API returned 403. A Qiita API query on 仮想通貨 / 暗号資産 returned news, scam warnings, and generic bot tutorials, not a strategy with a stated rule and a stated result. Korean sources were not retrieved. Those gaps are listed below rather than filled in.

## Sites that were inaccessible, paywalled, or empty

| Site | What happened |
|------|----------------|
| **Patreon** search (`patreon.com/cwsearch`) | HTTP 404. No public creator post or description was retrieved. Member-only posts are paywalled; nothing behind a paywall is described here. |
| **SSRN** | Cloudflare "Just a moment" challenge. Bibliographic records only. |
| **知乎 Zhihu** search | Shell / block page, no article bodies. The 知乎专栏 homepage loaded and contained no strategy text. |
| **雪球 Xueqiu** | WAF challenge page, no articles. |
| **JoinQuant 聚宽** | Page text: 「当前地区暂不支持访问」 (this region is not supported). |
| **掘金量化 myquant.cn** | SafeLine WAF, HTTP 403. |
| **BigQuant** | App shell only; no research article text. |
| **华泰 Huatai / 国泰君安 Guotai Junan** | TLS handshake failed (`unsafe legacy renegotiation`). |
| **中信证券 CITIC** research host | Homepage shell only (title 「中信证券」), no research note. |
| **Binance** Chinese research URL | HTTP 202, empty body. |
| **OKX** Chinese learn URL for funding | HTTP 404, redirected to the exchange homepage. |
| **微信 WeChat** via Sogou | The search page for 「加密货币资金费率套利」 loaded and said about 337 results. Individual article links and bodies were fragmented and are **not** cited. |
| **Bilibili** search for 「加密货币量化」 | The search page loaded. Visible hits were tutorial and promo video titles, not papers. Videos were not transcribed, so they are not used as sources. |
| **DuckDuckGo** | Bot challenge, no results. |
| **Habr** site search UI | JavaScript prompt to run the search; not usable. The two posts above were fetched by direct URL after the Habr API returned titles. The API's other hits for 「фандинг」 were unrelated. |
| **X / Twitter** thread cited by the roll-out README | Not retrieved. |

## How to use a page

Each strategy section has the same fields: name, sources and language, mechanism, data, rough rules, why it might change Sharpe, reported performance (or an explicit "not stated"), risks, fit, and an AlgoDaemon testability line (as-is, needs adapting, or can't be tested). The runs to give the bot are [AlgoDaemon hand-off](#algodaemon-hand-off), not every section. Agreeing to **try** one of them is research. Agreeing to **add** an indicator, a funding series, or a position-size layer is platform design and belongs under `docs/design/` plus `docs/decisions.md` when it is built.
