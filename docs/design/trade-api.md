# Design Doc: Strategy JSON → Trade API

!!! info "Status"
    **Proposed — not implemented.** A `FutuTrader` Python utility exists in `src/trade.py` (see [Paper Trading guide](../guides/trading.md)). The full Strategy-JSON-to-Trade-API flow described here is the long-term direction; persistence, deployment endpoints, and the broker-adapter abstraction have not been built yet.

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

```json
{
  "deployment_id": "auto-generated-uuid",
  "strategy_id": "links-to-strategy-config",
  "portfolio": "DEFAULT",
  "user": "alfcheun",
  "broker": "FUTU",
  "ticker": "US.WEAT",
  "qty": 100,
  "paper": true,
  "market": "US",
  "schedule": "daily_close",
  "enabled": true,
  "risk_limits": {
    "max_position_usd": 10000,
    "max_daily_trades": 10,
    "stop_loss_pct": 5.0
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `deployment_id` | string (UUID) | Unique deployment instance |
| `strategy_id` | string | FK → StrategyConfig |
| `portfolio` | string | Portfolio grouping label |
| `user` | string | Owner |
| `broker` | string | `"FUTU"`, `"BYBIT"`, etc. — selects trade adapter |
| `ticker` | string | Broker-specific symbol |
| `qty` | int | Position size per signal |
| `paper` | bool | Paper vs live trading |
| `market` | string | Market code (US, HK, etc.) |
| `schedule` | string | When to evaluate: `"daily_close"`, `"hourly"`, `"manual"` |
| `enabled` | bool | Kill switch |
| `risk_limits` | object | Safety guardrails (see §4) |

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

The algo trade system runs as a **separate service** (FastAPI) that the backtest
UI calls via HTTP. This decouples backtest from execution.

### 2.1 Strategy Management

```
POST   /api/v1/strategies                → Create strategy (accepts StrategyConfig JSON)
GET    /api/v1/strategies                → List all strategies
GET    /api/v1/strategies/{id}           → Get strategy details + latest backtest results
PUT    /api/v1/strategies/{id}           → Update strategy (bumps version)
DELETE /api/v1/strategies/{id}           → Soft-delete (mark inactive)
```

### 2.2 Deployment (one-click deploy)

```
POST   /api/v1/deployments               → Deploy strategy (accepts DeploymentConfig JSON)
GET    /api/v1/deployments               → List active deployments
GET    /api/v1/deployments/{id}          → Deployment status + recent trades
PATCH  /api/v1/deployments/{id}          → Update (e.g. toggle enabled, change qty)
DELETE /api/v1/deployments/{id}          → Stop deployment
```

### 2.3 Execution Log

```
GET    /api/v1/deployments/{id}/trades   → Trade history for a deployment
GET    /api/v1/deployments/{id}/signals  → Signal log (what indicator computed)
```

### 2.4 Backtest Results

```
POST   /api/v1/strategies/{id}/results   → Store backtest results
GET    /api/v1/strategies/{id}/results   → Get all historical backtest results
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

```python
class TradeAdapter:
    """Interface all broker adapters must implement."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def place_order(self, symbol: str, qty: int, side: str,
                    *, order_type: str = "MARKET",
                    price: float | None = None) -> OrderResult: ...
    def get_positions(self) -> pd.DataFrame | None: ...
    def get_orders(self) -> pd.DataFrame | None: ...
    def get_account_info(self) -> pd.DataFrame | None: ...
    def apply_signal(self, symbol: str, signal_value: float,
                     qty: int) -> OrderResult | None: ...
```

Current adapters:
- `FutuAdapter` — wraps existing `FutuTrader` (HK/US equities)
- `BybitAdapter` — future, resume from `backup/deco/bybit._trade.py` (crypto)

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

    # 6. Log
    log_trade(deployment, strategy, final_signal, result)
```

---

## 7. DB Schema (high-level)

Database: **Quant**. Tables use `SCHEMA.TABLE` naming:
- `BT.` — backtest artifacts and strategy definitions
- `TRADE.` — live execution records
- `REFDATA.` — reference/lookup data

```sql
-- ── BT schema ──

CREATE TABLE BT.STRATEGY (
    STRATEGY_ID    UUID PRIMARY KEY,
    NAME           TEXT NOT NULL,
    VERSION        INTEGER,
    TICKER         TEXT NOT NULL,          -- data-source symbol (e.g. "BTC-USD")
    CONJUNCTION    TEXT,
    TRADING_PERIOD INTEGER NOT NULL,
    CONFIG_JSON    JSONB NOT NULL,         -- full StrategyConfig JSON
    USER_ID        TEXT,
    CREATED_AT     TIMESTAMPTZ,
    UPDATED_AT     TIMESTAMPTZ,
    IS_CURRENT_IND CHAR(1)
);

