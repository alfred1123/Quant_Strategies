# Design: Separate Indicator Underlying from Trading Underlying

**Status:** Draft — pending review  
**Date:** 2026-04-18  
**Author:** alfcheun

## Problem

Every backtest currently uses a **single symbol** for both indicator calculation and PnL.
There is no way to express "compute RSI on VIX but trade SPY", or "use BTC dominance as a signal while trading ETH".

The same `ticker` string flows through the entire stack:

| Layer | Location | Field |
|-------|----------|-------|
| DB | `BT.STRATEGY` | `TICKER TEXT` |
| DB | `BT.RESULT` | `TICKER TEXT` |
| Python | `StrategyConfig` | `ticker: str` |
| Python | `SubStrategy` | *(none — inherits from config)* |
| API | `OptimizeRequest`, `PerformanceRequest` | `symbol: str` |
| Frontend | `BacktestConfig` | `symbol: string` |
| Frontend | `FactorConfig` | *(none)* |

`SubStrategy.data_column` selects which column (price, volume) from the *same* DataFrame — it does not select a different underlying.

## Goal

Separate the **trading underlying** (what we buy/sell for PnL) from the **indicator underlying** (what each SubStrategy computes its indicator on).

**Default behaviour:** When a sub-strategy's indicator operates on price data, it defaults to the trading product. Users can override per sub-strategy.

## Key Principle — Avoid Refetching Data

DataFrames are keyed by **ticker string** (e.g. `"BTC-USD"`, `"^VIX"`). When a sub-strategy uses the default product (same ticker as the trading product), it reuses the **same DataFrame** — no extra fetch. Only when a sub-strategy overrides with a different ticker does the caller fetch an additional DataFrame.

## Design

### Phase 1 — Python Backend (implement first)

#### 1a. `SubStrategy` — add `ticker`

```python
@dataclass(frozen=True)
class SubStrategy:
    indicator_name: str
    signal_func_name: str
    window: int
    signal: float
    data_column: str = "v"
    ticker: str | None = None  # NEW: indicator underlying
                                # None = use StrategyConfig.ticker (default)
```

**Default rule:** `ticker=None` means "same as `StrategyConfig.ticker`". The caller passes a `dict[str, pd.DataFrame]` keyed by ticker. When `sub.ticker is None`, the sub-strategy reads from `data[config.ticker]` — the **same** DataFrame, no copy, no refetch.

#### 1b. `StrategyConfig` — keep `ticker` as-is

`StrategyConfig.ticker` stays as a string. No change needed now — `product_id` migration happens in the DB phase.

Add a helper to collect all unique tickers:

```python
def get_tickers(self) -> set[str]:
    """Return all unique tickers needed by this strategy."""
    tickers = {self.ticker}
    for sub in self.substrategies:
        if sub.ticker is not None:
            tickers.add(sub.ticker)
    return tickers
```

#### 1c. `Performance.__init__` — accept `dict[str, pd.DataFrame]`

```python
class Performance:
    def __init__(self, data, config, window=None, signal=None, *, fee_bps=None):
        # data: dict[str, pd.DataFrame] keyed by ticker
        self.all_data = data
        self.data = data[config.ticker].copy()   # trading product (PnL source)
        ...
```

- `self.data` = the **trading** DataFrame (used for PnL, `price`, `chg`, buy-hold)
- `self.all_data` = the full dict (each sub-strategy resolves its own)

#### 1d. `Performance._enrich_multi_factor` — per-sub DataFrame lookup

```python
def _enrich_multi_factor(self):
    ...
    for i, sub in enumerate(self._subs):
        sub_ticker = sub.ticker or self.config.ticker
        sub_df = self.all_data[sub_ticker]     # same ref if default
        sub_data = sub_df[['factor']].copy()
        sub_data['factor'] = sub_df[sub.data_column]
        ta = TechnicalAnalysis(sub_data)
        indicator_vals = getattr(ta, sub.indicator_name)(self._windows[i])
        # Reindex to trading DataFrame's index
        indicator_vals = indicator_vals.reindex(self.data.index)
        ...
```

When `sub.ticker is None`, `sub_df` points to the same `self.all_data[config.ticker]` — no extra memory, no refetch.

#### 1e. `Performance._enrich_single_factor` — same pattern

```python
def _enrich_single_factor(self):
    sub = self._subs[0]
    sub_ticker = sub.ticker or self.config.ticker
    sub_df = self.all_data[sub_ticker]
    ...
```

