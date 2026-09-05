# Market data capture — bars for products you don't trade

**Status: built.** All of §11 is committed — `MARKET_DATA.BAR_SUBSCRIPTION` and
its three procedures, the subscription repo and `InstrumentSource` union, the API
routes, the Market data page, and the backtest seam (§7) that makes the captured
bars usable for the decision that motivated capturing them. Recorded as
[decision #50](../decisions.md) and [#51](../decisions.md).

The DDL is **staged, not released**: `1.3.0-bar-subscription.xml` carries
`context="market_data"` without `prod-deploy`, so a push to `main` does not
queue it for the production migrate job.

One decision here was **reversed during implementation**: subscriptions are
platform-wide rather than per user. §3.2 records both sides and which won.

**Parent:** [Scheduler & Price Bars](scheduler-price-bars.md) §3.2
**Related:** [Separate Underlying & Cache](separate-underlying.md), [Backtest API](../archive/backtest-api.md), [Alternative Data Sources](alt-data-sources.md)

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

### 3.2 One row per series — a subscription has no owner

**Reversed from the original proposal.** This section first argued for one row
per user, so that unsubscribing would remove only your own request:

| Model | Consequence |
|---|---|
| ~~One row per user, warmer reads `DISTINCT`~~ | Unsubscribing removes only your request; the series stays warm while anyone wants it |
| **One platform-wide row, no owner column** | Disabling stops the capture for everyone |

The per-user model was rejected because it answers a question the domain does
not ask. A bar is a **shared fact** — one row per `(cusip, interval, venue,
timestamp)`, readable by everybody — so a per-user request row models private
ownership of something nobody owns. It is not analogous to `DEPLOYMENT`, whose
`APP_USER_ID` isolation ([decision #42](../decisions.md)) exists because a
deployment spends *your* money through *your* credential. Capture spends
neither.

What the per-user model bought was a `DISTINCT` and the ability to withdraw
privately; what it cost was a second copy of every popular series and a list
that shows you only your own corner of a shared resource.

So: `UQ_BAR_SUBSCRIPTION_OPEN` allows exactly one open row per series, and
`SP_GET_ACTIVE_BAR_SUBSCRIPTIONS` needs no `DISTINCT` because the index already
guarantees it.

The table carries **no `USER_ID`** either, a deliberate exception to the audit
convention every other table follows. `SP_INS_BAR_SUBSCRIPTION` still takes
`IN_USER_ID` and hands it to `CORE_ADMIN.CORE_INS_LOG_PROC`, so who enabled,
disabled or retargeted a series is answerable from `CORE_ADMIN.LOG_PROC_DETAIL`
against the version window this table already stamps. A copy on the row would be
a second record of one fact, free to disagree with the log, and nothing in the
API or UI ever read it.

**The cost is real and accepted.** Disabling a subscription cools the series
for every user, and the bars missed while it was paused are recoverable only as
far back as the venue still retains them. That is exactly why the list is
unscoped and the row is visible to everyone: you cannot reason about whether to
pause a capture you cannot see. The UI confirms a pause and says who it affects.

### 3.3 Soft-versioned, like `DEPLOYMENT`

Enabling, disabling and changing the wanted history depth are edits to a mutable
entity, so the table soft-versions rather than updating in place — consistent with
`TRADE.DEPLOYMENT` and with the convention that `UPDATED_AT` is *not* added for
`IS_CURRENT_IND` flips. It also buys something real: a record of which series the
platform was capturing when, which is part of reproducing a backtest.

### 3.4 DDL sketch

As built (`db/liquidbase/market_data/tables/BAR_SUBSCRIPTION.sql`):

```sql
CREATE TABLE MARKET_DATA.BAR_SUBSCRIPTION (
    BAR_SUBSCRIPTION_ID   UUID          NOT NULL,   -- stable across versions
    BAR_SUBSCRIPTION_VID  INTEGER       NOT NULL,
    INTERNAL_CUSIP        TEXT          NOT NULL,   -- INST.PRODUCT
    TM_INTERVAL_ID        INTEGER       NOT NULL,   -- REFDATA.TM_INTERVAL
    SOURCE_APP_ID         INTEGER       NOT NULL,   -- REFDATA.APP, IS_EXCHANGE_IND = 'Y'
    IS_ENABLED_IND        CHAR(1)       NOT NULL,
    BACKFILL_FROM_TS      TIMESTAMPTZ,              -- history wanted; NULL = forward only
    TRANSACT_FROM_TS      TIMESTAMPTZ   NOT NULL,
    TRANSACT_TO_TS        TIMESTAMPTZ   NOT NULL,
    CREATED_AT            TIMESTAMPTZ   NOT NULL,

    PRIMARY KEY (BAR_SUBSCRIPTION_ID, BAR_SUBSCRIPTION_VID)
);

-- One live subscription per series. This is what makes the warmer's read a
-- plain scan rather than a DISTINCT: the index is the uniqueness.
CREATE UNIQUE INDEX UQ_BAR_SUBSCRIPTION_OPEN
    ON MARKET_DATA.BAR_SUBSCRIPTION (TM_INTERVAL_ID, INTERNAL_CUSIP, SOURCE_APP_ID)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';
```

`BACKFILL_FROM_TS` is **intent, not progress** — how far back the user wants
history, so the UI can show a target and offer to fill toward it. The fill itself
stays an explicit, reported operation (§5); a column that tracked progress would
imply a background crawler this design does not propose.

Procedures, mirroring the TRADE side:

| Procedure | Purpose |
|---|---|
| `MARKET_DATA.SP_INS_BAR_SUBSCRIPTION` | Append a version — create, enable, disable, retarget |
| `MARKET_DATA.SP_GET_BAR_SUBSCRIPTION` | Current rows, for the UI. Disabled rows included — their absence would read as "deleted" |
| `MARKET_DATA.SP_GET_ACTIVE_BAR_SUBSCRIPTIONS` | Enabled `(TM_INTERVAL_ID, INTERNAL_CUSIP, APP_ID)`, for the warmer. No `DISTINCT` — the unique index already guarantees it, unlike the deployment-side read where a dozen deployments can name one instrument |

Coverage is deliberately **not** joined into the list read: it is a
`MARKET_DATA.PRICE_BAR` question, answered per row by
`SP_GET_PRICE_BAR_COVERAGE` (two index probes), and folding an aggregate over
the bar table into the list would turn a cheap read into a scan.

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

[§7.8](scheduler-price-bars.md#78-scheduled-bar-warming-quantmarket_datawarmpy)
puts `BarWarmer` in `quant/trade/` with an explicit justification: *"the question
it answers — which instruments matter — is a deployment question."* **This feature
is what stops that being true.** After it, that question is a market-data question
with a trading input.

| Option | Shape | Trade-off |
|---|---|---|
| **A — minimal** | `BarWarmer` stays in `quant/trade/scheduler/warm.py`, gains a subscription repo | Smallest diff; but a research feature's warm loop lives in the trading package, and `quant/trade/` acquires a reason to exist for users who never trade |
| **B — invert (taken)** | `BarWarmer` moves to `quant/market_data/warm.py` and takes a list of `InstrumentSource`; `quant/trade/` supplies the deployment-derived one | Ownership matches the domain, and the one-way rule gets *stronger* — `quant/market_data/` still knows nothing about deployments, only a protocol |

```python
class InstrumentSource(Protocol):
    """Rows of (tm_interval_id, internal_cusip, app_id)."""
    def instruments(self) -> list[dict]: ...
```

B was a **move, not a rewrite**: the grouping, the settle, the per-group
`except` and `WarmResult` are unchanged; only where the rows come from moved
behind the protocol. `DeploymentInstrumentSource` (in `quant/trade/bar_source.py`,
the module that already composes trade and market data) wraps `TradeRepo`;
`SubscriptionInstrumentSource` wraps the new repo; the route handler wires both.
The route stays `POST /api/v1/market-data/price-bars/sync`, which was *already*
under `market-data` despite the handler living in `quant/trade/` — a mismatch
this resolves.

Two details the move forced, both small and both in the same direction:

- **The factory is a protocol too.** `BarWarmer` used to take
  `PriceBarServiceFactory`, which lives in `quant/trade/`. Importing it from
  `quant/market_data/warm.py` would have re-created the dependency the move
  removed, so `BarServiceFactory` is declared as a `Protocol` beside
  `PriceBarService` — the same trick `BarFetcher` already uses.
- **A failing source is not absorbed.** The broad `except` covers a failing
  *venue*, which is weather. A source that cannot be read is a missing procedure
  or a broken connection — a bug, and warming a partial estate while reporting
  success would hide it.

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

### 5.1 The venue's floor, not a date somebody typed

The first version asked the user how far back they wanted history, as a free
date field. That reliably produced targets the venue could never meet — a
`btcusdt.crypto` subscription asking for 2017-01-01 when Bybit's first daily
`BTCUSDT` bar is **2020-03-25**. The row then reported a permanent shortfall
against history that was never obtainable, which is indistinguishable on the
page from a gap a backfill could close.

The exchange knows the answer, so it is asked: `CcxtBarFetcher.earliest_bar`
reads the oldest bar a venue still serves, and `PriceBarService.venue_depth`
pairs it with how many bars that is at the requested interval. Both dialogs
default to it. `MARKET_DATA.BAR_SUBSCRIPTION.BACKFILL_FROM_TS` still stores a
target, but it is now the venue's floor unless someone deliberately narrows it.

Reading it takes two steps, and the one-step version silently lies. `since=0`
does not mean "from the beginning" — it is falsy, so ccxt sends no start and
Bybit answers with the *newest* page, reporting that a six-year-old series began
this morning. So the request anchors on the listing time ccxt normalises into
`market['created']` and lets the venue clamp forward. The listing time is only
an anchor, never the answer: Bybit lists `BTCUSDT` on 2020-03-15 and prints its
first daily bar ten days later. Retention also differs per timeframe, so it is
read per `(symbol, period)` rather than cached per venue.

A venue that publishes no listing time returns **unknown**, and the dialog asks
for a date as before. The tempting alternative — anchor on some fixed instant
predating every exchange — was rejected: a guessed floor is worse than an absent
one, because it arrives wearing the same authority as a real answer, and the
whole point here is that the date stops being a guess.

### 5.2 There is no "to", and there is a ceiling

Backfill takes no end date. It always ran to the last closed bar — a forming bar
cannot be stored and nothing beyond it exists to fetch — so the field only
invented a decision that had one correct answer.

The start is bounded instead, by `MAX_BACKFILL_BARS` (10,000). Backfill is one
synchronous blocking request that writes a row per bar through
`SP_INS_PRICE_BAR`, measured at **~200 bar/s** against a local database and
slower against Aurora. The ceiling is therefore a time budget in disguise:
roughly 50s locally against the ~100s a proxy allows before abandoning the
request. Cost scales with the interval, not the calendar — the same Bybit
history is ~2,300 daily bars, ~56,000 hourly and ~3.4 million 1-minute:

| Interval | Bars in full Bybit `BTCUSDT` history | One pass? |
|---|---|---|
| Daily | ~2,300 | yes, with room to spare |
| Hourly | ~56,000 | no — about six passes |
| 1-minute | ~3,400,000 | no, and not by this mechanism |

Oversized ranges are refused **before** `find_gaps` materialises one entry per
boundary, by arithmetic on the span — a guard that exhausts memory reaching its
own refusal is not a guard. Raising the ceiling does not make a minute-scale
fill work; that needs a background job with progress tracking, which
[§9](#9-open-questions) deliberately rejects.

### 5.3 A pass ends where coverage begins

The "about six passes" in the table above was, for a while, a fiction. The
refusal told you to fill a nearer date and repeat, and repeating could not work:
**every fill ran to the last closed bar**, so the range always included whatever
was already stored. An hourly series holding a year has no start that both
reaches further back and stays under 10,000 — 2020 is ~56,000 bars, and even a
start six months back is ~12,000, most of them bars already held. The span is
counted either way. Deep intraday history was not slow; it was unreachable, and
the message pointed at a door that was not there.

The fix is direction. A pass now ends at **the bar before coverage begins**
rather than at the last close, so it spans only bars that are absent, and the
next pass resumes from the ground the last one gained:

```
target                    coverage
  ▼                          ▼
  ├─── pass 3 ─┼─ pass 2 ─┼─ pass 1 ─┤████████ stored ████████┤
                                      ▲
                                 first stored bar
```

`PriceBarService.plan_backfill` computes that window — two index probes and
arithmetic, no exchange call — and reports the bar count and passes remaining,
so the commitment is visible before the first click. A series with nothing
stored anchors on the last closed bar rather than on the target, so the first
pass returns bars a strategy can already use; walking forward from history
instead would leave the series worthless until the final pass.

The looping is still the user's. Doing it server-side would be the background
filler under another name — the same progress tracking, just hidden inside a
request — so a pass is a click, and each one reports exactly what arrived. What
the ceiling now bounds is *one pass*, not the history obtainable.

## 6. Coverage — answering "can I backtest this yet?"

The question the UI must answer is not "am I subscribed" but "do I have enough
continuous history". Two reads already exist:
`SP_GET_PRICE_BAR_COVERAGE` (`MIN`/`MAX`, two index probes) and `find_gaps`
(read-only, no exchange call). Surfacing first bar, last bar and gap count per
subscription is what turns capture from an act of faith into something checkable
before a backtest is trusted.

### 6.1 Two lists, not one list with a status column

Paused series are listed **separately** from capturing ones rather than sharing
a table with a status chip. "What is accruing right now" is the operational
question the page exists to answer, and a mixed table dilutes it — the reader
filters by eye on every visit, and a paused row looks identical to an active one
until you read the chip. Splitting also gives the dormant set somewhere to say
what being dormant costs: bars missed while paused are recoverable only as far
back as the venue still retains them.

The paused section is hidden entirely when nothing is paused, so the common case
is one list.

### 6.1a "Continuous" is not "finished"

The green *continuous* chip means only that there are no holes **inside** what is
stored. It says nothing about reaching the target, and the two are easy to
confuse when they sit in adjacent columns: a daily series complete back to the
venue's first bar and an hourly series one year into a six-year target both
rendered the same green, and the only colour on either row said success.

So a row short of its target now says by how much, in days. Days rather than
bars because a bar count needs the interval's period, and fetching that per row
to label a table is a cost the backfill dialog already pays once — where it can
also say how many passes remain, which is the more useful form of the same fact.

A target the venue can never meet is a different failure and is prevented at the
source ([§5.1](#51-the-venues-floor-not-a-date-somebody-typed)): rows created
before that defaulted to whatever was typed, and one asking for 2017-01-01 on a
pair listed in 2020 would now show a permanent shortfall against history that
never existed. Such rows are retargeted to the venue floor rather than being
special-cased in the display.

So the chip has three states rather than two. A series whose first bar has
reached its target is **completed** — the target is the venue's floor, so
reaching it means there is nothing older to fetch and the capture is finished,
not merely hole-free. Short of the target it stays *continuous*, which is the
honest reading: no holes inside what is stored, and still accruing. A row with
no target at all stays *continuous* too, since absent intent must not be read
as success.

Both facts are already on the row — `BACKFILL_FROM_TS` and
`coverage.first_bar` — so this is a comparison the page makes, not a field the
API gained. That matters for the case that prompted it: Bybit's first hourly
`BTCUSDT` bar is `2020-03-25 10:00`, ten bars after midnight, and those ten
will never arrive. Reading that series as unfinished invites a backfill that
can only fail.

### 6.2 The vendor symbol belongs on the row

Each row carries the ticker the **venue** prints — `BTCUSDT` — beside the
internal CUSIP it is stored under. An internal identifier cannot be checked
against anything: you cannot look up `btcusdt.crypto` on an exchange, so a row
showing only that is unverifiable by the person who has to decide whether the
right series is being captured. This is the same complaint that opened #51,
where a deployment dialog showed a Yahoo symbol beside a Bybit account.

It is resolved through the same `InstrumentCache` the fetcher uses, so the page
cannot disagree with what actually gets requested — a lookup, not a query, and
no change to `SP_GET_BAR_SUBSCRIPTION`. A withdrawn `INST.PRODUCT_XREF` row
renders as **not listed on this venue** rather than blanking: capture is broken
at that point, and the list is exactly where somebody would look to find out
why.

Search filters on **either** identifier, because nobody reliably remembers which
of the two they know.

### 6.3 The venue chooses the products, not the other way round

The capture dialog asked for a product first, from a dropdown holding every
instrument the platform knows. With Bybit as the venue that list is mostly
Nasdaq and NYSE Arca tickers — `ibit.nasdaq`, `fbtc.cboebzx` — none of which
Bybit has ever listed. Picking one could only produce a subscription that never
captures a bar, because capture resolves the product through
`INST.PRODUCT_XREF` to reach the venue at all.

Making it a search box helped and did not fix it: a set that large is still not
one anyone should have to filter, and typing `btc` still surfaces a dozen ETFs
before the perpetual. The list was simply the wrong list.

So **venue is now the first field**, and the product options are what that venue
lists — served by `GET /api/v1/inst/apps/{app_id}/products` from the in-memory
`InstrumentCache`, since listing is precisely what `PRODUCT_XREF` records.
Bybit's handful of pairs needs no scrolling at all, and the search became a
convenience rather than a necessity. Changing venue clears the chosen product,
because the same product is not listed everywhere.

Each option carries the vendor symbol as well as the CUSIP, and the search
matches any of the three, so the ticker from the exchange's own screen is a
valid way in. The field is disabled until a venue is chosen and says how many
products that venue lists, so "no options" after typing reads as a search miss
rather than a broken form.

Scoping the list to the venue left one dead end, which is now closed. A venue
with no xrefs lists nothing, and the empty state said *"add an `INST.PRODUCT_XREF`
row for it"* — an instruction to open a SQL client against production, from
inside the page whose whole point was that capture no longer required one. The
Market data page now has an **Add an instrument** action beside *Capture a
series*, and the empty state points at it. It writes the `INST.PRODUCT` row and
its first `INST.PRODUCT_XREF` row in one submit, because a product without an
xref is invisible to this very dropdown — see decision #62 and
[Creating an instrument](../architecture/database.md#creating-an-instrument).

## 7. The backtest seam (built)

Backtest used to read the provider and only the provider. `_build_data_dict`
calls `fetch_df(symbol, start, end, data_source, …)` per symbol, where
`data_source` names a `REFDATA.APP` row and `class_name` selects the vendor
client — and for an exchange row there is no such class, so choosing Bybit in
the dropdown raised `AttributeError: module 'quant.data.sources' has no
attribute 'Bybit'`. The venue you traded on was the one venue you could not fit
on.

The seam was already there, and it is `data_source`. **Bybit is an app in
`REFDATA.APP`** with `IS_EXCHANGE_IND = 'Y'`, so `fetch_df` now branches on that
flag and reads `PriceBarService.read_bars` instead of instantiating a vendor
client. No parallel switch and no new request field to choose a "mode": picking
Bybit as the data source *is* pinning `SOURCE_APP_ID`, which is what #47
requires of a reproducible backtest.

`read_bars` returns the exact DataFrame shape the pipeline consumes (index,
`price`, `factor`, `Open/High/Low/Close/Volume`), so `Performance` and the
indicator math needed no changes at all.

Four things follow, and each is a decision rather than a detail:

- **The bar cache is bypassed on this path.** `PRICE_BAR` *is* the store.
  Copying it into `BT.API_REQUEST` would create a second version of the same
  fact, free to diverge from the first.
- **It refuses rather than substitutes.** A range the store cannot cover is an
  error naming the range it *can* — never a shorter series quietly returned
  under the requested label. Nor does a backtest trigger a fetch: capture is a
  standing decision made on the Market data page (§5), not a side effect of
  pressing Run, so a five-year request never becomes a five-year exchange crawl
  on someone's behalf.
- **The interval comes from the request, not from this module.** `read_bars`
  needs a `tm_interval_id` and `OptimizeRequest.tm_interval_id` supplies it,
  required for the same reason `data_source` is: it names an input series, and
  a default picks one on the caller's behalf silently. It was briefly a
  `BACKTEST_BAR_PERIOD` constant resolved through REFDATA on every run, which
  made intraday backtests
  ([§4.6](scheduler-price-bars.md#46-backtest-compatibility-same-dataframe-contract))
  impossible and left captured hourly bars unreachable. The forming-bar slack
  is now one bar *of that interval* — as a fixed day it would have excused a
  24-bar hole at the tail of an hourly series.
- **`_enforce_date_sync` becomes load-bearing.** It already refuses when products
  and factors do not share coverage. Against a rolling-window table with possible
  holes that guard is doing more work than it was written for, and it is the right
  place for it — complemented by `is_continuous` before trusting a range.

**Factors keep their own source** — the §9 question, now closed. `_build_data_dict`
already reads `f.data_source or req.data_source`, so a factor may name a provider
while the traded product names a venue. Only the *traded* product has to follow
the venue it executes on; a `^VIX` filter on a crypto strategy is a legitimate
research question and no exchange serves `^VIX`. Inheriting an exchange source is
therefore allowed but explained: a factor with no `INST.PRODUCT_XREF` row on that
venue is refused with the instruction to give it its own source, rather than the
bare "not captured" the traded product gets.

This is deliberately *looser* than live, where `bar_loader` routes every symbol to
the exchange. The asymmetry is intentional: mixing series is a research choice
worth making knowingly, and a fatal one to make silently with capital at risk.

### 7.1 Dry run reads what the apply reads

Same class of bug, opposite corner. The dry run called
`compute_latest_position` **without** a `bar_loader` while the live apply passed
one, so the preview a user checked before going live was computed from the
provider and the order that followed was computed from the exchange. Near a band
edge that is a preview reporting HOLD and an apply placing a BUY, with neither
malfunctioning and nothing in either output to show why.

`LiveApplyOrchestrator._resolve_signal_source` was the only place the venue rule
lived, so it moved to `bar_source.resolve_signal_source` and both callers use it.
A dry run predates its schedule, so it passes `schedule_tm_interval_id=None` and
falls through to daily — the only cadence a deployment may run on anyway.

`DryRunReport.bar_source` carries the label to the UI, next to `ApplyReport`'s,
for the same reason: two sources are two sets of numbers, and a divergence is
diagnosable only when the input is recorded beside the output.

## 8. API and auth

| Route | Purpose |
|---|---|
| `GET /api/v1/market-data/subscriptions` | Every subscription + coverage (not caller-scoped — §3.2) |
| `POST /api/v1/market-data/subscriptions` | Create / enable / disable / retarget. **200, not 201** — only one of those creates anything |
| `POST /api/v1/market-data/price-bars/backfill` | Fill from a start to the last closed bar, returns `BackfillResult` |
| `GET /api/v1/market-data/price-bars/coverage` | `MIN`/`MAX` + gaps for one series — what we *hold* |
| `GET /api/v1/market-data/price-bars/venue-depth` | Earliest bar the venue serves + bar count + fill ceiling — what *exists* ([§5.1](#51-the-venues-floor-not-a-date-somebody-typed)) |

`coverage` and `venue-depth` are separate routes because they are different
questions with different costs: coverage is two index probes, `venue-depth` asks
the exchange. That is also why the list endpoint carries coverage per row but
never depth — one network call per row to render a table is not a trade worth
making. The dialogs ask for depth on demand, once a whole series is identified.

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
`SubscriptionError` carries that to **400** and is logged server-side like every
other handled error.

Two failure modes are deliberately *not* symmetric. Subscribing to a series that
already exists is a 400 that names the series, because the unique index caught
it and the caller should edit that row — which, subscriptions being shared, may
be somebody else's. But a venue that cannot answer a **coverage** read degrades
one row instead of failing the list: a page showing ten series must still render
when one exchange is away, so the row reports `coverage.error` and the rest
display.

## 9. Open questions

| Question | Status |
|---|---|
| Do factors follow the main product's source, or keep their own? | **Closed — their own** (§7). Same-venue-or-nothing stays right for live and stays wrong for a `^VIX`-filtered crypto backtest, so the two paths differ on purpose. A factor inheriting a venue it is not listed on is refused with the instruction to name its own source |
| Should a subscription cap retention? | **Open, deferred.** `PRICE_BAR` is append-only immutable facts and [§4.3](scheduler-price-bars.md#43-volume-projections) makes volume trivial (~52 MB for 10 products × 5 years), so nothing prunes today |
| Is `BACKFILL_FROM_TS` worth storing before a filler consumes it? | **Kept.** §6's page needs a target to display. It is no longer typed, though: [§5.1](#51-the-venues-floor-not-a-date-somebody-typed) defaults it to the venue's own earliest bar |
| Does anything auto-backfill on subscribe? | **No.** A synchronous fill blocks the request; a background one needs progress tracking this design avoids. Subscribing makes the series eligible for the next warm pass, and nothing more |
| Should a fill too large for one pass be chunked automatically? | **No** — refused instead ([§5.2](#52-there-is-no-to-and-there-is-a-ceiling)). Chunking is the background filler under another name, and needs the same progress tracking. The refusal names a range that fits, and each pass keeps what it stored, so repeating is safe |
| How would intraday capture ever work, then? | **Open, deferred — and not by raising `MAX_BACKFILL_BARS`.** A request/response API writing a row per bar is the wrong shape for millions of them at any ceiling. Minute-scale capture is a streaming problem: a pipeline (Kafka for transport, Spark for batch load) rather than a bigger blocking call. Nothing here should be built as a half-step toward it — the current design is honest about serving daily, and the refusal is what keeps that honest |
| Who may subscribe? | **Any signed-in user**, unbounded. Rate limit is a shared resource and this is a throttling risk that nothing currently caps — revisit if the subscription list grows past a handful. A service token may *not* subscribe (§8) |

## 10. What this amends

Recorded as [decision #50](../decisions.md). It amends **decision #5** (bar
population follows deployments) and extends **#44** (`market_data/` owns
MARKET_DATA end-to-end) to cover the warm loop, §4 option B having been taken.
It leaves **#47** and **#48** intact and leans on both: the per-venue key is what
lets a subscription mean one series, and explicit backfill is already the
sanctioned continuity repair.

## 11. Implementation order

| Step | State |
|---|---|
| 1. **DDL** — `MARKET_DATA.BAR_SUBSCRIPTION` + three procedures | **Done and released** — `1.3.0-bar-subscription.xml`, `context="market_data,prod-deploy"` |
| 2. **Python** — subscription repo; `InstrumentSource` protocol; warmer union (§4) | **Done** — `quant/market_data/subscriptions.py`, `quant/market_data/warm.py` |
| 3. **API** — subscription CRUD, backfill and coverage routes, `require_user` | **Done** — `quant/api/market_data/router.py` |
| 4. **UI** — a Market data page: product / interval / venue pickers from REFDATA and `INST.PRODUCT`, coverage per row, and an explicit backfill action | **Done** — `frontend/src/pages/MarketDataPage.tsx`. This is the part that was looked for and not found |
| 5. **Backtest seam** — exchange `data_source` → `read_bars` | **Done** — `fetch_df` branches on `IS_EXCHANGE_IND`; §9's factor question closed. An optional interval on the request is still open, and daily is resolved from REFDATA meanwhile |
| 6. **Tests** — repo, warmer union, backfill reporting, and a backtest run pinned to a `SOURCE_APP_ID` | **Done** — `tests/unit/test_backtest_exchange_source.py` covers the pinned run and the four refusals |

Steps 1–4 deliver capture on their own. Step 5 is what makes the captured bars
usable for the decision that motivated capturing them: a strategy can now be
fitted on the series it will be traded on, and §7.1 makes the dry run preview
that same series.