CREATE TABLE BT.RESULT (
    RESULT_ID         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    STRATEGY_ID       UUID NOT NULL,
    RUN_AT            TIMESTAMPTZ,
    DATA_START        DATE,
    DATA_END          DATE,
    TICKER            TEXT,
    FEE_BPS           NUMERIC,
    METRICS_JSON      JSONB NOT NULL,     -- {sharpe, calmar, max_dd, ...}
    WALK_FORWARD_JSON JSONB,              -- optional
    USER_ID           TEXT,
    CREATED_AT        TIMESTAMPTZ
);

-- ── TRADE schema ──

CREATE TABLE TRADE.DEPLOYMENT (
    DEPLOYMENT_ID    UUID PRIMARY KEY,
    STRATEGY_ID      UUID NOT NULL,
    PORTFOLIO        TEXT,
    USER_ID          TEXT NOT NULL,
    BROKER           TEXT NOT NULL,
    TICKER           TEXT NOT NULL,
    QTY              INTEGER NOT NULL,
    PAPER            CHAR(1),
    MARKET           TEXT,
    SCHEDULE         TEXT,
    ENABLED          CHAR(1),
    RISK_LIMITS_JSON JSONB,
    CREATED_AT       TIMESTAMPTZ
);

CREATE TABLE TRADE.LOG (
    LOG_ID        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    DEPLOYMENT_ID UUID NOT NULL,
    TIMESTAMP     TIMESTAMPTZ,
    SIGNAL_VALUE  NUMERIC,
    ACTION        TEXT,                   -- BUY, SELL, HOLD, REJECTED
    QTY           INTEGER,
    ORDER_ID      TEXT,
    SUCCESS       CHAR(1),
    MESSAGE       TEXT,
    USER_ID       TEXT,
    CREATED_AT    TIMESTAMPTZ
);

-- ── REFDATA schema ──

-- TICKER_MAPPING has been dropped. Vendor-symbol mapping now lives in INST.PRODUCT_XREF.
-- See docs/architecture/database.md for the INST schema design.
```

---

## 8. Serialization: StrategyConfig ↔ JSON

Implemented in `src/strat.py` — `strategy_to_json()` and `backtest_results_to_json()`.

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

| Step | What | Depends on |
|------|------|------------|
| 1 | Define JSON schema (this doc) | — |
| 2 | `strategy_to_json()` + `backtest_results_to_json()` serializers in `strat.py` | Phase 1 (done) |
| 3 | DB schema + migrations in `db/sql/` | Step 1 |
| 4 | FastAPI Trade API service (separate `trade_api/` package) | Steps 1–3 |
| 5 | `TradeAdapter` interface + `FutuAdapter` wrapping `FutuTrader` | Step 4 |
| 6 | Signal execution loop + scheduler | Steps 4–5 |
| 7 | Risk checks module | Step 6 |
| 8 | "Deploy" button in Streamlit/TS UI | Steps 2–7 |
| 9 | Execution log + monitoring dashboard | Step 6 |

---

## 10. Open Questions

1. **Scheduler**: Use APScheduler (Python) or system cron? APScheduler keeps state in-process; cron is simpler but stateless.
2. **Multi-ticker**: Should one deployment handle multiple tickers, or one deployment per ticker?
3. **Position sizing**: Current design is fixed `qty`. Future: fractional/proportional sizing based on portfolio value.
4. **Rebalance frequency**: `daily_close` is straightforward. Intraday signals need streaming data — significantly more complex.
5. **Auth**: Trade API needs authentication. JWT tokens? API keys? Tied to `user` field.

---

## 11. AWS Infrastructure

### Compute — EC2 t4g.small (Graviton ARM)

| Spec | Value |
|------|-------|
| vCPU | 2 |
| RAM | 2 GB |
| Architecture | ARM64 (Graviton) — 20% cheaper than x86 |
| Baseline CPU | 20% sustained, burstable to 100% |
| On-Demand | ~$12/mo |
| Reserved 1yr | ~$7/mo |

**Why burstable**: FastAPI idle 99% of the time, daily signal cron runs for seconds, backtests are occasional bursts. CPU credits accumulate overnight. Upgrade to `t4g.medium` (4 GB, ~$24/mo) only if grid search exhausts burst credits regularly.

**Why Graviton**: Entire stack is Python — no x86 dependency. ARM is cheaper and faster for Python workloads.

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
│  EC2 t4g.small                                │
│                                               │
│  ┌─────────────────┐   ┌──────────────────┐   │
│  │  FastAPI         │   │  React/TS        │   │
│  │  Trade API       │   │  Frontend        │   │
│  │  :8000           │   │  :3000           │   │
│  └────────┬─────────┘   └──────────────────┘   │
│           │                                    │
│  ┌────────┴─────────┐                          │
│  │  APScheduler /   │                          │
│  │  Cron             │                          │
│  │  (daily signals) │                          │
│  └────────┬─────────┘                          │
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
| EC2 t4g.small (reserved 1yr) | ~$7 |
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