#### 1f. `ParametersOptimization` — accept `dict[str, pd.DataFrame]`

```python
class ParametersOptimization:
    def __init__(self, data, config, *, fee_bps=None):
        self.data = data    # dict[str, pd.DataFrame]
        ...
```

Inside `objective()`, pass `self.data` (not `.copy()`) — `Performance` copies the trading DataFrame internally.

#### 1g. `main.py` — build data dict

```python
# Fetch all unique tickers needed by the strategy
data_dict = {}
for ticker in config.get_tickers():
    data_dict[ticker] = data_source.get_historical_price(ticker, start, end)

perf = Performance(data_dict, config, fee_bps=fee_bps)
opt = ParametersOptimization(data_dict, config, fee_bps=fee_bps)
```

For the common single-ticker case, the dict has one entry — no overhead.

### Phase 2 — API Backend

#### 2a. `api/schemas/backtest.py` — add `symbol` per factor

```python
class FactorConfig(BaseModel):
    indicator: str
    strategy: str
    data_column: str = "price"
    window_range: RangeParam
    signal_range: RangeParam
    symbol: str | None = None   # NEW: None = use request-level symbol
```

Request models keep `symbol: str` for now. `product_id` comes in DB phase.

#### 2b. `api/services/backtest.py` — fetch unique symbols

```python
symbols = {req.symbol}
for f in (req.factors or []):
    if f.symbol is not None:
        symbols.add(f.symbol)

data = {sym: _fetch_df(sym, ...) for sym in symbols}
```

### Phase 3 — Database (all access via stored procedures)

#### 3a. INST seed data + procedures

Seed `INST.PRODUCT` and `INST.PRODUCT_XREF` via stored procedures:
- `INST.SP_INS_PRODUCT`
- `INST.SP_INS_PRODUCT_XREF`

GET procedures for backend:
- `INST.SP_GET_PRODUCT` — list/filter products
- `INST.SP_GET_PRODUCT_XREF` — resolve vendor symbol by product + app

#### 3a.1. PRODUCT_XREF population model

`INST.PRODUCT_XREF` is the canonical vendor-symbol mapping layer. The long-term design is a **semi-automatic proposal + approval** workflow, not blind auto-insert from vendor feeds.

Target flow:

1. Import vendor instrument master rows into a staging area keyed by `APP_ID`.
2. Run matching rules against `INST.PRODUCT` and generate candidate mappings with confidence scores.
3. Store candidates in an approval queue for review.
4. On approval, write the authoritative row to `INST.PRODUCT_XREF` via `INST.SP_INS_PRODUCT_XREF`.
5. On reject, either discard the proposal or create a new `INST.PRODUCT` first if the instrument is genuinely new.

Suggested matching split:

- **Auto-propose only**: listed equities with stable exchange+ticker, simple crypto spot pairs, previously-seen vendor symbols for the same `APP_ID`
- **Require manual approval**: futures, perpetuals, options, leveraged tokens, delisted/reused symbols, ambiguous exchange aliases

Implementation note:

- Future DB objects should likely include `INST.PRODUCT_XREF_STG` and `INST.PRODUCT_XREF_PROPOSAL` so the approval queue is separated from the authoritative `INST.PRODUCT_XREF` table.
- Until that workflow is built, **bootstrap/admin population may be done by direct database updates** as an operational shortcut. This is temporary and applies to admin setup only, not application write paths.

#### 3b. BT schema — `TICKER` → `PRODUCT_ID`

```sql
ALTER TABLE BT.STRATEGY ADD COLUMN IF NOT EXISTS PRODUCT_ID INTEGER;
UPDATE BT.STRATEGY s SET PRODUCT_ID = p.PRODUCT_ID
  FROM INST.PRODUCT p WHERE p.SYMBOL = s.TICKER;
ALTER TABLE BT.STRATEGY DROP COLUMN IF EXISTS TICKER;
```

Same pattern for `BT.RESULT`.

#### 3c. Update procedures

- `BT.SP_INS_STRATEGY` — `IN_TICKER` → `IN_PRODUCT_ID`
- `BT.SP_INS_RESULT` — `IN_TICKER` → `IN_PRODUCT_ID`
- New: `BT.SP_GET_STRATEGY`, `BT.SP_GET_RESULT` — backend reads via procedure

#### 3c.1. Where procedures are applied in the flow

