# Design: ccxt Trade Adapter & XREF Validation

!!! info "Status"
    **Partially implemented.** Phase 1.3 ccxt broker stack (`quant/trade/brokers/ccxt/`,
    registry, dry-run adapter path) is in the codebase. **Backend dry-run API**
    (`POST /api/v1/trade/deployments/dry-run`) is implemented. **Deferred:** deploy-time xref
    guards, `ExchangeMarketCache`, xref seed workflow (ccxt-before-insert), Trade UI dry-run
    button, and ProductSelector — implement per phases below.

**Related:** [Plan to Profit §1.3](plan-to-profit.md#phase-13--bybit-adapter-dry-run),
[Trade API](trade-api.md), [Trade Deployment Rollout](trade-deployment-rollout.md),
[Separate Underlying §3a.1](separate-underlying.md#3a1-product_xref-population-model).

---

## Problem

1. **Phase 1.3** needs ccxt-based brokers (Bybit, Binance, …) with a dry-run path — no live orders.
2. **`INST.PRODUCT_XREF`** maps platform `internal_cusip` → exchange-native `vendor_symbol`.
3. **Risk:** inserting or trusting xref rows **before** confirming the vendor symbol exists on the
   exchange leads to bad deploys and silent mismatches (e.g. `BTCUSDT` vs `BTC/USDT:USDT`).
4. **User input:** Trade UI currently allows free-text `internal_cusip`; typos and wrong products
   must fail fast with clear errors.

**Principle:** Validate vendor symbols against **ccxt `load_markets()` first**, then persist xref
rows. Runtime checks use cached market catalogs + INST data — not live ccxt on every HTTP request.

---

## Layering (do not mix concerns)

| Layer | Module (proposed) | Responsibility |
|-------|-------------------|----------------|
| INST read | `quant/data/instruments.py` — `InstrumentCache` | Postgres snapshot: products, xrefs |
| INST resolve | `InstrumentCache.resolve_internal_cusip(cusip, app_id)` | `(cusip, app_id) → vendor_symbol \| None` |
| Exchange catalog | `quant/trade/brokers/ccxt/markets.py` — `ExchangeMarketCache` | In-memory ccxt market ids per `(exchange_id, paper)` |
| Trade policy | `quant/trade/xref.py` — `require_product_xref(...)` | Raise `SymbolMappingError` when lookup fails |
| Live position | `quant/strategy/live_service.py` — `compute_latest_position` | Rolling lookback + fresh bars → latest position |
| Broker I/O | `quant/trade/brokers/ccxt/` — gateway + adapter | Connect, balance, positions; dry-run |
| Registry | `quant/trade/registry.py` | `REFDATA.APP` name → ccxt preset → adapter factory |

**Do not** put ccxt market data inside `InstrumentCache` — different source, refresh cadence, and
failure mode (HTTP vs DB).

**Do not** insert `PRODUCT_XREF` seed/migration rows until the vendor symbol passes ccxt validation
(see [XREF population workflow](#xref-population-workflow)).

---

## ccxt broker stack (Phase 1.3)

Single shared implementation; no per-exchange wrapper packages.

```
quant/trade/brokers/ccxt/
  config.py      # CCXT_PRESETS + wire hooks (paper/demo/sandbox per exchange)
  gateway.py     # CcxtTradeGateway — build exchange, call preset.wire(), load_markets
  adapter.py     # CcxtTradeAdapter + create_ccxt_adapter()
  markets.py     # ExchangeMarketCache — public load_markets, no API keys (deferred)
```

### REFDATA.APP vs `CCXT_PRESETS` (two-layer config)

| Layer | Source | Holds |
|-------|--------|--------|
| **Identity** | `REFDATA.APP` (Postgres → Redis) | `app_id`, `name` (`bybit`), display, `IS_EXCHANGE_IND` |
| **ccxt wiring** | `CCXT_PRESETS` in `config.py` (code) | `exchange_id`, `default_type`, `wire()`, `auth_hint()` |

Registry joins them: `REFDATA.APP.NAME` → `CCXT_PRESETS[name]` → adapter factory
(`quant/trade/registry.py`).

**Why not store wire hooks in REFDATA?** ccxt connect quirks (`has['fetchCurrencies']`,
`enable_demo_trading`, sandbox URLs) are library/version details — they belong in version-controlled
Python with unit tests, not SQL seeds. Adding a JSON column to `REFDATA.APP` would not improve
operability and would still require a deploy to change behaviour.

**Adding a broker:** seed `REFDATA.APP` row + add one `CcxtExchangePreset` entry (custom `wire` if
not default sandbox). Optional: custom `auth_hint` for clearer credential errors.

```python
# config.py — dict key MUST match REFDATA.APP.NAME
CCXT_PRESETS = {
    "bybit": CcxtExchangePreset(..., wire=_wire_bybit, auth_hint=_bybit_auth_hint),
    "binance": CcxtExchangePreset(...),  # default _wire_paper_sandbox
}
```

`ConnectParams(paper=…, demo=…)` is passed to `preset.wire(exchange, params)` before
`load_markets()`. Bybit demo mode uses `demo=True` (not sandbox).

Live order paths are implemented in `quant/trade/brokers/ccxt/` and `quant/trade/live_apply.py`.

---

## Exchange market cache

### Purpose

- Answer: “Does exchange X list symbol Y?” **without** user API keys or per-request HTTP.
- Catch stale/wrong `VENDOR_SYMBOL` in xref **before** deploy and **before** xref insert.
- Support admin tooling and UI product pickers filtered to tradable symbols.

### Shape

Hang off `DataCaches` (sibling to `instrument_cache`):

```python
class DataCaches:
    refdata: RedisRefData
    instrument_cache: InstrumentCache
    backtest_cache: BacktestCache
    exchange_market_cache: ExchangeMarketCache   # new
```

### Cache key

`(exchange_id, paper)` — sandbox and mainnet catalogs differ (`set_sandbox_mode(True)` for paper).

### Load (public, no credentials)

```python
def load_market_ids(preset: CcxtExchangePreset, *, paper: bool) -> frozenset[str]:
    exchange_cls = getattr(ccxt, preset.exchange_id)
    ex = exchange_cls({"enableRateLimit": True, **options})
    if paper:
        ex.set_sandbox_mode(True)
    ex.load_markets()
    return frozenset(ex.markets.keys())
```

Membership check should mirror gateway logic: direct key lookup, then `exchange.market(symbol)`
for unified/alternate ids.

### Refresh

- API startup (soft-fail if exchange unreachable — log warning; deploy may xref-only until refresh).
- `POST /api/v1/trade/markets/refresh` (or combined admin refresh).
- Optional TTL later; manual refresh is enough for M1.

### Usage

```python
vendor = inst_cache.resolve_internal_cusip(cusip, app_id)
if vendor is None:
    raise SymbolMappingError(...)
if not market_cache.has_market(app_id, paper, vendor):
    raise SymbolMappingError(f"{vendor!r} not listed on {exchange_label}")
```

Map `app_id` → preset via `REFDATA.APP.name` ∈ `CCXT_PRESETS`. Non-ccxt brokers (Futu) skip this
check.

---

## XREF population workflow

Aligns with [Separate Underlying §3a.1](separate-underlying.md#3a1-product_xref-population-model):
proposal/approval before authoritative xref.

**Required order for ccxt brokers:**

1. Resolve target exchange preset (`bybit`, `binance`, …) and `paper` flag for testnet vs mainnet.
2. Load ccxt markets (public) into `ExchangeMarketCache` or one-off CLI/admin call.
3. **Verify** candidate `vendor_symbol` ∈ market set (and optionally fetch ticker for smoke test).
4. Only then call `INST.SP_INS_PRODUCT_XREF` (or approved Liquibase seed after manual verification).

**Adding a second ccxt broker (e.g. Binance after Bybit):** insert another xref on the **same**
`PRODUCT_ID` with the new `APP_ID` — do **not** create `btcusdt.binance` as a separate product.
See decision [#21 INTERNAL_CUSIP](../decisions.md) and [database.md §INTERNAL_CUSIP](../architecture/database.md#internal_cusip-convention).

**Anti-pattern (do not do):**

```sql
-- BAD: seed xref in Liquibase without ccxt verification
INSERT INTO INST.PRODUCT_XREF (..., 'BTCUSDT', ...);
```

**Preferred:**

- Admin script or future `INST.PRODUCT_XREF_PROPOSAL` queue: ccxt-validated proposals → approve → SP.
- Liquibase seeds only for symbols **already verified** against testnet/mainnet and documented in
  the changeset comment.

---

## Runtime validation flows

### Deploy create (`POST /api/v1/trade/deployments`)

```
1. Pydantic: strip internal_cusip, qty > 0, …
2. TradeRepo: credential active, app_id match, strategy ownership
3. require_product_xref(inst_cache, internal_cusip, app_id)  → vendor_symbol
4. [ccxt brokers only] market_cache.has_market(app_id, paper, vendor_symbol)
5. SP_INS_DEPLOYMENT
```

Step 4 is optional if market cache failed to load at startup (policy: hard-fail vs warn — prefer
hard-fail for ccxt deploys once cache is operational).

### Dry-run (Phase 1.3 API — future)

```
1. Same xref + market cache checks as deploy
2. Decrypt credentials; CcxtTradeAdapter.connect()
3. validate_credentials() — balance fetch
4. market_exists(vendor_symbol) on live connection (redundant if cache fresh)
5. Compute signal; return DryRunReport (no orders)
```

Dry-run remains mandatory before live apply (Phase 1.7).

### Backtest data fetch

Keep **soft fallback**: if `resolve_internal_cusip` returns `None`, use symbol as raw ticker
(backtest allows non-INST symbols). **Do not** hard-fail backtest on missing xref.

---

## User input (Trade UI)

Today `DeploymentDialog` uses a free-text **Product (internal cusip)** field.

**Target UX:**

- Reuse `ProductSelector` (dropdown from `GET /api/v1/inst/products`).
- Filter products to those with:
  - a current xref for the selected account’s `app_id`, **and**
  - xref `vendor_symbol` ∈ `ExchangeMarketCache` for that exchange + paper mode.
- Pre-fill from strategy `config_json.symbol` but restrict changes to valid options.
- Normalize cusip: `.strip().lower()` in API validator (canonical form per decision #21).

Wrong free-text entry outcomes (server-side):

| Input | Error |
|-------|--------|
| Unknown cusip | `unknown product internal_cusip=…` (400) |
| Missing xref for broker | `no INST.PRODUCT_XREF for … app_id=…` (400) |
| Xref vendor not on exchange | `vendor symbol … not listed on Bybit` (400) |

---

## Implementation phases (suggested)

| Phase | Deliverable |
|-------|-------------|
| **A** | `InstrumentCache.resolve_internal_cusip`; backtest uses it |
| **B** | `ExchangeMarketCache` + startup load + refresh endpoint |
| **C** | ccxt gateway/adapter/registry (dry-run only) |
| **D** | `require_product_xref` + deploy guard (xref + market cache) |
| **E** | `POST /api/v1/trade/deployments/dry-run` + tests |
| **F** | Admin/CLI: validate vendor via ccxt → `SP_INS_PRODUCT_XREF` |
| **G** | Trade UI: ProductSelector with xref + market filter |

DDL xref seeds ship in **F** (or later), not before **B**/**F** verification.

---

## Testing

**Golden harness (manual, run first):** [`scripts/bybit_local_testnet.py`](../../scripts/bybit_local_testnet.py) — `python scripts/bybit_local_testnet.py --suite`. Documented in [Plan to Profit §1.3](plan-to-profit.md#phase-13--bybit-adapter-dry-run).

| Area | Tests |
|------|--------|
| `resolve_internal_cusip` | `tests/unit/test_data.py` |
| `ExchangeMarketCache` | mock ccxt `load_markets`; membership |
| `require_product_xref` | unknown cusip, missing xref |
| Deploy validation | `tests/unit/test_trade_db_repo.py` |
| ccxt adapter dry-run | `tests/unit/test_bybit_adapter.py`, `tests/unit/test_dry_run_service.py` |
| Integration (e2e, optional) | `tests/integration/test_ccxt_dry_run.py` — mirrors `--suite` gateway + dry-run; `-m e2e` only |

---

## Out of scope (this design)

- Live order placement (Phase 1.7) — see [Live Order Execution](live-order-execution.md)
- Futu adapter (separate [Futu Trading](futu-trading.md))
- `INST.PRODUCT_XREF_PROPOSAL` table (future; see separate-underlying)
- Automatic xref discovery from exchange feeds without approval

---

## Decisions to log when implemented

1. Deploy hard-fail vs soft-fail when `ExchangeMarketCache` is empty at startup.
2. Cache paper vs live catalogs separately — always match deployment `paper` flag.
3. Liquibase xref seeds require documented ccxt verification date/exchange in changeset comment.
