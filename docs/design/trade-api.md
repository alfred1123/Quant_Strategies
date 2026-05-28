# Design Doc: Strategy JSON → Trade API

!!! info "Status"
    **Partially implemented (Phase 1.2).** Deployment persistence and `GET`/`POST /api/v1/trade/deployments` are live. Credentials API, broker adapters, dry-run, and execution-log writes are still planned. A `FutuTrader` utility exists in `quant/trade/futu_trader.py` (see [Paper Trading guide](../guides/trading.md)).

!!! warning "Schema accuracy"
    §7 (DB Schema) is the **reference** for table DDL. The JSON examples in §1.2 and the pseudocode in §6 are **aspirational** — they show the target design, not what is implemented today. Always cross-check against the Liquibase DDL in `db/liquidbase/trade/tables/`.

## Overview

Enable one-click deployment of a backtested strategy to a separate algo trading system.
The backtest pipeline produces a **Strategy JSON** that carries everything needed to
execute the strategy live: indicator config, signal logic, parameters, and deployment
metadata. The Trade API consumes this JSON and manages autonomous execution.

```
┌─────────────┐    Strategy JSON    ┌──────────────┐    Orders     ┌──────────┐
│  Backtest    │ ──────────────────► │  Trade API   │ ────────────► │ Exchange │
│  (app.py /   │                    │  (algo       │ ◄──────────── │ (Futu /  │
│   main.py)   │                    │   system)    │    Fills      │  Bybit)  │
└─────────────┘                    └──────────────┘               └──────────┘
       │                                  │
       │  Backtest Results                │  Execution Log
       ▼                                  ▼
  ┌──────────┐                      ┌──────────┐
  │    DB    │ ◄────────────────── │    DB    │
  └──────────┘   strategy_id FK    └──────────┘
```

---

## 1. Strategy JSON Schema

Two top-level objects: `StrategyConfig` (what to compute) and `DeploymentConfig`
(where to trade). They are separate concerns but linked by a shared `strategy_id`.

### 1.1 StrategyConfig (backtest identity)