Use this sequence during implementation so each layer switches cleanly.

1. **Bootstrap data (admin step, current state):**
    - Populate `INST.PRODUCT`, `INST.PRODUCT_XREF`, `INST.PRODUCT_GRP`, `INST.PRODUCT_GRP_MEMBER`.
    - For now, direct DB updates are acceptable for bootstrap/admin loading.
    - After admin tooling is ready, use `INST.SP_INS_PRODUCT` and `INST.SP_INS_PRODUCT_XREF` for new writes.

2. **Backend read path (first UI dependency):**
    - Add `INST.SP_GET_PRODUCT` for product dropdown/listing.
    - Add `INST.SP_GET_PRODUCT_XREF` (or current-only variant) to resolve vendor symbol by `(PRODUCT_ID, APP_ID)`.
    - API calls these procedures to build UI payloads.

3. **Backtest write path (existing BT inserts):**
    - Update `BT.SP_INS_STRATEGY` and `BT.SP_INS_RESULT` to accept product identity (`IN_PRODUCT_ID`) instead of ticker.
    - Keep API/service writing through BT procedures only.

4. **Backtest read path (result display):**
    - Use `BT.SP_GET_STRATEGY` and `BT.SP_GET_RESULT` for result/history views.
    - UI should not read BT tables directly.

5. **Trade deployment symbol resolution:**
    - On deployment, resolve broker/data-source symbol via `INST.SP_GET_PRODUCT_XREF` from selected product + app.
    - Keep `TRADE.DEPLOYMENT` ticker field as vendor-facing symbol.

Procedure ownership by UI surface:

| UI surface | API need | Procedure(s) |
|---|---|---|
| Product selector | List products | `INST.SP_GET_PRODUCT` |
| Data source / broker symbol resolution | Resolve current vendor symbol | `INST.SP_GET_PRODUCT_XREF` |
| Backtest run save | Insert strategy/result rows | `BT.SP_INS_STRATEGY`, `BT.SP_INS_RESULT` |
| Backtest history screen | Read saved runs | `BT.SP_GET_STRATEGY`, `BT.SP_GET_RESULT` |
| Admin product maintenance | Create/update mappings | `INST.SP_INS_PRODUCT`, `INST.SP_INS_PRODUCT_XREF` |

#### 3d. `TRADE.DEPLOYMENT` — keep `TICKER`

Broker-specific symbol. Resolved from `INST.PRODUCT_XREF` at deployment time.

### Phase 4 — Frontend

#### 4a. Types

```typescript
export interface FactorConfig {
  indicator: string;
  strategy: string;
  data_column: string;
  window_range: RangeParam;
  signal_range: RangeParam;
  symbol?: string;             // null/undefined = use trading symbol
}
```

#### 4b. UI

| Current | After |
|---------|-------|
| Free-text `Symbol` TextField | **Product dropdown** from INST-backed API endpoint |
| *(none)* per factor | Optional **Symbol override** per sub-strategy (collapsed, defaults to trading symbol) |

## API Data Request Persistence

Every API call to an external data provider (Yahoo Finance, Glassnode, Nasdaq Data Link, etc.) is persisted so that repeated backtests never re-fetch the same data. This is especially important for paid / rate-limited providers. With the separate-underlying design, a multi-factor strategy may reference **multiple tickers** — each ticker × provider × metric × interval combination gets its own cached row.

### Schema

```
BT.API_REQUEST  (header — one current row per subscription)
  PK: (API_REQ_ID UUID, API_REQ_VID INTEGER)
  ──────────────────────────────────────────
  APP_ID            → REFDATA.APP           (which provider)
  APP_METRIC_ID     → REFDATA.APP_METRIC    (which metric: ohlcv, on-chain, …)
  TM_INTERVAL_ID    → REFDATA.TM_INTERVAL   (daily, 1h, …)
  INTERNAL_CUSIP    TEXT                     (product identifier)
  PRODUCT_GRP_ID    INTEGER                  (future: group-level requests)
  RANGE_START_TS    TIMESTAMPTZ              (earliest date across all versions)
  RANGE_END_TS      TIMESTAMPTZ              (latest date across all versions)
  TRANSACT_FROM_TS  TIMESTAMPTZ              (version effective from)
  TRANSACT_TO_TS    TIMESTAMPTZ              (9999-12-31 when current)
  USER_ID, CREATED_AT

BT.API_REQUEST_PAYLOAD  (data — JSONB, partitioned yearly via pg_partman)
  PK: (API_REQ_ID, API_REQ_VID, CREATED_AT)
  ──────────────────────────────────────────
  PAYLOAD  JSONB                             (complete merged history)
```

