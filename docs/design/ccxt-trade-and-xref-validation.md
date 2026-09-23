# Design: ccxt Trade Adapter & XREF Validation

!!! info "Status"
    **Partially implemented.** Phase 1.3 ccxt broker stack (`quant/trade/brokers/ccxt/`,
    registry, dry-run adapter path) is in the codebase. **Backend dry-run API**
    (`POST /api/v1/trade/deployments/dry-run`) is implemented. The exchange market catalog
    exists as the venue limits snapshot (see [Exchange market catalog](#exchange-market-catalog)).
    **Deferred:** deploy-time xref guards, xref seed workflow (ccxt-before-insert), Trade UI
    dry-run button, and ProductSelector — implement per phases below.

**Related:** [Plan to Profit §1.3](plan-to-profit.md#phase-13-bybit-adapter-dry-run),
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
| Exchange catalog | `quant/trade/venue_limits.py` — `RedisVenueLimits` | Listed symbols + order-size rules per broker app, from public `load_markets()` |
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
  config.py      # CCXT_PRESETS + CcxtVenue / BybitVenue (per-venue behaviour)
  egress.py      # EgressRoute / EgressRoutes — candidate routes from CCXT_EGRESS_<ID>
  routing.py     # KeyRouter — connects on the route the venue accepts the key from
  gateway.py     # CcxtTradeGateway — build exchange on a route, call venue.wire(), load_markets
  adapter.py     # CcxtTradeAdapter + create_ccxt_adapter()
```

### REFDATA.APP vs `CCXT_PRESETS` (two-layer config)

| Layer | Source | Holds |
|-------|--------|--------|
| **Identity** | `REFDATA.APP` (Postgres → Redis) | `app_id`, `name` (`bybit`), display, `IS_EXCHANGE_IND` |
| **ccxt wiring** | `CCXT_PRESETS` in `config.py` (code) | `exchange_id`, `default_type`, `venue` (a `CcxtVenue`) |

Registry joins them: `REFDATA.APP.NAME` → `CCXT_PRESETS[name]` → adapter factory
(`quant/trade/registry.py`).

**Venue behaviour is a class, not loose hooks.** `CcxtVenue` is what ccxt does
out of the box. A venue subclass overrides only the methods where it differs,
so the gateway calls `preset.venue.<method>()` with no per-venue branches:

| Method | `CcxtVenue` default | `BybitVenue` |
|---|---|---|
| `wire(exchange, params)` | Sandbox when `paper` | Also disables `fetchCurrencies`; demo uses Demo Trading |
| `auth_hint(params)` | `""` | Names testnet vs Demo Trading key mix-ups |
| `fetch_api_key_info(exchange)` | `None` (no such call) | `GET /v5/user/query-api` → `ApiKeyInfo` (allowlist, KYC region, read-only, expiry) |
| `classify_denial(exc)` | `None` | `retCode` 10010 → `IP_NOT_ALLOWED`, 10024 → `REGION_RESTRICTED` |

A key can only be routed on a venue whose `classify_denial` returns `IP_NOT_ALLOWED`: without it
there is no refusal to try another route on. A default venue therefore always uses its first
route, and `KeyRouter` logs a warning if `CCXT_EGRESS_<ID>` lists more than one.

**Why not store venue behaviour in REFDATA?** ccxt connect quirks (`has['fetchCurrencies']`,
`enable_demo_trading`, sandbox URLs) are library/version details — they belong in version-controlled
Python with unit tests, not SQL seeds. Adding a JSON column to `REFDATA.APP` would not improve
operability and would still require a deploy to change behaviour.

**Adding a broker:** seed a `REFDATA.APP` row and add one `CcxtExchangePreset` entry. Pass a
`CcxtVenue` subclass as `venue=` only if the venue differs from the defaults above.

```python
# config.py — dict key MUST match REFDATA.APP.NAME
CCXT_PRESETS = {
    "bybit": CcxtExchangePreset(..., venue=BybitVenue()),
    "binance": CcxtExchangePreset(...),  # default CcxtVenue()
}
```

`ConnectParams(paper=…, demo=…)` is passed to `venue.wire(exchange, params)` before
`load_markets()`. Bybit demo mode uses `demo=True` (not sandbox). The egress route is a
`connect(route)` argument, not session config, so one gateway serves whichever route
`KeyRouter` picks.

Live order paths are implemented in `quant/trade/brokers/ccxt/` and `quant/trade/live_apply.py`.

### Credential rejection is the caller's error, not a gateway failure

`load_markets()` is public, so a connection succeeds with any key at all; the
first *authenticated* call is where a wrong key surfaces. `_auth_error` raises
**`BrokerAuthError`** (400) and appends the venue's `auth_hint`, while
`BrokerConnectionError` (503) stays for a venue that is unreachable or erroring.
The split is retry semantics: one needs a new key, the other needs another tick.

This matters more than it looks because **paper mode is a different endpoint,
not a flag**. `BybitVenue.wire` calls `set_sandbox_mode(True)` when `paper=True`, so
a paper deployment authenticates against `testnet.bybit.com` and a mainnet key
is rejected there — which is precisely what `BybitVenue.auth_hint` says. Returning
that sentence as a 5xx classified a user's key mistake as a platform outage and
let a proxy substitute its own error page for the one message that named the
fix.

`demo` reaches `ConnectParams` but no caller sets it, so today `paper` always
means testnet rather than Bybit Demo Trading.

---

## Exchange market catalog

### Purpose

- Answer: “Does exchange X list symbol Y?” **without** user API keys or per-request HTTP.
- Catch stale/wrong `VENDOR_SYMBOL` in xref **before** deploy and **before** xref insert.
- Support admin tooling and UI product pickers filtered to tradable symbols.

### Use the venue limits snapshot; do not add a second catalog

This was originally designed as a separate `ExchangeMarketCache`. It was never
built: the venue limits cache ([decision #76](../decisions.md)) already
snapshots the same public `load_markets()` result into Redis, one entry per
broker app (`venue_limits:<app_id>`). The snapshot is keyed by vendor symbol, so
"is this symbol listed" is the same as "does the snapshot contain it". A second
cache would load the same data on its own schedule and could disagree with the
first.

Symbol validation should therefore extend `RedisVenueLimits` (e.g. a
`lists(app_id, vendor_symbol)` method) rather than add a new class on
`DataCaches`. Map `app_id` → preset via `REFDATA.APP.name` ∈ `CCXT_PRESETS`.
Non-ccxt brokers (Futu) skip this check.

**Mainnet only.** `VenueLimitsPublisher` snapshots the live venue
(`CcxtSessionConfig.public`), not testnet. A paper deployment on a
testnet-only symbol would fail this check. If that matters, add a
`paper` dimension to the snapshot key rather than a second cache.

---

## Venue caches: shared vs per user

Venue facts are cached in two separate caches, split by who the fact belongs to.
Neither holds the other's data.

| Scope | Cache | Key | Holds | Filled |
|---|---|---|---|---|
| Shared: same for every user of a venue | `RedisVenueLimits` (`quant/trade/venue_limits.py`) | `venue_limits:<app_id>` | Listed symbols, min lot, min notional | Keyless `load_markets()` at API startup and on refresh |
| Per user: one entry per API key | `RedisKeyProfiles` (`quant/trade/key_profiles.py`, broker-agnostic store) filled by `KeyRouter` (`quant/trade/brokers/ccxt/routing.py`) | `key_profile:<exchange>:<env>:<key fingerprint>` | Accepted egress route, IP allowlist, KYC region, read-only, expiry, refused products | That user's key, when a session connects; 1-day TTL |

Account facts must not go into the shared cache. They need the user's
credentials to read, they differ between users, and a user can change them at
the venue at any time.

Platform data stays out of both: products and xrefs are `InstrumentCache`
(Postgres INST). Balances and positions are not cached; `quant/trade/account.py`
reads them live. `CORE_ADMIN.API_CREDENTIAL` stores only the encrypted key pair.
See [Infrastructure: Per-key routing](../architecture/infrastructure.md#per-key-routing).

---

## XREF population workflow

Aligns with [Separate Underlying §3a.1](separate-underlying.md#3a1-product_xref-population-model):
proposal/approval before authoritative xref.

**Required order for ccxt brokers:**

1. Resolve target exchange preset (`bybit`, `binance`, …) and `paper` flag for testnet vs mainnet.
2. Refresh the venue limits snapshot (`POST /api/v1/trade/venue-limits/refresh`), or make a one-off CLI/admin `load_markets()` call.
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
4. [ccxt brokers only] venue_limits.lists(app_id, vendor_symbol)
5. SP_INS_DEPLOYMENT
```

Step 4 is skipped when the venue limits snapshot for that app is empty (venue unreachable at
startup). Policy: hard-fail vs warn — prefer hard-fail for ccxt deploys once the snapshot is
reliably populated.

### Dry-run (Phase 1.3 API — future)

```
1. Same xref + venue limits checks as deploy
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
  - xref `vendor_symbol` present in the venue limits snapshot for that app.
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
| **B** | Done as the venue limits cache (decision #76); add `RedisVenueLimits.lists` |
| **C** | ccxt gateway/adapter/registry (dry-run only) |
| **D** | `require_product_xref` + deploy guard (xref + market cache) |
| **E** | `POST /api/v1/trade/deployments/dry-run` + tests |
| **F** | Admin/CLI: validate vendor via ccxt → `SP_INS_PRODUCT_XREF` |
| **G** | Trade UI: ProductSelector with xref + market filter |

DDL xref seeds ship in **F** (or later), not before **B**/**F** verification.

---

## Testing

**Golden harness (manual, run first):** `scripts/bybit_local_testnet.py` — `python scripts/bybit_local_testnet.py --suite`. Documented in [Plan to Profit §1.3](plan-to-profit.md#phase-13-bybit-adapter-dry-run).

| Area | Tests |
|------|--------|
| `resolve_internal_cusip` | `tests/unit/test_data.py` |
| Venue limits snapshot | `tests/unit/test_venue_limits.py` (add membership when `lists` lands) |
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

1. Deploy hard-fail vs soft-fail when the venue limits snapshot is empty at startup.
2. Whether to add a `paper` dimension to the venue limits snapshot for testnet-only symbols.
3. Liquibase xref seeds require documented ccxt verification date/exchange in changeset comment.
