# Market data capture — bars for products you don't trade

**Status: design for review, not built.** No DDL, Python or UI is committed for
this. It exists because the platform can only collect bars for instruments a
strategy is already deployed against, and the decision that made that true was
answering a different question.

**Parent:** [Scheduler & Price Bars](scheduler-price-bars.md) §3.2
**Related:** [Separate Underlying & Cache](separate-underlying.md), [Backtest API](backtest-api.md), [Alternative Data Sources](alt-data-sources.md)

---

## 1. The gap

To accumulate history for a product today you must deploy a strategy against it:
`price_bar_sync` takes its instrument list from `TRADE.SP_GET_SCHEDULED_INSTRUMENTS`,
which reads `TRADE.DEPLOYMENT`. A deployment needs a strategy, a broker
credential and a quantity.

So the one thing you cannot do is the thing you want first: **collect prices for
a product while deciding whether to trade it.** The backtest that informs the
decision needs history, and the history only starts accruing once the decision is
already made. [Decision #5](scheduler-price-bars.md#2-decisions) — *"only products
with active deployments get bars stored"* — was aimed at avoiding a bulk ingest of
every product, which is still right. It was never asked about research.

## 2. Why the coupling is incidental

Nothing about collecting bars needs a deployment:

- **Bars are public.** `CcxtBarFetcher` deliberately builds a *keyless* ccxt
  client ([§7.5](scheduler-price-bars.md#75-bar-fetcher-quantmarket_datafetcherpy)),
  precisely so market data does not depend on a user's API keys or on a trading
  session being up. Capture needs no credential, no strategy and no quantity.
- **`PriceBarService` already does all of it.** `sync`, `backfill`, `find_gaps`
  and `read_bars` are written and tested. What is missing is a second answer to
  *which instruments matter* — not new machinery.

There is also a positive reason, not just an absence of obstacles.
[§7.7](scheduler-price-bars.md#recording-which-series-produced-the-signal) records
a live problem: **strategy parameters are fitted on provider history and traded
against exchange prints.** The Phase 0.1 candidate was signed off on Glassnode
daily data and now prices against Bybit bars, which are a different series, so the
same config can produce a different position on the same day. Capturing a venue's
bars *before* committing capital is what would let a strategy be fitted on the
series it will actually trade. That is the point of this feature, and it is worth
more than the convenience.

## 3. What is subscribed

### 3.1 The key is the bar key minus time

A subscription names `(INTERNAL_CUSIP, TM_INTERVAL_ID, SOURCE_APP_ID)` — exactly
`MARKET_DATA.PRICE_BAR`'s primary key without `BAR_TIMESTAMP`, and exactly the
triple `PriceBarService.sync` is grouped by. Venue is part of it because
[decision #47](../decisions.md) makes a bar a fact *from a venue*: `btcusdt.crypto`
on Bybit and on Binance are two separate series, and subscribing to one is not
subscribing to the other.

That the triple matches `TRADE.SP_GET_SCHEDULED_INSTRUMENTS`' output shape is what
makes the union in §4 trivial rather than a translation layer.

### 3.2 Rows are per user; the warm is not

Bars are shared facts — one row per `(cusip, interval, venue, timestamp)` — so two
users subscribing to the same series must produce **one** fetch, not two. But the
subscription is a *request*, and requests belong to people:

| Model | Consequence |
|---|---|
| One platform-wide row, `USER_ID` as audit | User A unsubscribing silently stops User B's capture |
| **One row per user, warmer reads `DISTINCT`** | Unsubscribing removes only your request; the series stays warm while anyone wants it |

The second, which also matches how every other user-owned entity here behaves
(deployments are owner-scoped; `APP_USER_ID` isolation is
[decision #42](../decisions.md)'s baseline). The cost is a `DISTINCT` in one
read.

### 3.3 Soft-versioned, like `DEPLOYMENT`

Enabling, disabling and changing the wanted history depth are edits to a mutable
entity, so the table soft-versions rather than updating in place — consistent with
`TRADE.DEPLOYMENT` and with the convention that `UPDATED_AT` is *not* added for
`IS_CURRENT_IND` flips. It also buys something real: a record of which series the
platform was capturing when, which is part of reproducing a backtest.

### 3.4 DDL sketch

```sql
CREATE TABLE MARKET_DATA.BAR_SUBSCRIPTION (
    BAR_SUBSCRIPTION_ID   UUID          NOT NULL,   -- uuid7, stable across versions
    BAR_SUBSCRIPTION_VID  INTEGER       NOT NULL,
    APP_USER_ID           UUID          NOT NULL,   -- who asked
    INTERNAL_CUSIP        TEXT          NOT NULL,   -- INST.PRODUCT
    TM_INTERVAL_ID        INTEGER       NOT NULL,   -- REFDATA.TM_INTERVAL
    SOURCE_APP_ID         INTEGER       NOT NULL,   -- REFDATA.APP, IS_EXCHANGE_IND = 'Y'
    IS_ENABLED_IND        CHAR(1)       NOT NULL,
    BACKFILL_FROM_TS      TIMESTAMPTZ,              -- history wanted; NULL = forward only
    TRANSACT_FROM_TS      TIMESTAMPTZ   NOT NULL,
    TRANSACT_TO_TS        TIMESTAMPTZ   NOT NULL,
    USER_ID               TEXT          NOT NULL,
    CREATED_AT            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    PRIMARY KEY (BAR_SUBSCRIPTION_ID, BAR_SUBSCRIPTION_VID)
);
```

`BACKFILL_FROM_TS` is **intent, not progress** — how far back the user wants
history, so the UI can show a target and offer to fill toward it. The fill itself
stays an explicit, reported operation (§5); a column that tracked progress would
imply a background crawler this design does not propose.

Procedures, mirroring the TRADE side:

| Procedure | Purpose |
|---|---|
| `MARKET_DATA.SP_INS_BAR_SUBSCRIPTION` | Append a version — create, enable, disable, retarget |
| `MARKET_DATA.SP_GET_BAR_SUBSCRIPTION` | One user's current rows, for the UI |
| `MARKET_DATA.SP_GET_ACTIVE_BAR_SUBSCRIPTIONS` | `DISTINCT (TM_INTERVAL_ID, INTERNAL_CUSIP, SOURCE_APP_ID)` across all users, for the warmer |

### 3.5 Subscriptions are not implied by deployments

Scheduling a deployment does **not** create a subscription row, and the two are
unioned rather than kept in step. The alternative — auto-subscribing on deploy —
forces a bad question on every stop: was that subscription the deployment's, or
did the user also want the data? Independence means stopping a deployment removes
its instruments from the warm by construction, exactly as it does today, while an
explicit subscription survives on its own terms.

## 4. Who warms it — and where that code should live

The warmer's instrument list becomes `deployments ∪ subscriptions`. Both sides
already produce the same triple, so the union is a concatenation and a `DISTINCT`.
The real question is *which package owns the loop*.

[§7.8](scheduler-price-bars.md#78-scheduled-bar-warming-quanttradeschedulerwarmpy)
puts `BarWarmer` in `quant/trade/` with an explicit justification: *"the question
it answers — which instruments matter — is a deployment question."* **This feature
is what stops that being true.** After it, that question is a market-data question
with a trading input.

| Option | Shape | Trade-off |
|---|---|---|
| **A — minimal** | `BarWarmer` stays in `quant/trade/scheduler/warm.py`, gains a subscription repo | Smallest diff; but a research feature's warm loop lives in the trading package, and `quant/trade/` acquires a reason to exist for users who never trade |
| **B — invert (recommended)** | `BarWarmer` moves to `quant/market_data/warm.py` and takes a list of `InstrumentSource`; `quant/trade/` supplies the deployment-derived one | Ownership matches the domain, and the one-way rule gets *stronger* — `quant/market_data/` still knows nothing about deployments, only a protocol |

```python
class InstrumentSource(Protocol):
    """Rows of (tm_interval_id, internal_cusip, source_app_id)."""
    def instruments(self) -> list[dict]: ...
```

B is a **move, not a rewrite**: the grouping, the settle, the per-group `except`
and `WarmResult` are unchanged; only where the rows come from moves behind the
protocol. `DeploymentInstrumentSource` wraps `TradeRepo`,
`SubscriptionInstrumentSource` wraps the new repo, and the FastAPI lifespan wires
both — the composition root already builds `app.state.price_bars`. The route stays
`POST /api/v1/market-data/price-bars/sync`, which is *already* under `market-data`
despite the handler living in `quant/trade/` — a mismatch this resolves.

One schedule still serves everything. `price_bar_sync` sweeps whatever intervals
the rows mention, so a subscription on `1H` for research while trading `DAILY`
needs no new schedule, and an interval nobody uses contributes no rows.

**Cost is not proportional to the lookback.** `DEFAULT_WARM_LOOKBACK` is
`live_lookback_bars(110)`, but `ensure_fresh` fetches only *missing* bars, so a
subscription in steady state costs one bar per instrument per tick. The generous
lookback is what repairs a gap after downtime, not a per-tick price.

## 5. Backfill — explicit, and it reports

`PriceBarService.backfill(internal_cusip, tm_interval_id, source_app_id, start, end)`
exists, is tested, and is reachable from **no route and no CLI**. Exposing it is
most of the historical half of this feature.

It deliberately **does not fail closed**, inverting the rule the rest of the
module follows ([decision #48](../decisions.md)). On the trade path a hole must
stop the run; during a repair a hole is ordinary — the range may predate the
listing, or reach past what the venue retains — and aborting would discard the
bars that *were* recoverable. `BackfillResult.unfilled` names what could not be
filled and `is_continuous` is the check a backtest should make.

Depth is bounded by the venue, not by us: ccxt `fetch_ohlcv` retention varies by
exchange and timeframe, and deep intraday history is often unavailable at any
price. A paid provider under its own `SOURCE_APP_ID` remains the answer where the
exchange cannot reach far enough — which is what #47's wide key already permits.

**This is the honest limit of the feature.** Subscribing today does not
retroactively create history; it starts a series and lets you fill backward as
far as the venue will serve.

## 6. Coverage — answering "can I backtest this yet?"

The question the UI must answer is not "am I subscribed" but "do I have enough
continuous history". Two reads already exist:
`SP_GET_PRICE_BAR_COVERAGE` (`MIN`/`MAX`, two index probes) and `find_gaps`
(read-only, no exchange call). Surfacing first bar, last bar and gap count per
subscription is what turns capture from an act of faith into something checkable
before a backtest is trusted.

## 7. The backtest seam

Backtest reads the provider, not `PRICE_BAR`. `_build_data_dict` calls
`fetch_df(symbol, start, end, data_source, …)` per symbol, where `data_source`
names a `REFDATA.APP` row and `class_name` selects the vendor client.

The seam is already there, and it is `data_source`. **Bybit is an app in
`REFDATA.APP`** with `IS_EXCHANGE_IND = 'Y'`. So when `data_source` names an
exchange that ccxt can serve — resolvable via `registry.exchange_id_for_app` —
route that symbol through `PriceBarService.read_bars` instead of a vendor client.
No parallel switch, no new request field to choose a "mode": picking Bybit as the
data source *is* pinning `SOURCE_APP_ID`, which is what #47 requires of a
reproducible backtest.

Two consequences worth stating:

- **An interval becomes explicit.** `read_bars` needs `tm_interval_id`;
  `BacktestCache.DEFAULT_TM_INTERVAL_ID = 1` hardcodes daily by convention today.
  An optional interval on the backtest request, defaulting to daily, preserves
  every existing run and opens the intraday backtests
  [§4.6](scheduler-price-bars.md#46-backtest-compatibility-same-dataframe-contract)
  anticipated.
- **`_enforce_date_sync` becomes load-bearing.** It already refuses when products
  and factors do not share coverage. Against a rolling-window table with possible
  holes that guard is doing more work than it was written for, and it is the right
  place for it — complemented by `is_continuous` before trusting a range.

`read_bars` returns the exact DataFrame shape the pipeline consumes
(index, `price`, `factor`, `Open/High/Low/Close/Volume`), so `Performance` and the
indicator math need no changes.

**Factors are the sharp edge.** `bars_loader` on the live path routes *every*
symbol to the exchange, including factors naming their own `data_source`, because
mixing an exchange series with a provider series aligns bars never observed on the
same clock. Backtest is more permissive by nature — a crypto strategy filtered on
`^VIX` is a legitimate research question and no exchange serves `^VIX`. This
design does **not** resolve that; see §9.

## 8. API and auth

| Route | Purpose |
|---|---|
| `GET /api/v1/market-data/subscriptions` | Caller's subscriptions + coverage |
| `POST /api/v1/market-data/subscriptions` | Create / enable / disable / retarget |
| `POST /api/v1/market-data/price-bars/backfill` | Explicit range fill, returns `BackfillResult` |
| `GET /api/v1/market-data/price-bars/coverage` | `MIN`/`MAX` + gaps for one series |

The `market_data` router is gated at **router level** with
`require_user_or_service` so the Lambda can drive `price-bars/sync`
([§6.4](scheduler-price-bars.md#64-service-auth-implemented)). These are human
actions, so each adds `require_user` itself — the documented pattern for that
router, and the reason the router-level gate is a floor rather than a ceiling. A
service token must not be able to subscribe or backfill: both spend exchange rate
limit on behalf of a user who did not ask.

**Validate at subscribe time, not at warm time.** A subscription is only
warmable if the product exists in `INST.PRODUCT`, an `INST.PRODUCT_XREF` row maps
it to a vendor symbol for that app, and the app resolves to a ccxt venue.
Checking on write turns three silent per-tick failures into one immediate error.

## 9. Open questions

| Question | Why it decides something |
|---|---|
| Do factors follow the main product's source, or keep their own? | §7's sharp edge. Same-venue-or-nothing is right for live, wrong for a `^VIX`-filtered crypto backtest |
| Should a subscription cap retention? | `PRICE_BAR` is append-only immutable facts and [§4.3](scheduler-price-bars.md#43-volume-projections) makes volume trivial (~52 MB for 10 products × 5 years), so probably not — but nothing prunes today |
| Is `BACKFILL_FROM_TS` worth storing before a filler consumes it? | It is intent with no reader in v1; the counter-argument is §6's UI needs a target to display |
| Does anything auto-backfill on subscribe? | A synchronous fill blocks the request; a background one needs progress tracking this design avoids |
| Who may subscribe? | Rate limit is a shared resource. Unbounded per-user subscriptions are a cost and a throttling risk |

## 10. What this amends

Nothing is added to the [decisions log](../decisions.md) yet — the decision is not
made. When agreed, it amends **decision #5** (bar population follows deployments)
and extends **#44** (`market_data/` owns MARKET_DATA end-to-end) to cover the warm
loop if §4 option B is taken. It leaves **#47** and **#48** intact and leans on
both: the per-venue key is what lets a subscription mean one series, and explicit
backfill is already the sanctioned continuity repair.

## 11. Implementation order

1. **DDL** — `MARKET_DATA.BAR_SUBSCRIPTION` + three procedures.
2. **Python** — subscription repo; `InstrumentSource` protocol; warmer union (§4).
3. **API** — subscription CRUD, backfill and coverage routes, `require_user`.
4. **UI** — a Market data page: product / interval / venue pickers from REFDATA
   and `INST.PRODUCT`, coverage per row, and an explicit backfill action. This is
   the part that was looked for and not found.
5. **Backtest seam** — exchange `data_source` → `read_bars`, optional interval on
   the request.
6. **Tests** — repo, warmer union, backfill reporting, and a backtest run pinned
   to a `SOURCE_APP_ID`.

Steps 1–4 deliver capture on their own. Step 5 is what makes the captured bars
usable for the decision that motivated capturing them, and until it lands the
bars accumulate correctly but backtest still reads the provider.