**Relationship:** `API_REQUEST` 1 → N `API_REQUEST_PAYLOAD` on `(API_REQ_ID, API_REQ_VID)`.

**Unique partial index** on `API_REQUEST`:

```sql
CREATE UNIQUE INDEX UX_API_REQUEST_CURRENT_SUBSCRIPTION
ON BT.API_REQUEST (APP_ID, APP_METRIC_ID, TM_INTERVAL_ID, INTERNAL_CUSIP)
NULLS NOT DISTINCT
WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31';
```

This guarantees exactly **one current row** per subscription key.

### Soft-versioning model

When new data is persisted, `SP_INS_API_REQUEST` does not update in place — it:

1. Resolves the next `API_REQ_VID` (`MAX + 1` or `1` if first).
2. Closes the old current row by setting `TRANSACT_TO_TS = now()`.
3. Inserts a new row with `TRANSACT_TO_TS = '9999-12-31'`.
4. Inserts the payload into `API_REQUEST_PAYLOAD` for the same VID.
5. Logs via `CORE_ADMIN.CORE_INS_LOG_PROC`.

This means the full history of every subscription is retained — each VID is a snapshot of the merged dataset at that point in time.

### Stored procedures

| Procedure | Direction | Status | Purpose |
|-----------|-----------|--------|---------|
| `BT.SP_INS_API_REQUEST` | Write | **Deployed** | Combined header + payload insert (steps 1–5 above) |
| `BT.SP_GET_API_REQUEST` | Read | **Deployed** | Return current rows filtered by (APP_ID, APP_METRIC_ID, TM_INTERVAL_ID, INTERNAL_CUSIP), joined with payload |

### Python layer — `BacktestCache`

`BacktestCache` in `src/data.py` (inherits `DbGateway`) is the only consumer of these SPs.

| Method | Role |
|--------|------|
| `get_or_fetch_payload(*, app_id, app_metric_id, internal_cusip, range_start, range_end, fetcher, refresh=False, ...)` | Two-mode orchestrator. With `refresh=False` (default — read-only) returns the cached slice if the cached range fully covers the request, otherwise raises `BacktestCache.CacheMissError` (translated to HTTP 400 by the service layer). With `refresh=True` calls `fetcher(range_start, range_end)` for the **full** requested range and inserts a new version via `SP_INS_API_REQUEST` (re-using the cached `api_req_id` so the SP bumps `API_REQ_VID`). |

The mode is driven by a single UI checkbox **"Refresh dataset"** on the trading-product card. When unchecked, no provider calls and no DB writes occur — versions of `BT.API_REQUEST` only grow when the user explicitly opts in. This keeps `API_REQUEST_PAYLOAD` row count bounded and old partitions easy to drop.

### Cache flow

```
get_or_fetch_payload(..., refresh)
  │
  ├─ 1. SP_GET_API_REQUEST → cached row (range_start_ts, range_end_ts, payload)
  │
  ├─ refresh=False (read-only)
  │     ├─ covers? → return cached_df.loc[req_start:req_end]
  │     └─ miss   → raise CacheMissError → HTTP 400 to client
  │
  └─ refresh=True (write — user opt-in)
        ├─ fetcher(req_start, req_end)  # full range, no gap math
        ├─ SP_INS_API_REQUEST(api_req_id=cached_id or new uuid,
        │                     range=[req_start, req_end],
        │                     payload=fetched)
        │     └─ closes old VID, inserts new VID + payload
        └─ return fetched.loc[req_start:req_end]
```

### Date sync across products + factors

A backtest with N products/factors aligns DataFrames via `reindex` on the main product's index. If a factor is missing dates the main product has, the result silently corrupts. `_build_data_dict` in `api/services/backtest.py` therefore enforces an **intersection check** after fetching: the common `[max(starts), min(ends)]` across all tickers must cover the requested `[start, end]`, else 400 with the limiting ticker named.

### Future work — minimise provider traffic without payload duplication

The current design fetches the full requested range whenever `refresh=True`. For non-price metrics (where the JSONB `API_REQUEST_PAYLOAD` is the only home — see "Future work" in the database doc for moving price into a normalised `BT.PRICE_BAR` table), this is the right trade-off today: one user-driven version per refresh, no churn from incidental range nudges.

