# FastAPI Backend

The `quant/api/` directory contains the FastAPI application for backtest, trade, and shared REFDATA endpoints. All `/api/v1/*` routes (except auth and health) require an authenticated session; the **admin**, **market-data**, and **scheduler** routers additionally accept the scheduler Lambda's service bearer token (`require_user_or_service`).

See [System Overview](overview.md) for the full stack.

!!! note "Queue endpoints"
    `/api/v1/backtest/jobs/*` (the backtest queue) is served by this FastAPI process — see decision #32 and [Queued Background Backtests](../design/backtest-queue.md). The Python `quant.queue.worker_loop` daemon (separate container) consumes jobs from `BT.QUEUE`; all HTTP terminates here.

## API namespaces

| Area | Path prefix | Notes |
|------|-------------|--------|
| **Auth** | `/api/v1/auth/*` | Session cookie |
| **Backtest** | `/api/v1/backtest/*` | Sync optimize / performance / walk-forward |
| **Backtest queue** | `/api/v1/backtest/jobs/*` | Async `BT.QUEUE` jobs |
| **Shared config** | `/api/v1/refdata/*`, `/api/v1/inst/*` | Used by Backtest and Trade UIs |
| **Trade — deployments** | `/api/v1/trade/deployments/*` | **Done** (Phase 1.2) |
| **Trade — credentials** | `/api/v1/credentials/*` | **Done** (Phase 1.1) |
| **Trade — strategies** | `/api/v1/strategies` | **Done** (Phase 1.6) — `?versions=best\|all`, `?limit=` |
| **Backtest — promotions** | `/api/v1/backtest/promotions` | **Done** — promotion history for the Promotion tab |
| **Admin / scheduler** | `/api/v1/admin/*`, `/api/v1/market-data/*`, `/api/v1/scheduler/*` | Service-token or session — EventBridge Lambda entry points |

UI mode (`/backtest` vs `/trade`) does **not** change these URLs — each page calls the appropriate prefix.

## Starting the Server

```bash
source env/bin/activate
uvicorn quant.api.main:app --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs`.

The Vite dev proxy forwards `/api` from `http://localhost:5173` to this backend.

## Endpoints

All endpoints below are mounted under the `/api/v1` prefix.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/login` | Public (rate-limited 5/15min per IP) | Issues an `HttpOnly` JWT cookie (`qs_token`). |
| `POST` | `/api/v1/auth/logout` | Required | Clears the session cookie. |
| `GET`  | `/api/v1/auth/me` | Required | Returns the current user (or 401). |

### Backtest

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/backtest/optimize` | Run parameter grid search over a list of factors. Returns top-10 results, grid, and best params. |
| `POST` | `/api/v1/backtest/optimize/stream` | SSE-streamed optimization — sends `init`, `progress`, `result`, and `error` events in real time. |
| `POST` | `/api/v1/backtest/performance` | Run a single backtest at fixed params. Returns equity curve, metrics, and daily P&L. |
| `POST` | `/api/v1/backtest/walk-forward` | Walk-forward overfitting test. Returns IS/OOS metrics, overfitting ratio, and full equity curve. |
| `POST` | `/api/v1/backtest/jobs` | Enqueue a backtest job (202 Accepted). |
| `GET`  | `/api/v1/backtest/jobs` | List queue rows for the current user. |
| `GET`  | `/api/v1/backtest/jobs/{queue_id}` | Job detail + strategy metadata. |
| `POST` | `/api/v1/backtest/jobs/{queue_id}/cancel` | Cancel a queued or running job. |
| `POST` | `/api/v1/backtest/jobs/{queue_id}/reenqueue` | Re-enqueue from a terminal row. |
| `GET`  | `/api/v1/backtest/jobs/{queue_id}/events` | SSE stream of job progress events. |
| `GET`  | `/api/v1/backtest/promotions` | Promotion history rows for the Promotion tab (`?limit=`). |
| `POST` | `/api/v1/backtest/jobs/strategies/{strategy_id}/promote` | Manual promote/demote a strategy VID. |

