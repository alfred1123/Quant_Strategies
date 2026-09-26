# Deployment performance reconcile

**Status:** Proposed. Covers [Plan to profit](plan-to-profit.md) Phase 2.1 (data model), 2.2 (job), and 2.3 (UI). Resolves open decision #3 in that page once adopted. Depends on `TRADE.INTENT` ([Multi-strategy netting §5](multi-strategy-netting.md#5-intent-first), decision #90).

**Question it answers:** is each live strategy earning what its backtest said it would, does the account hold what the strategies asked for, and when either is behind, is the cause the strategy or the execution?

---

## 1. Why a stored daily Sharpe fails

The first sketch in Phase 2.1 stored one row per deployment per day holding *live Sharpe* and *cumulative return*. That row breaks in two ways.

**A deployment stops partway through its life.**

- **Auto-pause** (decisions #70 and #79). Three failed attempts in one pass version the deployment `PAUSED` with `IS_ENABLED_IND='N'`. The broker position stays open.
- **Kill switch.** The same write with the same result: disabled, position held.
- **Re-enable.** Ops turns it back on days later, so the live history now has a hole in it.

A Sharpe number computed at each snapshot is taken over whatever window existed that day. Once the window has a hole, the value mixes days the strategy managed with days nobody managed. It also cannot be compared with a backtest, because the backtest never had the hole.

**Two strategies trade one asset on one account.** The broker keeps one position per symbol per account: the base-coin balance on spot, the net contract size on a perp. `EXECUTION_EVENT.POSITION_QTY` records that account number ([Multi-strategy netting §3](multi-strategy-netting.md#3-where-position_qty-really-belongs)). The broker cannot say how much of it belongs to each strategy, so a per-strategy return built from it is a guess.

**Answer:** store per-bar returns, derive every ratio on read, and take each strategy's position from its own `TRADE.INTENT` target. Reconcile at two levels:

| Level | Grain | Position | Answers |
|---|---|---|---|
| **Strategy** | deployment × bar | `INTENT.TARGET_QTY` — what the strategy asked for | Is the strategy earning its backtest? |
| **Account** | credential × instrument × bar | Broker holding | Does the account hold and earn what the strategies asked for? |

The two levels meet in one identity (§4.3). Its remainder is the alarm.

---

## 2. Which bars belong to a strategy

A deployment applies at slots `s_k`, each one `EXECUTE_OFFSET` before bar `k` closes (decision #81). The position from `s_k` to `s_{k+1}` is whatever the apply at `s_k` chose.

**Rule:** bar `k+1` is **managed** for a deployment when it has an `INTENT` at `s_k` and that pass recorded a successful attempt in `TRADE.EXECUTION_EVENT`. A `HOLD` counts: `OrderRetryExecutor` writes an attempt row for it. The intent and its attempts join on `(DEPLOYMENT_ID, TRANSACT_AT)`.

Every stop case falls out of that one rule:

| Event | Bars before | Bar after the event | Later bars |
|---|---|---|---|
| Auto-pause at slot `s_k` (third failure) | managed | unmanaged, because `s_k` failed | unmanaged until a slot succeeds again |
| Kill switch between `s_k` and `s_{k+1}` | managed | still managed; `s_k` chose that position | unmanaged |
| Re-enable, next slot succeeds | — | managed again | managed |
| Scheduler missed `s_k` (host down) | managed | unmanaged; no intent at `s_k` | resumes on the next successful slot |
| `QTY` or strategy changed (new `DEPLOYMENT_VID`) | managed | managed under the new VID | managed |

An unmanaged bar still gets a strategy row with `IS_MANAGED_IND = 'N'`, and strategy metrics leave it out. A paused deployment still carries its last target, and the account still holds it, because a pause does not flatten. That exposure is real money and belongs in the account level.

Strategy rows start at the first successful slot. They stop once the deployment is disabled **and** its last target is zero.

---

## 3. Strategy level

### 3.1 Live return

The strategy's position for bar `k+1` is `TARGET_QTY` from its intent at `s_k`. It is marked on the same `MARKET_DATA.PRICE_BAR` closes the signal reads (decision #45), from the deployment's own `SOURCE_APP_ID`. `c_k` is the close of bar `k`.

- `UNIT_NOTIONAL_AMT` = `QTY × c_k` under the `DEPLOYMENT_VID` in force at `s_k`. It is the notional of one full unit. Dividing by it puts live on the backtest's −1 / 0 / +1 scale, and a `QTY` change midway leaves the series comparable.

| Component | Formula | What it isolates |
|---|---|---|
| Position | `TARGET_QTY × (c_{k+1} − c_k) / UNIT_NOTIONAL_AMT` | The move the strategy's position caught |
| Fill gap | `Σ fill_qty_signed × (c_k − fill_px) / UNIT_NOTIONAL_AMT` | Filling at `s_k` on the forming candle against the close the backtest assumes |
| Fee | `− Σ fee_in_quote / UNIT_NOTIONAL_AMT` | Broker-charged fee from `TRADE.TRANSACTION.FEE_AMT` |

`LIVE_RETURN` is the sum.

**Which fills are the strategy's.** While each deployment applies on its own, a `TRANSACTION` row carries the `DEPLOYMENT_ID` that placed it, and the fills are that deployment's. Once netting places one order for several strategies, the order's fill gap and fee are shared by each strategy's `|Δ TARGET_QTY|` at that slot. The fee netting saves lands at the account level.

A strategy whose order never filled still holds its target on this level. That is deliberate: this level measures the strategy. The account level shows the missing fill.

### 3.2 Backtest return on the live bars

The benchmark is the strategy's own backtest **replayed over the live window**. The stored `BT.RESULT` covers the research sample; its dates are not the live dates.

- Config: `BT.STRATEGY.CONFIG_JSON` for the `STRATEGY_ID` / `STRATEGY_VID` on the deployment version, including its stored `fee_bps`.
- Bars: the same `PRICE_BAR` series the live marks use, closed bars only.
- Engine: `Performance` in `quant/strategy/performance.py`, unchanged. Its PnL line is `position_{t-1} × return_t − |Δposition| × fee` (see [Transaction costs](../guides/indicators-strategies.md#transaction-costs)).

The replay needs the indicator warmup ahead of the first live bar, the same lookback live apply already loads (`live_lookback_days`).

`BACKTEST_RETURN` is the replay's `pnl` on bar `k+1`.

### 3.3 Two comparisons, two causes

| Compare | Gap means |
|---|---|
| `LIVE_RETURN` vs `BACKTEST_RETURN`, managed bars | **Execution drift.** Fill gap, fee model, signal flips on the forming candle. |
| Replay Sharpe vs research Sharpe (`BT.RESULT`) | **Edge decay or regime.** The strategy itself earns less on new data. |

A deployment can execute perfectly and still lose because the edge is gone. It can also keep its edge and still lose it to fees. Keeping the two apart is the point.

### 3.4 Known differences that are not edge decay

These are listed so the UI labels them instead of blaming the strategy. The engine side is in the "Not modelled" list under [Transaction costs](../guides/indicators-strategies.md#transaction-costs).

- **Fill timing.** Live fills `EXECUTE_OFFSET` before the close on the forming candle (decision #81). The fill gap column measures it directly.
- **Signal on the forming candle.** Near a band edge the live signal can differ from the closed-bar signal. It shows up as `TARGET_POSITION ≠ BACKTEST_POSITION`.
- **Reversal in two steps.** `intended_side` maps signal −1 on a long to `SELL` (flatten), and the short opens on the next slot. The backtest reverses in one bar and pays 2× fee there.
- **Fees.** The broker fee against the single `fee_bps`: taker, VIP tier, fee coin.
- **Slippage, partial fills, funding.** Slippage lands in the fill gap. A partial fill leaves the account short of the target and shows at the account level. Funding needs its own column once a perp deployment exists.

---

## 4. Account level

### 4.1 What it holds

One row per `(API_CREDENTIAL_ID, INTERNAL_CUSIP, IS_PAPER_IND)` per bar. The credential and paper flag come off the `DEPLOYMENT_VID` of each deployment on that asset.

- `HELD_QTY` — the broker holding after the fills at `s_k`: `POSITION_QTY` on the last attempt at `s_k`, plus signed `TRANSACTION.QUANTITY` of the fills that followed.
- `TARGET_QTY` — `Σ TARGET_QTY` over the deployments' latest intents on this asset, paused ones included.
- `PNL_AMT` — the real result in quote currency: `HELD_QTY × (c_{k+1} − c_k)` plus the fill gap, minus every fee on the asset.

`HELD_QTY − TARGET_QTY` is the **position gap**. It is zero when the account holds exactly what the strategies asked for.

### 4.2 Mixed intervals

The account row uses the finest interval among the deployments on the asset. An hourly and a daily strategy on BTC give hourly account rows. For crypto the daily close is also an hourly close, so 24 hourly moves sum to the daily move exactly. The identity below is checked at the daily grain.

### 4.3 The identity

For each account × asset × day:

```text
PNL_AMT  =  Σ strategy PnL (LIVE_RETURN × UNIT_NOTIONAL_AMT, managed and unmanaged)
          + fee saved by netting
          + REMAINDER_PNL_AMT
```

`REMAINDER_PNL_AMT` is stored. It is non-zero when the account holds something no strategy asked for:

| Cause | Position gap looks like |
|---|---|
| Two deployments fight without netting: B sees A's long and answers `HOLD` | `HELD_QTY` short of `TARGET_QTY` by B's `QTY` |
| Partial fill | Short of target by the unfilled part |
| Manual trade on the account | Any size, no intent behind it |
| Dust below `_FLAT_EPS` | Tiny, ignorable |

A remainder past a threshold is the Phase 2.4 alert. The threshold is a `CONFIG` row; it is not in code.

### 4.4 Ratios on the account

Account return for a day is `PNL_AMT / Σ UNIT_NOTIONAL_AMT` over the deployments managed that day. Account Sharpe on the asset comes from that daily series with `trading_period` for daily bars. A Sharpe across the whole account, all assets, needs account equity by day; balances have no history yet, so that stays out of this design.

---

## 5. Tables

Both are soft-versioned like the rest of `TRADE`. A recompute that changes any value inserts the next VID and flips `IS_CURRENT_IND`. One that changes nothing is a no-op. A late `TRANSACTION` row (fill writes are best-effort) corrects its bar on the next run. Audit is `USER_ID` and `CREATED_AT`; no `UPDATED_AT`.

### 5.1 `TRADE.DEPLOYMENT_PERFORMANCE` — strategy level

| Column | Type | Meaning |
|---|---|---|
| `DEPLOYMENT_PERFORMANCE_ID` | `UUID` | Row identity |
| `DEPLOYMENT_PERFORMANCE_VID` | `INTEGER` | Version |
| `DEPLOYMENT_ID` | `UUID` | Logical deployment |
| `DEPLOYMENT_VID` | `INTEGER` | Version in force at `s_k` |
| `INTENT_ID` | `UUID` | The intent at `s_k`; null on a bar with no intent |
| `TM_INTERVAL_ID` | `INTEGER` | Bar interval, as on `PRICE_BAR` |
| `BAR_TIMESTAMP` | `TIMESTAMPTZ` | The bar, as on `PRICE_BAR` |
| `IS_MANAGED_IND` | `CHAR(1)` | `Y` when the pass at `s_k` succeeded (§2) |
| `TARGET_POSITION` | `NUMERIC` | `TARGET_QTY / QTY` |
| `BACKTEST_POSITION` | `NUMERIC` | Replay position −1 / 0 / +1 |
| `UNIT_NOTIONAL_AMT` | `NUMERIC` | `QTY × c_k` — turns returns back into quote amounts |
| `LIVE_RETURN` | `NUMERIC` | Sum of the three components |
| `LIVE_FILL_GAP_RETURN` | `NUMERIC` | Fill gap component |
| `LIVE_FEE_RETURN` | `NUMERIC` | Fee component |
| `BACKTEST_RETURN` | `NUMERIC` | Replay `pnl` |

One current row per `(DEPLOYMENT_ID, TM_INTERVAL_ID, BAR_TIMESTAMP)`. For a daily deployment that key is the trade date Phase 2.2 names.

### 5.2 `TRADE.ACCOUNT_PERFORMANCE` — account level

| Column | Type | Meaning |
|---|---|---|
| `ACCOUNT_PERFORMANCE_ID` | `UUID` | Row identity |
| `ACCOUNT_PERFORMANCE_VID` | `INTEGER` | Version |
| `API_CREDENTIAL_ID` | `INTEGER` | Account |
| `INTERNAL_CUSIP` | `TEXT` | Instrument |
| `IS_PAPER_IND` | `CHAR(1)` | Paper or live |
| `TM_INTERVAL_ID` | `INTEGER` | Finest interval on the asset (§4.2) |
| `BAR_TIMESTAMP` | `TIMESTAMPTZ` | The bar |
| `HELD_QTY` | `NUMERIC` | Broker holding (§4.1) |
| `TARGET_QTY` | `NUMERIC` | Sum of strategy targets |
| `CLOSE_PX` | `NUMERIC` | `c_{k+1}`, so notional is `HELD_QTY × CLOSE_PX` without a join |
| `PNL_AMT` | `NUMERIC` | Real result in quote |
| `FEE_AMT` | `NUMERIC` | Fees charged in quote |
| `REMAINDER_PNL_AMT` | `NUMERIC` | §4.3 remainder |

One current row per `(API_CREDENTIAL_ID, INTERNAL_CUSIP, IS_PAPER_IND, TM_INTERVAL_ID, BAR_TIMESTAMP)`.

### 5.3 Procedures

- `TRADE.SP_INS_DEPLOYMENT_PERFORMANCE` and `TRADE.SP_INS_ACCOUNT_PERFORMANCE` each take a batch of bars and apply the insert, version, or no-op rule per key.
- `TRADE.SP_GET_DEPLOYMENT_PERFORMANCE` and `TRADE.SP_GET_ACCOUNT_PERFORMANCE` return current rows in a time range, scoped by `APP_USER_ID` like `SP_GET_TRANSACTION`. The chart reads only these.

Each logs with `V_LOG_START TIMESTAMPTZ := clock_timestamp();`. The release is a new `trade` changeset with context `trade` alone; adding `prod-deploy` is a separate decision.

### 5.4 Snapshot table vs materialized view (open decision #3)

**Snapshot tables.** A materialized view would rescan `INTENT`, `EXECUTION_EVENT`, `TRANSACTION`, and `PRICE_BAR` on every refresh, and it cannot hold the backtest replay, which is Python. The tables are written incrementally, version their corrections, and the chart reads them with no joins.

---

## 6. The job (Phase 2.2)

Runs once a day on the trade host's cron (decision #35), after the daily `23:55 UTC` slot has settled.

1. For each deployment with rows to write (enabled, or disabled with a non-zero last target), read the last current `BAR_TIMESTAMP`. Start one bar before it so a late fill on that bar is picked up.
2. Read intents, attempts, fills, and `DEPLOYMENT` versions from that time forward, and `PRICE_BAR` closes plus warmup for the range.
3. Classify each bar per §2, compute §3.1, replay §3.2, and write strategy rows.
4. Group the deployments by account × asset, compute §4 from the same reads plus the strategy rows just written, and write account rows.

Each run reads only the bars since the last row, which meets the Phase 2.1 task of avoiding a full scan. The job writes no orders and needs no broker credentials.

---

## 7. UI (Phase 2.3)

### 7.1 Open position and notional

The Trade page shows what is open now, at both levels:

| Row | Quantity | Notional | Source |
|---|---|---|---|
| Each deployment | Latest `INTENT.TARGET_QTY` | `TARGET_QTY × mark` | `SP_GET_INTENT` |
| Account × asset | Broker holding | `HELD × mark` | `GET /api/v1/trade/accounts/{id}/snapshot` |
| Position gap | Holding − Σ targets | Gap × mark | Derived; highlighted when non-zero |

The mark is the snapshot's `mark_price`, or the latest `PRICE_BAR` close when the venue returns none. Unrealized PnL per deployment is its `DEPLOYMENT_PERFORMANCE` return since the target last changed, times `UNIT_NOTIONAL_AMT`.

### 7.2 Performance

- **Cumulative return**, live and backtest, per deployment over managed bars. Unmanaged stretches are shaded.
- **Sharpe**, live and replay, over managed bars only, annualised with the interval's `trading_period` the same way `Performance` does it. Below `MIN_METRIC_OBS` (60) managed bars it reads "insufficient data", the same floor the backtest uses. Seven days of rows (the Phase 2.3 exit criterion) show the return chart; Sharpe arrives at bar 60.
- **Account × asset**: daily PnL, account Sharpe (§4.4), and the remainder with its cause when one is identifiable.
- **Drift breakdown**: summed fill gap, fee, and position difference, so a user sees *where* live fell behind.
- **Last reconcile** timestamp from the newest `CREATED_AT`, with the stale warning past 36 hours.
- Paper deployments (`IS_PAPER_IND`) are labelled and kept out of any live total.

Managed bars on either side of a pause are joined into one series. That is correct for the strategy's per-bar distribution; the shading keeps the gap visible.

---

## 8. Gaps to close before building

| Gap | Where | Fix |
|---|---|---|
| No per-strategy position | Only the account holding is recorded | `TRADE.INTENT` ([Multi-strategy netting §5](multi-strategy-netting.md#5-intent-first)) — build first |
| Fee currency is dropped | `_extract_fee` in `quant/trade/brokers/ccxt/confirm.py` keeps `fee.cost` and discards `fee.currency`. Bybit spot charges a buy fee in the base coin and a sell fee in the quote, so `FEE_AMT` mixes units. | Record the fee currency on `TRADE.TRANSACTION` and convert base fees at the fill price |
| Reads have no time filter | `SP_GET_TRANSACTION` and `SP_GET_EXECUTION_EVENT` return the newest `IN_LIMIT` rows | Add a from-timestamp parameter to those two procedures |
| Spot holdings missing from the snapshot positions | `fetch_open_positions` lists contracts; a spot holding appears only as a balance, with no mark or notional | Add spot holdings as position rows, read from the base balance the way `fetch_position_qty` already does for spot |
| Fill ↔ attempt link | `TRANSACTION` joins to `EXECUTION_EVENT` only by `VENDOR_ORDER_ID` | Sufficient for ccxt; confirm Futu fills carry the same id |
| Funding | No perp deployment yet | Add a funding column when the first `ISSUE_TYPE = future` deployment goes live |

---

## Related

- [Plan to profit](plan-to-profit.md) — Phase 2 tasks and exit criteria
- [Multi-strategy netting](multi-strategy-netting.md) — `TRADE.INTENT`, and the order side that comes later
- [Scheduler & trade open questions](scheduler-trade-open-questions.md#5-stuck-deployment-bad-config-permanent-broker-error) — auto-pause and why it does not flatten
- [Decisions](../decisions.md) — #35, #45, #70, #79, #81, #90