Eventually we'll want **delta-row storage** for those metrics — instead of one current row per `(app, metric, interval, cusip)` holding the whole payload, allow multiple current rows each covering a disjoint date range. The read path becomes `union all current rows for the key`, and `refresh=True` only fetches the missing prefix/suffix and inserts it as a new delta row. This gives "minimal API call" without re-introducing the payload duplication that the current single-row design avoids.

Not in scope for this PR — flagged here so the next data-layer change can target it.

### Future work — scheduled purge of closed versions

Soft-versioning means `BT.API_REQUEST` and `BT.API_REQUEST_PAYLOAD` accumulate closed rows (`TRANSACT_TO_TS < '9999-12-31'`) every time a user ticks *Refresh dataset*. The current schema has **no scheduled purge** — closed rows live until the partition is manually dropped. Two pieces of work are needed before automating this:

1. **Repartitioning by `TRANSACT_TO_TS`** (or a dedicated archive flag column) instead of `CREATED_AT`. The current `pg_partman` yearly partitions on `CREATED_AT` cleanly drop *all* versions written in a given year — both still-current and closed — which is wrong: we want to keep current rows regardless of age. Splitting current vs. closed into separate partition trees (or moving closed rows to an archive table on close) is required first.
2. **Retention policy + scheduler.** Decide how long closed versions are kept (e.g. 90 days for audit replay), then drive purges via `pg_cron` or an external scheduled job calling a new `BT.SP_PURGE_CLOSED_API_REQUESTS(retention_days)` procedure that does whole-partition `DROP` rather than per-row `DELETE`.

This is a meaningful chunk of work — partition migrations on a populated table need a careful online plan (`pg_partman` partition-add + data-copy + cutover). Tracking separately; the *Refresh dataset* checkbox above intentionally minimises closed-row creation in the meantime so the eventual migration has less to chew through.

### FastAPI integration

The FastAPI backend creates `BacktestCache` at startup (`api/main.py` lifespan). `_fetch_df` in `api/services/backtest.py` is the sole caller — it always routes through `get_or_fetch_payload` when `bt_cache` is wired, falling back to a direct provider call only when the DB is unavailable (e.g. unit tests).

### Partition maintenance

`API_REQUEST_PAYLOAD` is partitioned by `CREATED_AT` (yearly, via `pg_partman`). Purge path = `DROP TABLE <partition>`. No TTL policy yet — partitions grow until manually dropped. See the "Scheduled purge of closed versions" future-work section above for why automated dropping is non-trivial under the current partition key.

## Data Flow (after)

```
User selects:
  Trading symbol:  SPY
  Factor 1:        RSI on ^VIX (ticker="^VIX")   ← overridden
  Factor 2:        SMA on SPY  (ticker=None)      ← defaults to trading symbol

Backend:
  1. Collect unique tickers: {"SPY", "^VIX"}
  2. Fetch two DataFrames: {"SPY": df_spy, "^VIX": df_vix}
     (each goes through the two-mode `BacktestCache.get_or_fetch_payload` flow above)
  3. Compute RSI on df_vix, SMA on df_spy (same ref as trading)
  4. Reindex indicator values to df_spy's index
  5. Merge signals, run PnL on SPY prices
```

## Migration Plan

| Phase | Scope |
|-------|-------|
| **1** | **Python backend** — SubStrategy.ticker, Performance/ParamOpt accept `dict[str, DataFrame]`, main.py builds data dict |
| **2** | **API** — FactorConfig.symbol, service fetches unique symbols |
| **3** | **Database** — INST seed + procedures, BT ALTER (TICKER → PRODUCT_ID), SP_GET_* procedures |
| **4** | **Frontend** — Product dropdown, per-factor symbol override |
| **5** | Tests — unit + integration across all layers |

## Open Questions

1. ~~**Should `REFDATA.TICKER_MAPPING` be retired now or later?**~~ **Resolved**: Dropped via Liquibase changeset `116-refdata-drop-ticker-mapping`. `INST.PRODUCT_XREF` is the replacement.
2. **Walk-forward:** Currently single-symbol. Same `dict[str, DataFrame]` pattern applies?
3. **Seed data scope:** Start minimal (5–10 products) or bulk-load?
4. **Approval threshold:** What confidence score should allow auto-proposal without extra heuristics by asset class?