### Trade (Phase 1.2 — deployments)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/trade/deployments` | Required | Create or re-apply a deployment. Optional `schedule_tm_interval_id` (`REFDATA.TM_INTERVAL`) sets the apply cadence; omit or `null` for manual-only, which is what the UI's schedule dropdown defaults to (see [scheduler §3.1](../design/scheduler-price-bars.md#31-product-ux-how-scheduling-is-enabled)). |
| `GET` | `/api/v1/trade/deployments` | Required | List current deployments for the authenticated user. |
| `GET` | `/api/v1/trade/deployments/{id}` | Required | One deployment (current version). |
| `PATCH` | `/api/v1/trade/deployments/{id}` | Required | Toggle `enabled` / `deployment_status`, or change `schedule_tm_interval_id`. Omitted fields keep their value; explicit `null` clears the schedule. |
| `POST` | `/api/v1/trade/deployments/{id}/stop` | Required | Stop a deployment — disables it and sets `STOPPED`. Idempotent. |
| `POST` | `/api/v1/trade/deployments/{id}/apply` | Required | Run one live-apply cycle now. |
| `POST` | `/api/v1/trade/deployments/dry-run` | Required | Preflight a deployment without placing orders. |
| `GET` | `/api/v1/trade/execution-events` | Required | Recent order attempts across the caller's deployments (`?limit=50`, optional `deployment_id`). |
| `GET` | `/api/v1/trade/transactions` | Required | Recent broker-confirmed fills (`?limit=50`, optional `deployment_id`). |
| `GET` | `/api/v1/trade/deployments/{id}/events` | Required | Execution diary for one deployment. |
| `GET` | `/api/v1/trade/deployments/{id}/transactions` | Required | Fill history for one deployment. |
| `GET` | `/api/v1/trade/accounts/{api_credential_id}/snapshot` | Required | Live balances and open positions for one broker account. Read-only. Query `paper` (default `true`). **404** if the credential is not owned. |
| `GET` | `/api/v1/trade/schedule-options` | Required | `tm_interval_ids` a deployment may be scheduled on — see [the cadence guard](#the-schedule-cadence-must-match-the-fitted-bars) below. |

#### The schedule cadence must match the fitted bars

A schedule decides more than *when* an apply runs. `LiveApplyOrchestrator`
resolves the deployment's interval into the bar window it loads, so the cadence
also decides **which bars the signal is computed from**. Every backtest fits on
daily bars, so an hourly schedule would push hourly bars through daily-fitted
parameters — which fails silently: the indicator still returns a number and the
order still places.

`POST /trade/deployments` and `PATCH /trade/deployments/{id}` therefore reject a
`schedule_tm_interval_id` outside `schedulable_interval_ids()` with **400** and a
message naming both cadences. `null` (manual) is always accepted. A PATCH is
checked only on the value it *sets*, so the kill switch still reaches a row
whose cadence predates the rule.

`GET /trade/schedule-options` publishes the same set, which is how
`DeploymentDialog` and `ScheduleCell` grey out the cadences the API would refuse
rather than keeping their own copy of the rule.

#### A dry run previews the apply's own price series

`POST /trade/deployments/dry-run` computes its signal from the series the live
apply would read, resolved by the same `bar_source.resolve_signal_source` — the
venue's bars where the venue serves market data (#45), the provider only for a
broker that has none. It did not always: the dry run passed no `bar_loader` and
so priced off the provider while the apply priced off the exchange, which near a
band edge is a preview reporting `HOLD` and an order going out as `BUY`, with
neither computation wrong.

`DryRunReport.bar_source` names the series (`price_bar:<venue>` or `provider`),
matching `ApplyReport.bar_source`, and the report dialog shows it as **Price
source**. Two sources are two sets of numbers, so a divergence is only
diagnosable when the input is recorded next to the output.

#### Broker failures — status says whether to retry

Anything that reaches an exchange (`dry-run`, `apply`, the account snapshot) can
fail at the broker rather than in our code, and the status separates the two
things a caller can do about it:

| Condition | Status | What the caller does |
|---|---|---|
| Broker rejected the credentials (`BrokerAuthError`) | **400** | Fix the key — retrying is pointless |
| Broker unreachable or erroring (`BrokerConnectionError`) | **503** | Come back on the next tick |
| Bars incomplete (`StaleBarsError`) | **503** | Come back on the next tick |
| Unknown product / no xref (`SymbolMappingError`) | **400** | Fix the request or seed `INST.PRODUCT_XREF` |

A rejected key used to answer **502**, which put a wrong API key in the same
bucket as a platform outage. That is worth stating because the response body
carries the broker's own explanation and the remedy — a **paper** deployment
connects to the venue's *testnet*, so mainnet keys are rejected there — and a
5xx is exactly the response an intermediate proxy is entitled to replace with
its own error page before anyone reads it.

Every handled error is also logged once by `quant/api/exception_handlers.py`
(`METHOD /path -> status: detail`), at `WARNING` for 4xx and `ERROR` for 5xx.
Handling an exception consumes it, so before that a failed request left no
server-side trace at all and could only be reconstructed from the client.

#### Account snapshot

Every field is read from the exchange at request time — nothing comes from our
tables. The point is to show what the account *actually* holds, so a position
opened by hand or left behind by a stopped deployment appears here even though no
`TRADE.DEPLOYMENT` row explains it. Compare with `POSITION_QTY` on
`TRADE.EXECUTION_EVENT`, which records what one apply *saw* at its moment;
this endpoint answers what is true now.

- `balances[]` — `code`, `free`, `used`, `total` per currency. Currencies with
  nothing in them are dropped: a unified account reports every listed asset, and
  a hundred zero rows would bury the one that matters. A currency held only as
  margin (`free` 0, `used` > 0) is kept.
- `positions[]` — signed `qty` (negative short), plus `entry_price`,
  `mark_price`, `notional`, `unrealized_pnl`, `leverage`, `liquidation_price`.
  Optional fields are `null` when the exchange omits them; one missing field
  never fails the snapshot. `symbol` is the raw exchange symbol so it lines up
  with `INST.PRODUCT_XREF`.
- `app_id` is read off the credential row, not taken from the caller — a client
  cannot pair one exchange's keys with another's adapter.
- `paper` defaults to `true`, so a caller that omits it reaches the demo account
  and never real money. The same credential can address both, and they hold
  different money.
- Not cached server-side: each call is a rate-limited exchange round-trip. The
  frontend uses a 30s stale window with an explicit refresh rather than polling.

### Credentials (Phase 1.1 — implemented)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/credentials` | Required | List current user's exchange credentials (masked). |
| `GET` | `/api/v1/credentials/{id}` | Required | One credential (masked). **404** if not owned (never 403). |
| `POST` | `/api/v1/credentials` | Required | Save new broker API key pair. Rate-limited 5/15min per IP. |
| `PUT` | `/api/v1/credentials/{id}` | Required | Rotate keys (soft-version bump). Rate-limited 5/15min per IP. |
| `DELETE` | `/api/v1/credentials/{id}` | Required | Revoke (soft-version; clears ciphertext). Returns 204. |

Keys are Fernet-encrypted in Python (`quant/shared/secrets_crypto.py`) before `CALL CORE_ADMIN.SP_INS_API_CREDENTIAL`. Responses never include `*_CIPHERTEXT`. Broker is identified by `app_id` (`REFDATA.APP`). Full flow: [Credential Encryption](credentials.md).

See [Plan to Profit §1.1](../design/plan-to-profit.md#phase-11-user-secrets) and [Login §6.4](../design/login.md#64-reuse-from-login-jwt-credential-api-phase-11).

### Strategies (Phase 1.6 — implemented)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/strategies` | Required | List caller-owned `BT.STRATEGY` rows for the Trade strategy picker. Query `versions=best` (default — `IS_BEST_IND` rows only) or `all`; `limit` defaults to 200. |

Not the same as REFDATA `signal_type` — see [trade-api §2.1](../design/trade-api.md#21-strategy-catalog-phase-16).

### REFDATA / Instruments (shared)

How the cache is published and read: [REFDATA Cache](refdata-cache.md).

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/v1/refdata/{table_name}` | Fetch a cached REFDATA table (e.g. `indicator`, `signal_type`, `asset_type`, `app`). |
| `POST` | `/api/v1/refdata/refresh` | Reload all REFDATA tables from the database without restarting the server. Returns `{"tables": n}`. |
| `GET`  | `/api/v1/inst/products` | List products (cached `InstrumentCache`). |
| `GET`  | `/api/v1/inst/products/{id}/xrefs` | Vendor-symbol cross-references for a product. |
| `GET`  | `/api/v1/inst/apps/{app_id}/products` | Only the products that app lists, each with the `vendor_symbol` it prints. |

`/inst/products` is every instrument the platform knows, which is the wrong
list to offer once a venue is chosen — a Nasdaq ETF has no Bybit xref, so
picking it could only produce a subscription that never captures a bar.
Listing is exactly what `INST.PRODUCT_XREF` records, so the xrefs for one app
*are* the venue's catalogue. Served from `InstrumentCache` in memory, no query.
An app that lists nothing returns `[]`, unlike `/products/{id}/xrefs`, where a
missing product is a 404 — listing nothing is a real answer, not an error.
| `POST` | `/api/v1/inst/refresh` | Reload the instrument cache. Returns 204. |

### Admin / scheduler (service token or session)

These routers are mounted with `require_user_or_service` so the EventBridge Lambda can call them with `TRADE_SERVICE_TOKEN`. Human-facing routes on the same routers add `require_user` when needed.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/admin/log-proc-summary/summarize` | Service or session | Aggregate `LOG_PROC_DETAIL` into daily per-procedure summaries. |
| `POST` | `/api/v1/market-data/price-bars/sync` | Service or session | Pre-fetch bars for every series a scheduled deployment or a subscription wants (bar warmer). |
| `POST` | `/api/v1/scheduler/tick` | Service or session | Apply every deployment currently due across all intervals (hourly platform sweep). |

### Market data capture (session only)

On the same router, but each adds `require_user` — the router gate is a floor,
not a ceiling. A service token must **not** subscribe or backfill: both spend
exchange rate limit on behalf of a user who did not ask.

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/v1/market-data/subscriptions` | Every bar subscription with its coverage (first bar, last bar, gap count) and the venue's own `vendor_symbol`. |
| `POST` | `/api/v1/market-data/subscriptions` | Create a subscription, or version one — enable, disable, retarget. |
| `GET`  | `/api/v1/market-data/price-bars/coverage` | `MIN`/`MAX` stored bar plus gap count for one series — what is **held**. |
| `GET`  | `/api/v1/market-data/price-bars/venue-depth` | Oldest bar the venue serves, how many bars that is, and the fill ceiling — what **exists**. |
| `GET`  | `/api/v1/market-data/price-bars/backfill-plan` | The next pass toward a `target`: window, bar count, passes remaining. |
| `POST` | `/api/v1/market-data/price-bars/backfill` | Fill an explicit range, reporting what the venue would not serve. `end` defaults to the last closed bar. |

#### Coverage and depth are different questions

`coverage` reads two index probes against `PRICE_BAR`; `venue-depth` asks the
exchange. That cost difference is why the subscription list carries coverage on
every row but never depth — a network call per row to draw a table is not worth
it — and why the dialogs request depth on demand, once product, interval and
venue together identify one series.

Depth is what lets a capture target be the venue's own floor rather than a date
someone invented. A target older than the first bar an exchange ever printed can
never be met, and before this existed the page reported that as an open gap
([decision #52](../decisions.md)).

Backfill takes a ceiling: a range spanning more than `MAX_BACKFILL_BARS`
boundaries is refused **400** before any work starts, because the fill is one
synchronous blocking request and a range large enough to outlive the proxy
would store nothing while the caller learned only that the request died.

#### Deep history is filled in passes

The ceiling alone made deep intraday history unreachable rather than merely
slow. Backfill used to run to the last closed bar always, so for a series
already holding a year of hourly bars **no start** both reached further back and
stayed under the ceiling: the nearer the start, the more of the span was bars
already stored, and the span is counted either way. The advice the refusal gave
— fill a nearer date and repeat — could not work however many times it was
followed.

`GET /price-bars/backfill-plan` answers what one pass should cover. Given a
`target`, it returns the window ending where coverage currently begins, the bar
count, and how many passes remain. Each pass therefore spans only bars that are
absent, and the next resumes from the ground the last one gained. A series with
nothing stored anchors on the last closed bar instead, so the first pass yields
bars a strategy can already use rather than history nobody can trade on.

The plan costs two index probes and arithmetic — no exchange call — so the
dialog re-asks after every fill, which is the point: the answer moves as
coverage grows. `target` is supplied by the caller rather than read from the
subscription, because the page has already chosen between the row's own target
and the venue floor, and re-deriving it server-side would mean an exchange call
for a question answerable from stored bars.

Chunking is still not done on the caller's behalf. A pass is a click, because
looping server-side would be the background filler this design declined —
needing the progress tracking nothing here keeps ([decision #52](../decisions.md)).

`vendor_symbol` is resolved by the service through the same `InstrumentCache`
the fetcher uses, not selected by `SP_GET_BAR_SUBSCRIPTION` — so the list cannot
disagree with what actually gets requested, and adding it needed no migration.
It is `null` when the `INST.PRODUCT_XREF` row has been withdrawn since
subscribing, which breaks capture and is worth surfacing rather than hiding
behind an internal identifier nobody can look up on an exchange.

#### Subscriptions are shared, not caller-scoped

Unlike deployments, these reads and writes are **not** filtered by
`APP_USER_ID`. A bar is a shared fact — one row per `(cusip, interval, venue,
timestamp)` — so a subscription is a platform-wide request that any signed-in
user can see and edit, including disable, which cools the series for everybody
([decision #50](../decisions.md)). Being signed in is what these routes check;
ownership is not something a bar series has.

Two error shapes worth knowing:

- **400 on subscribe** when the product has no `INST.PRODUCT_XREF` row for that
  venue, or the app is not an exchange this platform reads bars from. Validated
  on write precisely so three silent per-tick warm failures become one message
  the caller can act on.
- **`coverage.error` rather than a failed response** when a venue cannot be
  reached during a list read. A page showing ten series must still render when
  one exchange is away.

Backfill returns 200 with `is_continuous: false` rather than raising on a hole.
That inverts the live path's fail-closed rule deliberately: during a repair a
hole is ordinary — pre-listing history, or past what the venue retains — and
aborting would discard the bars that *were* recoverable.

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness — returns 200 if the process is up. |
| `GET`  | `/health/ready` | Readiness — performs a DB ping. |

Health endpoints are **not** under `/api/v1` and are unauthenticated.

## Authentication

Protected routers use `Depends(require_user)` to validate the JWT cookie. Unauthenticated requests get **401 Unauthorized**, which the frontend interceptor uses to evict the cached user and re-render the login page.

Provisioning new users is admin-only (no signup endpoint) — see [Login & Authentication](../design/login.md) for the runbook.

## Factor List (single source of truth)

All backtest requests use a uniform **factor-list** shape. There is no `mode` discriminator and no separate single-factor branch — a "single factor" backtest is just a 1-element `factors` list. This keeps cross-product semantics (factor on a different symbol than the trade asset, e.g. trade SPY but signal off VIX RSI) available for any factor count.

Each `FactorConfig` carries:

- `symbol` / `vendor_symbol` / `data_source` — **where the indicator reads from** (optional; defaults to the top-level trade asset). Set these when the indicator should be computed from a different product than the one being traded.
- `data_column` — which column of the source DataFrame becomes the `factor` series (default `"price"`).
- `indicator` / `strategy` — what to compute and how to turn it into positions.
- `window_range` / `signal_range` — the parameter grid for this factor.

`conjunction` (`"AND"` / `"OR"` / `"FILTER"`) describes how multiple factors' positions are combined. It is **required only when there are 2+ factors** and must be omitted (or `null`) for a single-factor request — the field is meaningless in that case. The service layer dispatches the optimizer based on `len(factors)`:

- 1 factor → `ParametersOptimization.optimize()` returning rows keyed `window` / `signal`
- 2+ factors → `ParametersOptimization.optimize_multi()` returning rows keyed `window_0` / `signal_0` / `window_1` / …

For `/performance`, the caller passes `windows: list[int]` and `signals: list[float]` — one value per factor, in the same order.

### The traded venue is required, and the name says which one

Request-level `data_source` — the venue the **trade asset** is priced from — is mandatory on `OptimizeRequest`, `PerformanceRequest`, and `WalkForwardRequest`. It has no default and rejects the empty string, so omitting it is **422**, not a Yahoo run.

It used to default to `"yahoo"`, and the client dropped the field when the box was blank. The two combined to produce a run nobody configured: a strategy stored in production carried `"data_source": "yahoo"` while its `STRATEGY_NM` read `... on bybit:price`, because the name was assembled only from factor recipes and a factor had been set to Bybit. Setting the source on a factor does not move the traded series — the traded leg is fetched with the request-level value, and only factors fall back to it (`f.data_source or req.data_source`).

The canonical name therefore carries the traded venue **and the cadence** as `TRADE@VENUE:CADENCE ← …`:

```
btcusdt.crypto@bybit:DAILY ← btcusdt.crypto/get_bollinger_band/momentum on bybit:price
btcusdt.crypto@bybit:1H    ← btcusdt.crypto/get_bollinger_band/momentum on bybit:price
```

Since `STRATEGY_NM` is the identity key, the same recipe fitted on Yahoo prints and on Bybit prints are now two strategies rather than one grouped pair. Names minted before the venue segment existed have none; re-running such a config produces a new name, and therefore a new identity, which is intended — the old name could not distinguish the two.

Cadence joined the key for the same reason and one worse consequence. `tm_interval_id` was added to the request ([below](#the-cadence-is-chosen-not-assumed)) but not to the name, so an hourly run of a daily recipe resolved to the daily lineage and was stored as its next `STRATEGY_VID`. A shared `STRATEGY_ID` is the claim that two runs are versions of one thing, which is also the instruction to compare their metrics: `_evaluate_soft` ranks a candidate against the current best VID by Sharpe, and hourly Sharpe is annualised over 8,760 periods against daily's 365. The candidate died on a range error before producing a number, and nothing else would have stopped it taking `IS_BEST_IND` on units alone — a winner `schedule_policy` would then refuse to deploy, since it only allows the cadence a strategy was fitted on. `buildStrategyNm` takes the cadence as `REFDATA.TM_INTERVAL.NAME`, never the id, so renumbering the table cannot fork every lineage.

### What counts as a new version, and what counts as a new strategy

`STRATEGY_VID` counts re-optimisations of one strategy. A new `STRATEGY_ID` is a different question being asked. The line falls where the metrics stop being comparable:

| Same lineage — new `STRATEGY_VID` | New lineage — `STRATEGY_VID` 1 |
|---|---|
| Grid bounds (`window_range`, `signal_range`) | Traded product |
| Date range | Venue / `data_source` |
| `fee_bps`, `split_ratio`, `walk_forward` | `tm_interval_id` |
| The fitted `window` / `signal` the optimizer returns | A factor's signal source, indicator, or signal type |
| | `data_column` — the metric read |
| | Factor count, conjunction |

Everything on the right names *what series goes in*; everything on the left names *how hard the optimizer searched, given that series*. Date range is the loosest item on the left — two runs over different periods are not strictly comparable either — but they are at least on one scale, which cadence is not.

### The range comes from what is captured

An exchange backtest reads `MARKET_DATA.PRICE_BAR`, so the stored bars bound it. `_fetch_exchange_df` refuses a range the store cannot cover rather than returning a shorter series under the requested label, and the config drawer reads `GET /price-bars/coverage` for the traded series so the refusal is avoidable rather than a surprise: choosing an exchange series snaps Start and End to the captured range, and a date typed outside it is flagged with the range offered as a one-click fix. Provider sources are left alone — `Refresh dataset` refetches any window on demand, so what happens to be cached is not a floor.

**The tail gets one bar of slack, the head gets none.** The End field defaults to today and today's bar has not closed, so demanding the store reach it refused every run made before the close. A bar that cannot exist yet is not missing history, so a requested end up to one bar past the last stored bar is served. Slack of exactly one period keeps that from excusing a real hole — an end a month past the last close is still refused — and the head gets none, because a day before the first bar is absence rather than a bar still forming. The period is the requested interval's, not a fixed day: as a constant it would have let an hourly run skip 24 missing bars at the tail.

**An intraday range carries a time, because a date input cannot say 10:00.** A date field expresses midnight, and truncating an intraday bound to its date moves it *backwards*. Bybit's first hourly `BTCUSDT` bar is `2020-03-25 10:00`, so snapping produced a start of `2020-03-25` — ten hours of history that has never existed, against a head with no slack. The drawer said the range fitted, because it compared the same truncated strings, and the worker refused the job: one FAILED run whose only fault was that the two sides reasoned in different units.

The first fix rounded the head *up* to the next whole day. That was accepted by the server but paid for a field's limitation with a day of history, and it left the two sides still reasoning in different units — so the field holds the unit instead. `capturedRange` reports the stored bounds **as stored**, to the minute, and marks the range `intraday` when either bound carries a time; the drawer then renders `datetime-local` rather than `date` controls. `_fetch_exchange_df` already parses whatever ISO string arrives through `pd.Timestamp(start, tz="UTC")`, so nothing changed server-side. Daily series are untouched — their bars sit on midnight, so there is no time of day to lose and none is shown.

### The cadence is chosen, not assumed

`OptimizeRequest.tm_interval_id` names the bars a run is fitted on, and it is **required** for the same reason `data_source` is — it selects an input series, and a server-side default chooses one without saying so. Only an exchange source can serve anything but daily, because only captured bars exist at other cadences; a provider asked for an intraday interval is refused rather than handed daily bars under an intraday label, since `get_historical_price` returns daily bars whatever it is asked for.

**The server refuses a name that disagrees with its config.** `STRATEGY_NM` is the lineage key `SP_INS_STRATEGY` resolves, and it was stored exactly as the client sent it — which made identity a client-side construction. After `1.19.0` renamed every stored row to carry its cadence, a browser still holding a bundle from before that change enqueued `btcusdt.crypto@bybit ← …` and forked a second lineage beside the `:DAILY` one it belonged to. Fixing the frontend cannot prevent that recurring, because the guarantee has to hold where the row is written, and the fork cannot be repaired afterwards: `UNIQUE (USER_ID, STRATEGY_NM, STRATEGY_VID)` means renaming the stray lineage onto the real one collides at VID 1. `JobsService.enqueue` now checks the traded leg ends `:<REFDATA.TM_INTERVAL.NAME>` for the request's own `tm_interval_id` and returns **400** otherwise, so the two halves of one request cannot describe different series.

Three things follow for callers. `BT.STRATEGY.CONFIG_JSON` stores the request verbatim and `live_service` replays it through `OptimizeRequest.model_validate`, so rows written before the field existed were backfilled to DAILY — what they always were. `trading_period` is the annualisation scalar (365 daily, 8,760 hourly): the config drawer scales `REFDATA.ASSET_TYPE.TRADING_PERIOD` by the interval's bars-per-day, because annualised return scales by that number and Sharpe by its square root, so a daily figure left on an hourly run understates both. And because that scalar moves, the cadence is part of the [strategy's identity](#the-traded-venue-is-required-and-the-name-says-which-one) — two runs whose Sharpe is annualised differently must not share a `STRATEGY_ID`, where promotion would compare them bare.

## SSE Streaming (`/optimize/stream`)

The streaming endpoint uses `StreamingResponse` with Server-Sent Events:

1. **`init`** — sent once with `{ "total": <total_trials> }` before optimization starts
2. **`progress`** — sent per trial with `{ "trial": ..., "total": ..., "best_sharpe": ... }`
3. **`result`** — sent once with the full optimization result (same shape as `/optimize`)
4. **`error`** — sent if optimization fails; payload contains `{ "detail": "..." }`

Backend implementation: `queue.Queue` + `threading.Thread` + `asyncio.to_thread` so the worker can stream progress without blocking the event loop.

## Caches: REFDATA, INST, BT

At startup the FastAPI lifespan hook also builds `CredentialCrypto` (Fernet key from `EXCHANGE_SECRETS_KEY` — prod fail-fast) and a `DataCaches` bundle wired to Postgres + Redis:

- **`RefDataPublisher`** (`quant/refdata/publisher.py`) — first runs `publish_all()`, which discovers every `REFDATA.*` table via `information_schema`, calls `REFDATA.SP_GET_ENUM`, and writes JSON snapshots under `refdata:<table>` plus a bumped `refdata:version` key in Redis. The same call is exposed at `POST /api/v1/refdata/refresh` for ad-hoc reseeding.
- **`RedisRefData`** (`quant/refdata/reader.py`) — read-only accessor used by request handlers and the worker. Checks `refdata:version` on every `get()` and rebuilds its local snapshot lazily on bump, so long-lived processes always see the current REFDATA without pub/sub.
- **`InstrumentCache`** (`quant/data/instruments.py`) — products + xrefs from the INST schema; loaded at startup and refreshable via `POST /api/v1/inst/refresh`.
- **`BacktestCache`** (`quant/data/backtest_cache.py`) — BT schema read/write used by the optimize/performance services for the dataset cache.

If the REFDATA publish fails at startup the server still boots (REFDATA endpoints 503 until `POST /api/v1/refdata/refresh` succeeds); the instrument-cache load and missing prod secrets still fail the boot.

## Project Structure

```
quant/api/
├── main.py              # App factory — CORS, lifespan, router registration
├── deps.py              # FastAPI dependencies (DataCaches, auth)
├── exception_handlers.py
├── auth/
│   ├── router.py        # /api/v1/auth/* endpoints
│   ├── service.py       # AuthService — password verify (Argon2), JWT
│   ├── dependencies.py  # require_user / require_user_or_service
│   ├── repo.py          # AuthRepo — calls SP_GET_APP_USER_BY_*
│   └── models.py        # Pydantic models (LoginRequest, etc.)
├── credentials/         # Phase 1.1 — exchange API keys
│   ├── router.py        # /api/v1/credentials/* (rate-limited POST/PUT)
│   ├── service.py       # CredentialService — Fernet encrypt, mask responses
│   ├── repo.py          # ApiCredentialRepo — SP_INS/GET/REVOKE
│   └── schemas.py       # CreateCredentialRequest, CredentialResponse, …
├── admin/               # Service-token maintenance (log-proc summary)
│   ├── router.py
│   └── repo.py
├── market_data/         # Bar warmer + capture subscriptions, coverage, backfill
│   └── router.py
├── scheduler/           # Platform tick — POST /scheduler/tick
│   └── router.py
├── routers/
│   ├── backtest.py      # /api/v1/backtest/* endpoints
│   ├── deployments.py   # /api/v1/trade/deployments/* + execution diary reads
│   ├── jobs.py          # /api/v1/backtest/jobs/* + manual promote
│   ├── promotion.py     # /api/v1/backtest/promotions
│   ├── strategies.py    # /api/v1/strategies (Phase 1.6)
│   ├── refdata.py       # /api/v1/refdata/* endpoints
│   └── inst.py          # /api/v1/inst/* endpoints
├── schemas/
│   ├── jobs.py
│   ├── promotion.py
│   └── strategies.py
└── services/
    ├── jobs.py          # Enqueue, list, cancel, SSE broker
    ├── promotion.py
    └── strategies.py

quant/shared/config.py              # Settings, env/SSM loading (not under api/)
quant/shared/secrets_crypto.py      # CredentialCrypto — EXCHANGE_SECRETS_KEY + Fernet
quant/strategy/backtest_service.py  # Backtest orchestration (called from routers)
quant/trade/service.py              # TradeService — deployments (Phase 1.2)
quant/trade/db_repo.py              # TradeRepo — SP_INS/GET_DEPLOYMENT
```

REFDATA, INST, and BT cache classes live under `quant/refdata/` and `quant/data/` (shared between the API and the worker via `quant/refdata/bundle.py::DataCaches`). All Postgres access goes through `quant/shared/db.py::DbGateway` — no other module imports `psycopg` (except the `/health/ready` DB ping in `main.py`).