```json
{
  "strategy_id": "auto-generated-uuid",
  "name": "bollinger_momentum_20_1.0",
  "version": 1,
  "created_at": "2026-04-05T12:00:00Z",
  "ticker": "BTC-USD",
  "conjunction": "AND",
  "trading_period": 365,
  "substrategies": [
    {
      "id": 1,
      "indicator": "get_bollinger_band",
      "signal_func": "momentum_band_signal",
      "window": 20,
      "signal": 1.0,
      "data_column": "v"
    },
    {
      "id": 2,
      "indicator": "get_rsi",
      "signal_func": "reversion_band_signal",
      "window": 14,
      "signal": 30.0,
      "data_column": "v"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `strategy_id` | string (UUID) | Unique identifier, auto-generated |
| `name` | string | Human-readable name; auto-generated from indicator+strategy if empty |
| `version` | int | Incremented on parameter changes; original preserved for audit |
| `ticker` | string | Data-source symbol the strategy was backtested on (e.g. `"BTC-USD"`, `"AAPL"`). Broker-specific symbols live in DeploymentConfig; mapping stored in `INST.PRODUCT_XREF`. |
| `conjunction` | `"AND"` \| `"OR"` | How substrategy positions combine (flat enum for now) |
| `trading_period` | int | 365 (crypto) or 252 (equity) — for annualization |
| `substrategies` | array | 1–2 substrategy objects (expandable later) |

Each substrategy:

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Ordering key (1-indexed) |
| `indicator` | string | `TechnicalAnalysis` method name |
| `signal_func` | string | `SignalDirection` static method name (serialized as string, resolved at runtime) |
| `window` | int | Indicator lookback period |
| `signal` | float | Signal threshold |
| `data_column` | string | Source data column to use as `factor` |

### 1.2 DeploymentConfig (trading target)

**Implemented** — `CreateDeploymentRequest` in `quant/schemas/deployments.py`.
DDL: `db/liquidbase/trade/tables/DEPLOYMENT.sql` (soft-versioned).

```json
{
  "deployment_id": "auto-generated-uuid (optional, server generates if omitted)",
  "strategy_id": "links-to-strategy-config",
  "strategy_vid": 1,
  "api_credential_id": 42,
  "app_id": 2,
  "internal_cusip": "BTC-USD",
  "qty": 100,
  "paper": true,
  "enabled": true,
  "deployment_status": "CREATED"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `deployment_id` | UUID (optional) | Unique deployment instance; auto-generated if omitted |
| `strategy_id` | UUID | FK → `BT.STRATEGY` |
| `strategy_vid` | int | Pinned strategy version |
| `api_credential_id` | int | FK → `CORE_ADMIN.API_CREDENTIAL` — links exchange account |
| `app_id` | int | FK → `REFDATA.APP` — broker identity (e.g. 2=bybit, 3=futu) |
| `internal_cusip` | string | Platform-internal product ID; mapped to vendor symbol via `INST.PRODUCT_XREF` |
| `qty` | numeric | Position size per signal |
| `paper` | bool | Paper / testnet (`IS_PAPER_IND` = Y/N) |
| `enabled` | bool | Kill switch (`IS_ENABLED_IND` = Y/N) |
| `deployment_status` | string | `CREATED`, `ACTIVE`, `PAUSED`, `STOPPED` |

**Not yet implemented** (planned extensions to `TRADE.DEPLOYMENT`):

| Field | Purpose |
|-------|---------|
| `schedule` | When to evaluate: `daily_close`, `hourly`, `manual` |
| `risk_limits_json` | Safety guardrails (see §4) — `max_position_usd`, `max_daily_trades`, `stop_loss_pct` |
| `portfolio` | Portfolio grouping label |
| `market` | Market code (US, HK) — currently inferred from `internal_cusip` |

### 1.3 BacktestResults (stored alongside strategy)

```json
{
  "strategy_id": "links-to-strategy-config",
  "run_at": "2026-04-05T12:00:00Z",
  "data_range": {"start": "2016-01-01", "end": "2026-04-01"},
  "ticker_backtested": "BTC-USD",
  "fee_bps": 5.0,
  "metrics": {
    "total_return": 1.45,
    "annualized_return": 0.12,
    "sharpe_ratio": 1.35,
    "max_drawdown": 0.23,
    "calmar_ratio": 0.52
  },
  "buy_hold_metrics": {
    "total_return": 2.10,
    "annualized_return": 0.18,
    "sharpe_ratio": 0.85,
    "max_drawdown": 0.55,
    "calmar_ratio": 0.33
  },
  "walk_forward": {
    "best_window": 20,
    "best_signal": 1.0,
    "is_sharpe": 1.50,
    "oos_sharpe": 1.10,
    "overfitting_ratio": 0.27
  }
}
```

This is stored in DB when a strategy is deployed, so the user can review historical
performance before and after going live.

---

## 2. Trade API Endpoints

The trade API runs inside the existing FastAPI service (`quant/api/`).
Endpoints use JWT auth (`require_user`); the user's `app_user_id` scopes all data.

### 2.1 Strategy Management — planned

!!! note ""
    Not yet implemented. Strategy definitions are currently managed via `BT.STRATEGY` + `BT.SP_INS_STRATEGY`. These endpoints will provide HTTP access when needed.

```
POST   /api/v1/strategies                → Create strategy (accepts StrategyConfig JSON)
GET    /api/v1/strategies                → List all strategies
GET    /api/v1/strategies/{id}           → Get strategy details + latest backtest results
PUT    /api/v1/strategies/{id}           → Update strategy (bumps version)
DELETE /api/v1/strategies/{id}           → Soft-delete (mark inactive)
```

### 2.2 Deployment (one-click deploy)

**Implemented (Phase 1.2)** — `quant/api/routers/deployments.py`, mounted at `/api/v1/trade/deployments`:

```
POST   /api/v1/trade/deployments               → Create / re-apply deployment    ✅ live
GET    /api/v1/trade/deployments               → List deployments for user       ✅ live
GET    /api/v1/trade/deployments/{id}          → One deployment (current ver.)   ✅ live
```

**Planned:**

```
PATCH  /api/v1/trade/deployments/{id}          → Update (toggle enabled, qty)    — planned
DELETE /api/v1/trade/deployments/{id}          → Stop deployment                 — planned
```

### 2.3 Credentials — planned (Phase 1.1)

!!! note ""
    Not yet implemented. Frontend stub returns `[]`. Backend stored procedures for `CORE_ADMIN.API_CREDENTIAL` exist; HTTP layer does not.

```
GET    /api/v1/credentials                     → List user's broker accounts     — planned
POST   /api/v1/credentials                     → Save new API key/secret         — planned
PUT    /api/v1/credentials/{id}                → Update credential               — planned
DELETE /api/v1/credentials/{id}                → Revoke credential               — planned
```

### 2.4 Execution Log — planned (Phase 1.8)

!!! note ""
    Not yet implemented. DB tables (`TRADE.EXECUTION_EVENT`, `TRADE.TRANSACTION`) and SPs exist; HTTP layer does not.

```
GET    /api/v1/trade/deployments/{id}/events   → Execution events for deployment — planned
GET    /api/v1/trade/deployments/{id}/trades   → Filled transactions             — planned
```

### 2.5 Backtest Results — planned

```
POST   /api/v1/strategies/{id}/results         → Store backtest results          — planned
GET    /api/v1/strategies/{id}/results         → Historical backtest results     — planned
```

---

## 3. One-Click Deploy Flow

```
User clicks "Deploy" in UI
         │
         ▼
┌──────────────────────────┐
│ 1. Serialize StrategyConfig │
│    + BacktestResults to JSON  │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 2. POST /strategies       │
│    (creates/updates)      │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 3. POST /strategies/{id}/ │
│    results                │
│    (store backtest perf)  │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 4. User fills:           │
│    - ticker              │
│    - qty                 │
│    - broker              │
│    - paper/live toggle   │
│    - risk limits         │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 5. POST /deployments     │
│    (starts algo)         │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 6. Trade API scheduler   │
│    runs on schedule:     │
│    - Fetch latest data   │
│    - Compute indicators  │
│    - Generate signal     │
│    - Apply risk checks   │
│    - Execute via broker  │
└──────────────────────────┘
```

---

## 4. Risk & Safety

These checks run **before every order** in the Trade API. They are non-negotiable.

| Check | Description | Default |
|-------|-------------|---------|
| **Kill switch** | `deployment.enabled` must be `true` | — |
| **Paper-first** | New deployments default to `paper=true` | `true` |
| **Max position** | Reject if position value > `max_position_usd` | $10,000 |
| **Max daily trades** | Reject if trade count today > `max_daily_trades` | 10 |
| **Stop loss** | Flatten position if unrealized loss > `stop_loss_pct` | 5% |
| **Cash check** | Query broker for available cash before placing order | — |
| **Signal validation** | Signal must be in `{-1, 0, 1}` — reject anything else | — |
| **Duplicate guard** | Don't place order if same signal was already acted on | — |
| **Connection check** | Verify broker gateway is reachable before trading | — |

### 4.1 Confirmation flow for live trading

```
paper=true  → Deploy immediately, no confirmation
paper=false → Require explicit user confirmation + trade password
              Log warning: "LIVE TRADING ENABLED for {ticker}"
```

---

## 5. Trade Adapter Interface

Abstract the broker so new exchanges can be added without changing signal logic.
The canonical interface is defined in [Futu Trading §3.4](futu-trading.md#34-abstract-interfaces) and will live in `quant/trade/adapters/base.py`.

```python
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
Value objects `OrderRequest`, `OrderResult`, `BrokerSessionState` live in `quant/trade/models/`.

**Adapter registry:** `AdapterRegistry.get(app_id)` resolves `REFDATA.APP` → adapter class (see [Futu Trading §3.1](futu-trading.md#31-principles)).

Planned adapters:

| Adapter | Gateway | Asset class | Reference |
|---------|---------|-------------|-----------|
| `FutuAdapter` | `FutuTradeGateway` (OpenD) | HK/US equities | [futu-trading.md](futu-trading.md) |
| `BybitAdapter` | `CcxtTradeGateway` (ccxt) | Crypto perpetuals | `backup/deco/bybit._trade.py` |
| `BinanceAdapter` | `CcxtTradeGateway` (ccxt) | Crypto spot/perps | — |

---

## 6. Signal Execution Loop

The Trade API scheduler runs this loop for each active deployment:

```python
def execute_deployment(deployment, strategy):
    # 1. Fetch latest data
    data = fetch_live_data(deployment.broker, deployment.ticker)

    # 2. For each substrategy, compute indicator + position
    positions = []
    for sub in strategy.substrategies:
        df = data.copy()
        df['factor'] = df[sub.data_column]
        ta = TechnicalAnalysis(df)
        indicator_func = getattr(ta, sub.indicator)
        indicator_vals = indicator_func(sub.window)
        signal_func = getattr(Strategy, sub.signal_func)
        pos = signal_func(indicator_vals, sub.signal)
        positions.append(pos[-1])  # latest signal only

    # 3. Combine via conjunction
    if strategy.conjunction == "AND":
        final_signal = min(positions) if all same sign, else 0
    else:  # OR
        final_signal = max(positions, key=abs)

    # 4. Risk checks
    if not passes_risk_checks(deployment, final_signal):
        log_rejected(deployment, final_signal)
        return

    # 5. Execute
    adapter = get_adapter(deployment.broker)
    result = adapter.apply_signal(
        deployment.ticker, final_signal, deployment.qty
    )

    # 6. Persist audit rows (no TRADE.INTENT — signal was in-memory for this tick)
    log_execution_event(deployment, final_signal, result)  # TRADE.EXECUTION_EVENT
    if result.filled:
        log_transaction(deployment, result)                # TRADE.TRANSACTION
```

---

## 7. DB Schema (high-level)

Database: **Quant**. Tables use `SCHEMA.TABLE` naming:
- `BT.` — backtest artifacts and strategy definitions
- `TRADE.` — live execution records (`DEPLOYMENT`, `EXECUTION_EVENT`, `TRANSACTION` only — no `INTENT`; decision #38)
- `CORE_ADMIN.` — user accounts, API credentials
- `INST.` — instrument reference (product cross-reference)
- `REFDATA.` — reference/lookup data

!!! tip "Source of truth"
    DDL lives in `db/liquidbase/`. The SQL below mirrors those files. Always run `diff` against the Liquibase source when in doubt (see AGENTS.md §Checking Schema Discrepancies).

```sql
-- ── BT schema (soft-versioned) ──

CREATE TABLE BT.STRATEGY (
    STRATEGY_ID    UUID NOT NULL,
    STRATEGY_VID   INTEGER NOT NULL,
    STRATEGY_NM    TEXT,
    CONFIG_JSON    JSONB NOT NULL,         -- full OptimizeRequest payload
    IS_CURRENT_IND CHAR(1) NOT NULL,
    USER_ID        TEXT NOT NULL,
    CREATED_AT     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (STRATEGY_ID, STRATEGY_VID)
);

CREATE TABLE BT.RESULT (
    RESULT_ID    UUID PRIMARY KEY,        -- client-generated (queue worker)
    QUEUE_ID     UUID NOT NULL,
    PAYLOAD_JSON JSONB NOT NULL,
    USER_ID      TEXT,
    CREATED_AT   TIMESTAMPTZ NOT NULL
);

-- ── TRADE schema (soft-versioned deployment, append-only event/txn) ──

CREATE TABLE TRADE.DEPLOYMENT (
    DEPLOYMENT_ID       UUID NOT NULL,
    DEPLOYMENT_VID      INTEGER NOT NULL,         -- bumps on config change
    APP_USER_ID         UUID NOT NULL,            -- owner
    STRATEGY_ID         UUID NOT NULL,            -- FK → BT.STRATEGY
    STRATEGY_VID        INTEGER NOT NULL,         -- pinned strategy version
    API_CREDENTIAL_ID   INTEGER NOT NULL,         -- FK → CORE_ADMIN.API_CREDENTIAL
    APP_ID              INTEGER NOT NULL,         -- FK → REFDATA.APP (broker)
    INTERNAL_CUSIP      TEXT NOT NULL,            -- platform product ID
    QTY                 NUMERIC NOT NULL,
    IS_PAPER_IND        CHAR(1) NOT NULL,         -- Y = paper / testnet
    IS_ENABLED_IND      CHAR(1) NOT NULL,         -- kill switch
    DEPLOYMENT_STATUS   TEXT NOT NULL,             -- CREATED / ACTIVE / PAUSED / STOPPED
    TRANSACT_FROM_TS    TIMESTAMPTZ NOT NULL,
    TRANSACT_TO_TS      TIMESTAMPTZ NOT NULL,     -- 9999-12-31 = current
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (DEPLOYMENT_ID, DEPLOYMENT_VID)
);

CREATE TABLE TRADE.EXECUTION_EVENT (
    EXECUTION_EVENT_ID  UUID NOT NULL PRIMARY KEY,
    DEPLOYMENT_ID       UUID NOT NULL,
    DEPLOYMENT_VID      INTEGER NOT NULL,
    SIGNAL_VALUE        NUMERIC,
    BUY_SELL_CD         TEXT NOT NULL,             -- BUY, SELL, HOLD, REJECTED
    QUANTITY            NUMERIC,
    VENDOR_ORDER_ID     TEXT,
    IS_SUCCESS_IND      CHAR(1) NOT NULL,
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL
);

CREATE TABLE TRADE.TRANSACTION (
    TRANSACTION_ID      UUID NOT NULL PRIMARY KEY,
    DEPLOYMENT_ID       UUID NOT NULL,
    APP_ID              INTEGER NOT NULL,
    ORDER_STATE_ID      INTEGER,
    TRANS_STATE_ID      INTEGER,
    INTERNAL_CUSIP      TEXT NOT NULL,
    VENDOR_SYMBOL       TEXT,
    BUY_SELL_CD         TEXT NOT NULL,
    TRANS_CCY_CD        TEXT NOT NULL,
    QUANTITY            NUMERIC,
    PRICE               NUMERIC,
    NOTIONAL_AMT        NUMERIC,
    FEE_AMT             NUMERIC,
    VENDOR_ORDER_ID     TEXT,
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL
);

-- ── REFDATA / INST ──

-- Vendor-symbol mapping lives in INST.PRODUCT_XREF.
-- See docs/architecture/database.md for the INST schema design.
```

---

## 8. Serialization: StrategyConfig ↔ JSON

Implemented in `quant/strategy/signals.py` — `strategy_to_json()` and `backtest_results_to_json()`.

```python
from strat import StrategyConfig, SubStrategy, strategy_to_json, backtest_results_to_json

# Single-factor (uses StrategyConfig.single for self-describing config):
cfg = StrategyConfig.single(
    "BTC-USD", "get_bollinger_band",
    SignalDirection.momentum_band_signal, 365,
    window=20, signal=1.0
)
strat_json = strategy_to_json(cfg)

# Multi-factor:
sub1 = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
sub2 = SubStrategy("get_rsi", "reversion_band_signal", 14, 0.5)
cfg = StrategyConfig(
    "AAPL", "get_sma", SignalDirection.momentum_band_signal, 252,
    conjunction="AND", substrategies=(sub1, sub2)
)
strat_json = strategy_to_json(cfg)

# Backtest results (links via strategy_id):
bt_json = backtest_results_to_json(
    cfg.strategy_id, perf, cfg.ticker,
    "2020-01-01", "2023-12-31", 5.0
)
```

Legacy `StrategyConfig` (without substrategies) is still supported —
pass `window` and `signal` explicitly to `strategy_to_json(cfg, window=20, signal=1.0)`.

---

## 9. Implementation Order

| Step | What | Status | Depends on |
|------|------|--------|------------|
| 1 | Define JSON schema (this doc) | done | — |
| 2 | `strategy_to_json()` + `backtest_results_to_json()` serializers | done | Step 1 |
| 3 | DB schema + Liquibase migrations (`db/liquidbase/trade/`) | done | Step 1 |
| 4 | FastAPI Trade API (`quant/api/routers/deployments.py`) | done (GET/POST) | Steps 1–3 |
| 5 | Credentials API (`/api/v1/credentials`) — Phase 1.1 | — | Step 3 |
| 6 | `TradeAdapter` interface + `FutuAdapter` + `AdapterRegistry` | — | Step 4 — [futu-trading.md](futu-trading.md) |
| 7 | Signal execution loop + scheduler (`DeploymentExecutor`) | — | Steps 5–6 |
| 8 | Risk checks module (`RiskRules`) | — | Step 7 |
| 9 | Deploy / Apply in React Trade UI | — (shell exists) | Steps 5–8 |
| 10 | Execution log + monitoring dashboard (Phase 1.8) | — | Step 7 |

---

## 10. Open Questions

1. **Scheduler**: Use APScheduler (Python) or system cron? APScheduler keeps state in-process; cron is simpler but stateless.
2. ~~**Multi-ticker**: Should one deployment handle multiple tickers, or one deployment per ticker?~~ **Resolved:** one deployment = one ticker (`INTERNAL_CUSIP`).
3. **Position sizing**: Current design is fixed `qty`. Future: fractional/proportional sizing based on portfolio value.
4. **Rebalance frequency**: `daily_close` is straightforward. Intraday signals need streaming data — significantly more complex.
5. ~~**Auth**: Trade API needs authentication. JWT tokens? API keys? Tied to `user` field.~~ **Resolved:** JWT via `require_user` + `CurrentUser.app_user_id`. All deployment rows scoped to `APP_USER_ID`.

---

## 11. AWS Infrastructure

### Compute — EC2 t4g.medium (Graviton ARM)

| Spec | Value |
|------|-------|
| vCPU | 2 |
| RAM | 4 GB |
| Architecture | ARM64 (Graviton) |
| On-Demand | ~$24/mo |
| Reserved 1yr | ~$14/mo |

**Current prod:** `t4g.medium` per decision #34 — headroom for api + worker + redis + future trade service. See [phase-0.2-capacity.md](../archive/phase-0/phase-0.2-capacity.md).

### Database — Aurora PostgreSQL 17.9 (Serverless v2)

| Spec | Value |
|------|-------|
| Engine | Aurora PostgreSQL 17.9 |
| Min ACU | 0.5 |
| Max ACU | 2 |
| Cost | ~$0.12/ACU-hour when active |
| Storage | gp3 (~$2.30/mo) |

**Why Postgres over SQLite**:
- Native `CREATE SCHEMA` — `BT.`, `TRADE.`, `REFDATA.` schemas work natively
- `jsonb` type for `CONFIG_JSON`, `METRICS_JSON` — queryable and indexable
- Native `UUID` column type (not text)
- Concurrent writes (Trade API + backtest don't collide)
- Serverless v2 scales to zero — near-$0 when idle

**Why not DynamoDB**: Data is relational (joins: strategy → results → deployments). Wrong fit for key-value.

### Architecture Diagram

```
┌───────────────────────────────────────────────┐
│  EC2 t4g.medium (Docker Compose)               │
│  nginx + api + worker + redis (+ trade later) │
└───────────┼───────────────────────────────────┘
            │
            ▼
┌───────────────────────┐          ┌──────────┐
│  Aurora PostgreSQL    │          │ Exchange │
│  17.9 Serverless v2   │          │ (Futu /  │
│  ┌─────────────────┐  │          │  Bybit)  │
│  │ BT.*            │  │          └──────────┘
│  │ TRADE.*         │  │               ▲
│  │ REFDATA.*       │  │               │
│  └─────────────────┘  │         Orders/Fills
│  DB: Quant             │               │
└───────────────────────┘     ◄─────────┘
```

### Local Development

Use SQLite or Docker Postgres locally. Switch via environment variable:

```bash
# .env
DB_URL=sqlite:///db/store/quant.db               # local dev
DB_URL=postgresql://user:pass@host/quant          # AWS
```

### Estimated Monthly Cost

| Resource | Cost |
|----------|------|
| EC2 t4g.medium (reserved 1yr) | ~$14 |
| RDS Serverless v2 (mostly idle) | ~$5–15 |
| EBS 20 GB gp3 | ~$1.60 |
| **Total** | **~$15–25** |

### Upgrade Path

| Trigger | Action |
|---------|--------|
| Grid search too slow on burstable | Upgrade to `t4g.medium` or `c7g.medium` (sustained compute) |
| Multi-user or high-frequency signals | Move to ECS Fargate or EKS |
| DB exceeds 2 ACU regularly | Increase Max ACU or switch to provisioned RDS |
| Python 3.14 stable (Oct 2026) | Drop `uuid7` package, use stdlib `uuid.uuid7()` |
