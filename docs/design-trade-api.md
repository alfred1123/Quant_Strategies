# Design Doc: Strategy JSON → Trade API

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
  "conjunction": "AND",
  "trading_period": 365,
  "substrategies": [
    {
      "id": 1,
      "indicator": "get_bollinger_band",
      "signal_func": "momentum_const_signal",
      "window": 20,
      "signal": 1.0,
      "data_column": "v"
    },
    {
      "id": 2,
      "indicator": "get_rsi",
      "signal_func": "reversion_const_signal",
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
| `conjunction` | `"AND"` \| `"OR"` | How substrategy positions combine (flat enum for now) |
| `trading_period` | int | 365 (crypto) or 252 (equity) — for annualization |
| `substrategies` | array | 1–2 substrategy objects (expandable later) |

Each substrategy:

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Ordering key (1-indexed) |
| `indicator` | string | `TechnicalAnalysis` method name |
| `signal_func` | string | `Strategy` static method name (serialized as string, resolved at runtime) |
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

```sql
CREATE TABLE strategies (
    strategy_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    version       INTEGER DEFAULT 1,
    conjunction   TEXT CHECK(conjunction IN ('AND', 'OR')) DEFAULT 'AND',
    trading_period INTEGER NOT NULL,
    config_json   TEXT NOT NULL,        -- full StrategyConfig JSON
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    active        INTEGER DEFAULT 1
);

CREATE TABLE substrategies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id   TEXT REFERENCES strategies(strategy_id),
    substrategy_id INTEGER NOT NULL,    -- 1, 2, ...
    indicator     TEXT NOT NULL,
    signal_func   TEXT NOT NULL,
    window        INTEGER NOT NULL,
    signal        REAL NOT NULL,
    data_column   TEXT DEFAULT 'v'
);

CREATE TABLE backtest_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id   TEXT REFERENCES strategies(strategy_id),
    run_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    data_start    TEXT,
    data_end      TEXT,
    ticker        TEXT,
    fee_bps       REAL,
    metrics_json  TEXT NOT NULL,        -- {sharpe, calmar, max_dd, ...}
    walk_forward_json TEXT              -- optional
);

CREATE TABLE deployments (
    deployment_id TEXT PRIMARY KEY,
    strategy_id   TEXT REFERENCES strategies(strategy_id),
    portfolio     TEXT DEFAULT 'DEFAULT',
    user          TEXT NOT NULL,
    broker        TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    qty           INTEGER NOT NULL,
    paper         INTEGER DEFAULT 1,
    market        TEXT DEFAULT 'US',
    schedule      TEXT DEFAULT 'daily_close',
    enabled       INTEGER DEFAULT 1,
    risk_limits_json TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trade_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id TEXT REFERENCES deployments(deployment_id),
    timestamp     TEXT DEFAULT CURRENT_TIMESTAMP,
    signal_value  REAL,
    action        TEXT,                 -- BUY, SELL, HOLD, REJECTED
    qty           INTEGER,
    order_id      TEXT,
    success       INTEGER,
    message       TEXT
);
```

---

## 8. Serialization: StrategyConfig ↔ JSON

```python
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

def strategy_to_json(config: StrategyConfig, window, signal) -> dict:
    """Serialize a StrategyConfig + params to the Strategy JSON schema."""
    return {
        "strategy_id": str(uuid.uuid4()),
        "name": f"{config.indicator_name}_{config.strategy_func.__name__}_{window}_{signal}",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "conjunction": "AND",
        "trading_period": config.trading_period,
        "substrategies": [
            {
                "id": 1,
                "indicator": config.indicator_name,
                "signal_func": config.strategy_func.__name__,
                "window": window,
                "signal": signal,
                "data_column": "v",
            }
        ],
    }

def backtest_results_to_json(strategy_id, perf, ticker, start, end, fee_bps):
    """Serialize backtest Performance metrics to JSON."""
    return {
        "strategy_id": strategy_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "data_range": {"start": start, "end": end},
        "ticker_backtested": ticker,
        "fee_bps": fee_bps,
        "metrics": perf.get_strategy_performance().to_dict(),
        "buy_hold_metrics": perf.get_buy_hold_performance().to_dict(),
    }
```

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
