# Futu Trading — OOP Implementation Plan

!!! info "Status"
    **Design — not implemented.** A procedural prototype exists in `quant/futu_trader.py` (single class, ~275 lines). This document defines how to integrate Futu into the Plan-to-Profit trade pipeline using **strict OOP**, broker adapters, and the existing `TRADE.DEPLOYMENT` model.

**References**

| Source | Use |
|--------|-----|
| [Futu API — Program Samples](https://openapi.futunn.com/futu-api-doc/en/quick/demo.html) | Official `OpenSecTradeContext`, `TrdEnv.SIMULATE`, `unlock_trade` |
| [quincylin1/futubot](https://github.com/quincylin1/futubot) | Modular `Accounts` / `Robot` / `Portfolio` separation; paper vs live; pending-order guard |
| [GitHub topic: futu-api](https://github.com/topics/futu-api) | Ecosystem patterns (e.g. [billpwchan/futu_algo](https://github.com/billpwchan/futu_algo) for HK quant workflows) |
| [Trade API](trade-api.md) | `TradeAdapter`, deployment loop, risk checks |
| [Plan to Profit §1.1–1.7](plan-to-profit.md#phase-1--fastest-profit-pipeline) | Credentials, deployments, dry-run, live apply |

---

## 1. Goals

| Goal | Detail |
|------|--------|
| **Enable Futu live/paper trade** | HK / US / SG / JP equities via Futu OpenD — first broker adapter after deployments API |
| **Strict OOP** | Abstract interfaces, value objects, single-responsibility classes; **no** monolithic god-class or script-style loops in `quant/trade/` |
| **Fit existing architecture** | `REFDATA.APP` (`futu`, `APP_ID=3`), `TRADE.DEPLOYMENT`, `INST.PRODUCT_XREF` symbol mapping, `TradeService`, future trade worker |
| **Reuse backtest logic** | Signal path identical to [Trade API §6](trade-api.md#6-signal-execution-loop) — indicators from `quant/strategy/`, not reimplemented in the broker layer |
| **Safety** | Paper-first default; live requires unlock + explicit UI confirmation (Phase 1.7) |

**Out of scope for first cut**

- Intraday streaming dashboard (futubot-style Dash UI)
- Multi-stock basket robot in one process
- Replacing `quant/data/sources.py::FutuOpenD` quote path (keep quote vs trade contexts separate)

---

## 2. Current State

### 2.1 What exists

| Artifact | Location | Notes |
|----------|----------|--------|
| `FutuTrader` | `quant/futu_trader.py` | Procedural wrapper around `OpenSecTradeContext`; `place_order`, `apply_signal`, queries |
| Quote data | `quant/data/sources.py::FutuOpenD` | `OpenQuoteContext` — **separate** from trade context (matches Futu docs) |
| Deployments API | `quant/api/routers/deployments.py` | Persist strategy + `api_credential_id` + `app_id` |
| Trade domain | `quant/trade/service.py`, `db_repo.py` | DB only — no broker calls yet |
| Legacy scripts | `quant/trade/trade.py`, `source.py`, `repo.py` | Old Bybit/ccxt experiments — **do not extend**; delete or move to `backup/deco/` when Futu adapter lands |
| Unit / E2E tests | `tests/unit/test_trade.py`, `tests/e2e/test_futu_trader_e2e.py` | Target `quant.trade` exports — needs realignment after package refactor |

### 2.2 Futu OpenD model (from official docs)

Futu splits responsibilities into two programs ([Program Samples](https://openapi.futunn.com/futu-api-doc/en/quick/demo.html)):

```
┌─────────────┐     TCP (host:port)      ┌──────────────┐     ┌─────────────┐
│  Your app   │ ◄──────────────────────► │  FutuOpenD   │ ◄──►│ Futu servers│
│  (futu-api) │                          │  (gateway)   │     │             │
└─────────────┘                          └──────────────┘     └─────────────┘
```

Python SDK contexts:

| Context | Purpose | Our module |
|---------|---------|------------|
| `OpenQuoteContext` | Snapshots, klines, subscriptions | `FutuOpenD` (data) — already exists |
| `OpenSecTradeContext` | Orders, positions, account | **New** `FutuTradeGateway` (trade) |

Paper vs live is **`trd_env`**, not a separate host:

```python
# Official pattern (paper)
trd_ctx.place_order(..., trd_env=TrdEnv.SIMULATE)

# Live — requires unlock_trade(password) first
trd_ctx.unlock_trade(trade_password)
trd_ctx.place_order(..., trd_env=TrdEnv.REAL)
```

### 2.3 Lessons from futubot

[futubot](https://github.com/quincylin1/futubot) modularizes:

| Module | Responsibility | Quant Strategies equivalent |
|--------|----------------|----------------------------|
| `Accounts` | Raw Futu API encapsulation | `FutuTradeGateway` (SDK only) |
| `Robot` | Signal → order orchestration | `SignalExecutor` + `FutuAdapter` |
| `Portfolio` | Positions, PnL, metrics | `PositionReader` protocol + adapter method |
| `Strategy/` | Pluggable strategy files | `BT.STRATEGY` JSON + existing `Strategy` class |

**Behaviours to adopt**

- **Pending-order guard** — futubot skips new signals while orders are pending; map to `Duplicate guard` in [Trade API §4](trade-api.md#4-risk--safety).
- **Paper order type** — Futu paper often rejects market orders; default paper path to **limit** or `NORMAL` with computed price (document in adapter).
- **Market hours** — E2E and worker should no-op or defer outside session (configurable per market).

**Behaviours we skip**

- Real-time Dash dashboard
- HK-only assumption — we support US/HK/SG/JP via `filter_trdmarket` (already in `FutuTrader.MARKET_MAP`)

---

## 3. OOP Design

### 3.1 Principles

1. **Depend on abstractions** — workers and API call `TradeAdapter`, never `import futu` outside the Futu package.
2. **Thin SDK boundary** — one class (`FutuTradeGateway`) owns all `futu.*` imports and `(ret, data)` tuple handling.
3. **Immutable config** — `@dataclass(frozen=True)` for connection and order requests.
4. **Explicit results** — `OrderResult`, `ConnectionStatus` value objects; no silent `None` except “no action needed”.
5. **Composition** — `FutuAdapter` holds `FutuTradeGateway` + `FutuSymbolMapper`; does not subclass the SDK context.
6. **Factory registration** — `AdapterRegistry.get(app_id)` resolves `REFDATA.APP` → adapter class.

### 3.2 Layer diagram

```mermaid
flowchart TB
  subgraph app["Application layer"]
    API["deployments router"]
    Worker["trade worker / scheduler"]
    TS["TradeService"]
  end

  subgraph domain["Trade domain — quant/trade/"]
    EX["DeploymentExecutor"]
    RR["RiskRules"]
    AR["AdapterRegistry"]
  end

  subgraph abstractions["Abstractions — quant/trade/adapters/"]
    TA["TradeAdapter ABC"]
    BR["BrokerSession ABC"]
  end

  subgraph futu_pkg["Futu broker — quant/trade/brokers/futu/"]
    FA["FutuAdapter"]
    GW["FutuTradeGateway"]
    MAP["FutuSymbolMapper"]
    CFG["FutuSessionConfig"]
  end

  subgraph external["External"]
    OpenD["FutuOpenD"]
    DB["PostgreSQL TRADE.*"]
  end

  API --> TS
  Worker --> EX
  EX --> RR
  EX --> AR
  AR --> FA
  FA --> TA
  FA --> GW
  FA --> MAP
  GW --> OpenD
  TS --> DB
  EX --> DB
```

### 3.3 Package layout (target)

```
quant/trade/
├── __init__.py              # public exports: TradeService, AdapterRegistry, …
├── service.py               # existing — deployments CRUD
├── db_repo.py               # existing
├── errors.py                # existing + BrokerError, ConnectionError
├── executor.py              # NEW — DeploymentExecutor (signal → risk → adapter)
├── registry.py              # NEW — AdapterRegistry(app_id → TradeAdapter)
├── adapters/
│   ├── __init__.py
│   ├── base.py              # TradeAdapter, BrokerSession ABCs
│   └── protocols.py         # PositionReader, OrderPlacer (optional typing.Protocol)
├── models/
│   ├── __init__.py
│   ├── order.py             # OrderSide, OrderType, OrderRequest, OrderResult
│   └── session.py           # BrokerSessionState, ConnectionConfig
└── brokers/
    └── futu/
        ├── __init__.py
        ├── config.py        # FutuSessionConfig(frozen dataclass)
        ├── gateway.py       # FutuTradeGateway — sole futu import site
        ├── mapper.py        # internal_cusip → Futu code via INST.PRODUCT_XREF
        └── adapter.py       # FutuAdapter(TradeAdapter)
```

**Migration:** Move logic from `quant/futu_trader.py` into `brokers/futu/*`, then delete `futu_trader.py` and update imports/tests. Keep a one-release shim only if needed — project convention is **no backward-compat shims**.

### 3.4 Abstract interfaces

```python
# quant/trade/adapters/base.py
from abc import ABC, abstractmethod
from quant.trade.models.order import OrderRequest, OrderResult
from quant.trade.models.session import BrokerSessionState


class BrokerSession(ABC):
    """Lifecycle: connect → (optional unlock) → use → disconnect."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> BrokerSessionState: ...

    def __enter__(self) -> "BrokerSession":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()


class TradeAdapter(BrokerSession):
    """Broker-agnostic trading surface for the execution loop."""

    @abstractmethod
    def unlock_live_trading(self, trade_password: str) -> None:
        """Required for REAL env; no-op or skip for paper."""

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, vendor_order_id: str) -> OrderResult: ...

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_position_qty(self, symbol: str) -> int: ...

    @abstractmethod
    def apply_signal(self, symbol: str, signal: float, qty: int) -> OrderResult | None:
        """Translate {-1,0,1} signal to orders; None if no action."""
```

`TradeAdapter` extends `BrokerSession` so the worker can use `with adapter:` uniformly.

### 3.5 Futu concrete classes

#### `FutuSessionConfig` (frozen dataclass)

| Field | Source | Notes |
|-------|--------|-------|
| `host` | `.env` `FUTU_HOST` or deployment infra | OpenD is **per host**, not per user in v1 |
| `port` | `.env` `FUTU_PORT` | Default `11111` |
| `market` | `TrdMarket` from symbol prefix or deployment | `US`, `HK`, … |
| `paper` | `TRADE.DEPLOYMENT.is_paper_ind` | Maps to `TrdEnv.SIMULATE` / `REAL` |
| `trade_password` | Decrypted credential (live only) | See §4 |

#### `FutuTradeGateway`

Single class that wraps `OpenSecTradeContext`:

| Method | SDK call | Returns |
|--------|----------|---------|
| `connect()` | `OpenSecTradeContext(host, port, filter_trdmarket=…)` | — |
| `disconnect()` | `ctx.close()` | — |
| `unlock(password)` | `unlock_trade(password)` | raises `FutuApiError` if `ret != 0` |
| `place_order(req)` | `place_order(price, qty, code, trd_side, order_type, trd_env)` | `OrderResult` |
| `cancel_order(id)` | `modify_order(CANCEL, …)` | `OrderResult` |
| `list_orders()` | `order_list_query(trd_env=…)` | `list[OrderSnapshot]` |
| `list_positions()` | `position_list_query(trd_env=…)` | `list[PositionSnapshot]` |
| `account_info()` | `accinfo_query(trd_env=…)` | `AccountSnapshot` |

**Error handling:** Private `_call(ret, data)` raises `FutuApiError(ret, data)` — never leak raw tuples upward.

#### `FutuSymbolMapper`

| Input | Output |
|-------|--------|
| `internal_cusip` + `app_id=3` | Futu code e.g. `US.AAPL` |

Query `INST.PRODUCT_XREF` where vendor = futu (same pattern as Bybit Phase 1.3). Fail fast with `SymbolMappingError` if xref missing.

#### `FutuAdapter`

Implements `TradeAdapter`:

- Constructs `FutuTradeGateway` from `FutuSessionConfig`
- Delegates all SDK calls to gateway
- Implements `apply_signal` (port from current `FutuTrader.apply_signal` with pending-order check)
- **Paper order policy:** if `paper` and market order rejected, retry as limit at last snapshot price (optional strategy — document in adapter docstring)

### 3.6 Value objects

```python
# quant/trade/models/order.py
from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str          # broker-native, e.g. US.AAPL
    qty: int
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None


@dataclass(frozen=True)
class OrderResult:
    success: bool
    vendor_order_id: str | None
    message: str
    raw_status: str | None = None   # e.g. SUBMITTED, FILLED
```

---

## 4. Credentials & Multi-Account

Futu differs from Bybit: authentication is **OpenD session + trade password**, not REST API key/secret.

| Concern | Bybit (Phase 1.1) | Futu (this doc) |
|---------|-------------------|-----------------|
| Secret material | `api_key` + `api_secret` | **Trade unlock password** (live); paper may omit |
| Gateway | Public REST | Local **OpenD** (`FUTU_HOST`/`FUTU_PORT`) |
| Multi-account | Multiple `API_CREDENTIAL_ID` per `APP_ID` | Multiple Futu accounts under one OpenD login — use **label** + optional `acc_id` in future |

**Recommended v1 mapping to `CORE_ADMIN.API_CREDENTIAL`**

| Column | Futu usage |
|--------|------------|
| `APP_ID` | `3` (`REFDATA.APP` name `futu`) |
| `LABEL` | User label ("HK main", "US IRA") |
| `API_KEY_CIPHERTEXT` | Unused or store OpenD `acc_id` if needed |
| `API_SECRET_CIPHERTEXT` | Fernet-encrypted **trade password** (live unlock) |
| `IS_PAPER_IND` | `Y` = always `TrdEnv.SIMULATE` |

OpenD host/port remain **infrastructure** (`.env` / SSM on trade worker host), not per-user credential rows — unless you run OpenD per user (unlikely).

**Decision to log:** extend Phase 1.1 credential schema doc vs add `CONFIG_JSON` on credential for broker-specific fields (`acc_id`, `security_firm`). Record in [decisions.md](../decisions.md) when chosen.

---

## 5. Execution Flow

### 5.1 Dry run (Phase 1.3 analogue for Futu)

```
POST /api/v1/trade/deployments/{id}/dry-run   # future endpoint
```

1. Load deployment + strategy JSON + credential (masked check only).
2. Resolve symbol via `FutuSymbolMapper`.
3. `with FutuAdapter(...) as adapter:` — **no unlock** if paper.
4. Run signal loop in memory (fetch data via existing backtest data path or `FutuOpenD` quote).
5. Return report: `{ signal, intended_side, qty, symbol, errors[] }` — **no** `place_order`.

### 5.2 Live apply tick (worker)

Align with [Trade API §6](trade-api.md#6-signal-execution-loop):

```python
# quant/trade/executor.py (sketch)
class DeploymentExecutor:
    def __init__(self, repo: TradeRepo, registry: AdapterRegistry, risk: RiskRules):
        self._repo = repo
        self._registry = registry
        self._risk = risk

    def run_tick(self, deployment_id: UUID, app_user_id: UUID) -> None:
        dep = self._repo.sp_get_deployment(...)
        strategy = load_strategy(dep.strategy_id, dep.strategy_vid)
        adapter = self._registry.create(dep.app_id, dep.api_credential_id, dep)
        symbol = self._mapper.to_vendor_symbol(dep.internal_cusip, dep.app_id)

        with adapter:
            if dep.is_paper_ind == "N":
                adapter.unlock_live_trading(trade_password)
            signal = compute_signal(strategy)          # existing TA / Strategy code
            if not self._risk.passes(dep, signal):
                self._repo.sp_ins_execution_event(..., BUY_SELL_CD="REJECTED")
                return
            result = adapter.apply_signal(symbol, signal, int(dep.qty))
            self._repo.sp_ins_execution_event(...)
            if result and result.success:
                self._repo.sp_ins_transaction(...)     # when fill confirmed
```

### 5.3 UI integration (Phase 1.5–1.7)

Already scaffolded:

- Config toolbar: Exchange / Account / Paper|Live filters
- Deployments table: Exchange + Account columns

When Futu is enabled:

1. User registers Futu credential on Config (label + trade password, paper flag).
2. User creates deployment with `app_id=3`, `internal_cusip` → xref → `US.*` / `HK.*`.
3. Dry run → Apply on Trade page calls executor path above.

---

## 6. REFDATA & INST Wiring

| Lookup | Value |
|--------|-------|
| `REFDATA.APP` | `NAME='futu'`, `CLASS_NAME='FutuOpenD'`, `APP_ID=3` |
| `AdapterRegistry` | Register `3 → FutuAdapter` at worker/API startup |
| `INST.PRODUCT_XREF` | Map `internal_cusip` → `US.AAPL`, `HK.00700`, … |

Seed xref rows for instruments you intend to trade before dry-run.

---

## 7. Implementation Phases

Work in order; each phase has testable exit criteria.

### Phase A — Package skeleton (no behaviour change)

| Task | Exit |
|------|------|
| Create `adapters/`, `models/`, `brokers/futu/` per §3.3 | `pytest` imports succeed |
| Move `OrderResult` to `models/order.py` | Unit tests updated |
| Port `FutuTrader` logic → `FutuTradeGateway` + `FutuAdapter` | Existing `test_trade.py` green against new paths |
| Delete `quant/futu_trader.py` | No stale imports |

### Phase B — Registry + mapper

| Task | Exit |
|------|------|
| `AdapterRegistry.register(3, FutuAdapter)` | Factory returns adapter for futu `app_id` |
| `FutuSymbolMapper` + INST xref query | Unit test: cusip → `US.WEAT` |
| `FutuApiError` → `TradeValidationError` at API boundary | Consistent HTTP 400/502 |

### Phase C — Executor + dry-run

| Task | Exit |
|------|------|
| `DeploymentExecutor.run_tick` (paper only) | E2E: deployment row → simulated order path |
| `GET/POST …/dry-run` endpoint | UI Dry run button enabled for Futu |
| Pending-order guard in `apply_signal` | Unit test: skips when open orders exist |

### Phase D — Persistence + UI

| Task | Exit |
|------|------|
| Wire `sp_ins_execution_event` / `sp_ins_transaction` on order result | Row appears after apply |
| Phase 1.1 credential API for Futu password | Config save → masked reload |
| Trade Apply button (paper) | End-to-end paper order on OpenD |

### Phase E — Live + ops

| Task | Exit |
|------|------|
| Live unlock + confirmation gate | Cannot apply live without explicit confirm |
| Rate-limit wrapper on gateway (futubot lesson) | Logs + backoff on Futu frequency errors |
| Docker OpenD note (optional) | Document [timontr/docker-futuopend](https://github.com/timontr/docker-futuopend) for headless EC2 if needed |

---

## 8. Testing Strategy

| Layer | Approach |
|-------|----------|
| **Unit** | Mock `FutuTradeGateway`; test `FutuAdapter.apply_signal` matrix (long/short/flat, existing position) |
| **Gateway** | Mock `OpenSecTradeContext` methods; assert `(ret, data)` handling |
| **Integration** | `tests/e2e/test_futu_trader_e2e.py` — real OpenD, `TrdEnv.SIMULATE`, skip if `FUTU_HOST` unset |
| **Registry** | `AdapterRegistry.create(3, …)` with fake credential repo |

Keep E2E **paper only** in CI; live unlock tests manual.

---

## 9. Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `FUTU_HOST` | Yes (trade host) | OpenD bind address — usually `127.0.0.1` dev |
| `FUTU_PORT` | Yes | Default `11111` |
| Trade password | Live only | From credential decrypt — **never** log or return in API |

Prod: OpenD runs on trade worker EC2; API container talks to OpenD via host network or sidecar. See [phase-0.3 topology](../archive/phase-0/phase-0.3-topology.md).

---

## 10. Comparison: futubot vs this design

| futubot | Quant Strategies |
|---------|------------------|
| Config file (`futubot_config.py`) | `TRADE.DEPLOYMENT` + `BT.STRATEGY` JSON in DB |
| Intraday loop in `Robot` | Worker scheduler + `DeploymentExecutor` |
| Indicators module | Reuse `quant/strategy/` + `TechnicalAnalysis` |
| `StockFrame` pandas state | Transient DataFrame per tick; no separate frame class unless profiling shows need |
| Dash dashboard | React Trade tab + execution log (Phase 1.8) |
| Strategy folder per `.py` file | Strategy identity = `strategy_id` UUID from backtest |

---

## 11. Open Decisions

| # | Question | Options |
|---|----------|---------|
| 1 | Futu credential shape in `API_CREDENTIAL` | Trade password only vs `CONFIG_JSON` with `acc_id` |
| 2 | OpenD on EC2 | Desktop GUI vs Docker OpenD vs SSH tunnel from dev |
| 3 | Paper order type default | Limit-at-last vs market-with-fallback |
| 4 | Short selling | `apply_signal(-1)` — US/HK margin rules; may restrict to long-only v1 |
| 5 | Legacy `quant/trade/trade.py` | Delete vs move to `backup/deco/` |

Record resolutions in [decisions.md](../decisions.md).

---

## 12. Related Docs

| Doc | Relevance |
|-----|-----------|
| [Paper Trading guide](../guides/trading.md) | User-facing OpenD setup (update imports after Phase A) |
| [Trade API](trade-api.md) | Adapter interface, risk checks, DB schema |
| [Plan to Profit](plan-to-profit.md) | Phase 1.1 credentials, 1.3 dry-run, 1.7 live apply |
| [Database](../architecture/database.md) | `TRADE.*`, `CORE_ADMIN.API_CREDENTIAL` |
| [Pipeline](../architecture/pipeline.md) | Data vs trade separation |

---

## 13. Success Criteria

**Futu trade is “enabled” when:**

1. `AdapterRegistry` resolves `app_id=3` to `FutuAdapter`.
2. User with a Futu credential and deployment can **dry-run** and see intended signal/side/qty.
3. **Paper apply** places an order via OpenD (`TrdEnv.SIMULATE`) and writes `TRADE.EXECUTION_EVENT`.
4. All Futu SDK imports live under `quant/trade/brokers/futu/` only.
5. Unit tests cover adapter + executor; E2E covers OpenD paper path when gateway is available.

That satisfies the Futu slice of **M1 — Pipeline** alongside Bybit (Phase 1.3).
