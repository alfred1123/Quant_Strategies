# Crypto spot — baseline improvements

**Doc type:** strategy research  
**Status:** hypothesis — not backtested on-platform for the variants below. Nothing here is scheduled for live.

A later pass ranks a wider set of Sharpe ideas (momentum evidence, funding, cross-section, microstructure) and says which to try first: [Sharpe ideas — where to start](sharpe-ideas-index.md). This page stays the write-up of the BTC daily Bollinger baseline.

This page condenses an external research thread about raising the risk-adjusted return of a
**BTC daily, Bollinger momentum, long-only** strategy. That baseline had a backtest Sharpe of
about **1.48**. The page also records which ideas the platform can already express and which
would need new code.

!!! warning "Sharpe figures below are third-party claims"
    The 1.92 and 2.0+ figures come from blog posts and forum write-ups. They have not been
    reproduced here, and their fee, slippage, and sample-period assumptions are unknown. Treat
    them as hypotheses to backtest, not as expected returns.

## 1. Baseline

| Item | Value |
|---|---|
| Product | BTC spot (`*.crypto`, decision #21) |
| Bar | Daily |
| Recipe | `get_bollinger_band` (z-score) + `momentum_long` |
| Reported Sharpe | ~1.48 |

A 1.48 Sharpe on daily BTC is already strong. The ideas below target the two usual weak spots
of a plain band breakout: **false breakouts in sideways markets**, and **large drawdowns in
bear markets**.

## 2. Improvements to the baseline

### 2.1 Squeeze / bandwidth breakout

Only take a breakout after a period of low volatility. Bollinger **bandwidth**
(`(upper − lower) / middle`) falling to a multi-month low marks a "squeeze"; the breakout
that follows tends to carry further than one from already-wide bands.

The widely cited **Squeeze Momentum** variant (LazyBear/TTM style) defines the squeeze as
the Bollinger Bands sitting *inside* the Keltner Channels (EMA ± k × ATR). It goes long when
the squeeze releases with positive momentum, and it is usually paired with a 50 EMA trend
filter.

### 2.2 Macro trend filter (50 / 200-day SMA)

Only allow longs when price is above the 200-day SMA (or when the 50-day SMA is above the
200-day SMA). The aim is to sit out long bear phases, which cuts max drawdown and usually
raises Sharpe more than it lowers return.

### 2.3 Volatility targeting (14-day ATR)

Scale position size inversely to recent volatility, e.g. `size = target_vol / ATR_14`, capped
at 1× for spot. Smaller positions in turbulent regimes lower the PnL standard deviation, which
is the denominator of Sharpe.

## 3. Other strategies from the thread

| Strategy | Bar | Idea | Claimed Sharpe |
|---|---|---|---|
| Squeeze Momentum | Daily | BB inside Keltner = squeeze; long on release with 50 EMA filter | not stated |
| StochRSI Exhaustion Snap | 4h | Mean reversion: long when StochRSI is deeply oversold and turns up; exit on the snap back | 1.92 |
| Volume-enhanced stat-arb / pairs | Intraday–daily | Trade the spread of two cointegrated coins when it passes 2σ; volume filter to avoid thin moves | 2.0+ |

Pairs trading is market-neutral and needs a short leg, so on spot-only venues it is only
partially possible (long the cheap leg, flat the rich one).

## 4. Measurement hygiene

These points apply to any number quoted above:

- **Annualize with √365** for crypto, not √252. The platform already does this: Sharpe is
  `mean / std × sqrt(trading_period)` and `REFDATA.ASSET_TYPE` gives crypto
  `TRADING_PERIOD = 365` (`quant/strategy/performance.py`).
- **Report Sortino alongside Sharpe.** Long-only crypto has fat upside tails; Sharpe penalizes
  them as "risk". Sortino only penalizes downside deviation. The platform does not compute
  Sortino today.
- **Costs.** Fees, slippage, and tax each come off the edge. The default haircut is 10 bps per
  unit of turnover (Bybit VIP-0 spot taker); see
  [Transaction Costs](../guides/indicators-strategies.md#transaction-costs). Higher-frequency
  ideas such as the 4h StochRSI trade far more often, so the fee drag grows with them. A
  volume filter and maker (limit) orders are the usual mitigations; apply is a market order
  today (decision #38).
- **Sample size.** Short histories inflate Sharpe. Metrics are `NaN` below
  `MIN_METRIC_OBS` finite PnL bars. A search whose loaded series is shorter than
  the longest window plus that floor fails before the first trial (decision #82).
  Clearing the floor is not proof of robustness. Check out-of-sample periods and
  more than one coin.

## 5. What the platform can express today

| Idea | Expressible now? | How |
|---|---|---|
| Baseline BB momentum long | Yes | `get_bollinger_band` + `momentum_long` |
| 200-day trend filter | **Approximately** | FILTER conjunction: gate = `get_bollinger_band` window 200, threshold 0, `momentum_long`. The z-score is positive exactly when price > SMA_200, so the gate passes only above the 200-day average. Signal = the baseline recipe. |
| 50 / 200 SMA cross | No | `get_sma` returns the SMA *level*, so thresholds compare against a price, not another average. Needs a ratio/spread indicator. |
| StochRSI | No | `get_rsi` and `get_stochastic_oscillator` exist separately; stochastic is applied to price High/Low/Close, not to RSI. |
| 4h bars | No | `REFDATA.TM_INTERVAL` has only `DAILY` and `1H`. A 4h row would be needed, and the deployment schedule would follow it, since schedule is locked to the fitted cadence (decision #80). |
| Squeeze (bandwidth or BB-inside-Keltner) | No | No bandwidth, ATR, or Keltner indicator. |
| ATR volatility targeting | No | Signals are discrete {−1, 0, 1}; there is no position-sizing layer. |
| Volume as the factor input | Yes | `REFDATA.DATA_COLUMN` includes `volume` (`COLUMN_NAME = Volume`), and a factor can set `data_column` to it. That is the indicator input, not a filter that drops thin bars. |
| Pairs / stat-arb | No | Single-instrument signals only; needs a spread input and a short leg. |
| Sortino | No | Not in `Performance`. |

Conjunction semantics are documented under
[Conjunction Modes](../guides/indicators-strategies.md#conjunction-modes-multi-factor).

## 6. Suggested order if this is pursued

Ordered by value per unit of effort:

1. **Backtest the 200-day FILTER gate now.** It needs no code, only a second factor.
2. **Add Sortino** to `Performance`, next to Sharpe and Calmar.
3. **Add a bandwidth indicator** (and optionally ATR/Keltner), so the squeeze variant can be
   tested as a FILTER gate.
4. **Position sizing** (ATR vol targeting). This is the largest change: it touches the PnL
   line, turnover-based fees, and live order sizing.
5. **Pairs trading.** This needs multi-instrument signals and short capability, so it is out
   of scope for spot-only deployment.

## 7. AlgoDaemon testability

The hand-off bot is Bybit spot, BTC/ETH/BNB only, 10 bps per trade, daily bars preferred, hourly allowed, backtests only. No derivatives. Sweep grids are in [AlgoDaemon hand-off](sharpe-ideas-index.md#algodaemon-hand-off).

| Idea on this page | AlgoDaemon |
|-------------------|------------|
| Baseline Bollinger momentum, long only | **As-is**, daily, each of the three coins. It is the inner signal of hand-off row 1. |
| 200-day trend filter | **As-is**. Hand-off row 1. |
| Squeeze / bandwidth breakout | **As-is** from daily OHLC if the bot can compute bandwidth. Hand-off row 6, after the simpler gates. |
| ATR volatility targeting, continuous size | **As-is** only as a weight in `(0, 1]` from daily ATR or realized vol. Spot cannot lever. Prefer the binary flat gate, hand-off row 4, if the bot has no size input. |
| StochRSI exhaustion, 4h | **Can't** be tested on 4-hour bars. Hourly is allowed and is a poor match for 10 bps. Not in the hand-off. |
| Pairs / stat-arb | **Can't** be tested with a short leg. Long-the-cheap / flat-the-rich among these three coins would be an adaptation, and the thread did not state the pair, hedge ratio, or window, so it is not in the hand-off. |

## 8. Venue note: Bybit error 10024

The thread also surfaced a Bybit `retCode 10024` ("regulatory restriction"). Bybit returns this
when the account's jurisdiction is not allowed to trade the product or the request originates
from a restricted region. It is an account/egress issue, not a strategy one: see
[UK egress proxy](../architecture/infrastructure.md#uk-egress-proxy). Live Bybit wiring also
still uses `default_type="linear"` (perp) while research is on spot; see the note at the end of
[Transaction Costs](../guides/indicators-strategies.md#transaction-costs).
