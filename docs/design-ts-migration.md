# Design Doc: Streamlit → TypeScript Migration

## Overview

Replace `src/app.py` (Streamlit) with a React/TypeScript SPA backed by a FastAPI service. The FastAPI layer also serves as the foundation for the Trade API (Phase 7), so both backtest UI and algo execution share one backend.

```
┌──────────────────┐       REST / WebSocket       ┌──────────────────────┐
│  React / TS SPA  │ ◄──────────────────────────► │  FastAPI (Python)    │
│  (Vite + Plotly) │                              │  backtest + trade    │
└──────────────────┘                              └──────────┬───────────┘
                                                             │
                                                  ┌──────────▼───────────┐
                                                  │  Existing src/       │
                                                  │  data, strat, perf,  │
                                                  │  param_opt,          │
                                                  │  walk_forward        │
                                                  └──────────┬───────────┘
                                                             │
                                                  ┌──────────▼───────────┐
                                                  │  PostgreSQL (quantdb)│
                                                  └──────────────────────┘
```

---

## 1. Why Migrate

| Limitation in Streamlit | TypeScript solution |
|---|---|
| No interactive row-click on the Top 10 table to drill into equity curves | DataGrid with `onRowClick` → fetch + render equity curve for that param combo |
| Full page re-run on every interaction (Streamlit execution model) | SPA with granular state — only affected components re-render |
| No WebSocket for long-running optimization progress | FastAPI `WebSocket` endpoint streams trial-by-trial progress |
| Limited control over layout, routing, theming | Full React component tree with CSS/Tailwind |
| Tight coupling: UI + compute in one Python process | Decoupled: FastAPI scales independently; TS frontend is static |
| Cannot share backend with Trade API | FastAPI serves both backtest endpoints and trade endpoints |

---

## 2. Architecture

### 2.1 Directory Layout

```
frontend/               # React / TypeScript SPA (Vite + Tailwind + MUI)
  src/
    api/
      client.ts         # Axios instance (baseURL /api/v1, proxied to :8000)
      backtest.ts       # runOptimize(), runPerformance()
      refdata.ts        # useIndicators(), useSignalTypes(), useAssetTypes(), useConjunctions()
    components/
      ConfigDrawer.tsx  # Left-side MUI Drawer — all form fields + Run button
      Top10Table.tsx    # MUI DataGrid — param rows + View Analysis / ★ Best buttons
      MetricsCards.tsx  # Strategy vs Buy & Hold metric cards (side-by-side)
      HeatmapChart.tsx  # Plotly heatmap (Sharpe vs window/signal grid)
      EquityCurveChart.tsx # Plotly cumulative return + drawdown charts
    pages/
      BacktestPage.tsx  # Single-page layout: topbar, drawer, results, analysis
    types/
      backtest.ts       # BacktestConfig (form state) + API request/response types
      refdata.ts        # IndicatorRow, SignalTypeRow, AssetTypeRow, ConjunctionRow
    App.tsx             # → BacktestPage only
    main.tsx            # StrictMode + QueryClientProvider
    index.css           # @import "tailwindcss"
  vite.config.ts        # Tailwind plugin + /api proxy → localhost:8000
  tsconfig.json
  package.json

api/                    # FastAPI backend
  main.py              # uvicorn entrypoint
  routers/
    backtest.py        # /api/v1/backtest/*
    strategies.py      # /api/v1/strategies/*  (Phase 7)
    deployments.py     # /api/v1/deployments/* (Phase 7)
  schemas/
    backtest.py        # Pydantic request/response models
  services/
    backtest.py        # Calls src/ modules (ParametersOptimization, Performance, WalkForward)
  ws/
    progress.py        # WebSocket for optimization progress streaming
```

### 2.2 Shared Backend

The FastAPI service imports `src/` modules directly (same Python process):

```python
# api/services/backtest.py
from src.param_opt import ParametersOptimization
from src.perf import Performance
from src.walk_forward import WalkForward
from src.strat import StrategyConfig, SubStrategy, SignalDirection
from src.data import YahooFinance
```

No duplication of backtest logic — the TypeScript frontend replaces only the presentation layer.

---

## 3. API Endpoints — Backtest

All endpoints under `/api/v1/backtest/`. Trade API endpoints (from `design-trade-api.md`) live under `/api/v1/strategies/` and `/api/v1/deployments/`.

### 3.1 Fetch Data

```
POST /api/v1/backtest/data
```

Request:
```json
{
  "symbol": "BTC-USD",
  "start": "2016-01-01",
  "end": "2026-04-01"
}
```

Response:
```json
{
  "rows": 3743,
  "start_date": "2016-01-01",
  "end_date": "2026-03-31",
  "data": [
    {"datetime": "2016-01-01", "price": 430.72},
    ...
  ]
}
```

### 3.2 Run Optimization

```
POST /api/v1/backtest/optimize
```

Request:
```json
{
  "symbol": "BTC-USD",
  "start": "2016-01-01",
  "end": "2026-04-01",
  "mode": "single",
  "indicator": "get_bollinger_band",
  "strategy": "momentum_const_signal",
  "trading_period": 365,
  "fee_bps": 5.0,
  "window_range": {"min": 5, "max": 100, "step": 5},
  "signal_range": {"min": 0.25, "max": 2.50, "step": 0.25}
}
```

Multi-factor request:
```json
{
  "symbol": "BTC-USD",
  "start": "2016-01-01",
  "end": "2026-04-01",
  "mode": "multi",
  "trading_period": 365,
  "fee_bps": 5.0,
  "conjunction": "AND",
  "factors": [
    {
      "indicator": "get_bollinger_band",
      "strategy": "momentum_const_signal",
      "data_column": "price",
      "window_range": {"min": 10, "max": 100, "step": 5},
      "signal_range": {"min": 0.25, "max": 2.50, "step": 0.25}
    },
    {
      "indicator": "get_rsi",
      "strategy": "reversion_const_signal",
      "data_column": "price",
      "window_range": {"min": 5, "max": 50, "step": 1},
      "signal_range": {"min": 10.0, "max": 40.0, "step": 5.0}
    }
  ]
}
```

Response:
```json
{
  "total_trials": 190,
  "valid": 188,
  "best": {
    "window": 20,
    "signal": 1.0,
    "sharpe": 1.35
  },
  "top10": [
    {"window": 20, "signal": 1.0, "sharpe": 1.35},
    {"window": 25, "signal": 0.75, "sharpe": 1.28},
    ...
  ],
  "grid": [
    {"window": 5, "signal": 0.25, "sharpe": 0.42},
    ...
  ]
}
```

### 3.3 Optimization Progress (WebSocket)

```
WS /api/v1/backtest/optimize/ws
```

Client sends the same optimize request JSON on connect. Server streams:
```json
{"type": "progress", "completed": 42, "total": 190}
{"type": "progress", "completed": 43, "total": 190}
...
{"type": "complete", "result": { ... same as REST response ... }}
```

### 3.4 Run Single Performance

```
POST /api/v1/backtest/performance
```

Request:
```json
{
  "symbol": "BTC-USD",
  "start": "2016-01-01",
  "end": "2026-04-01",
  "mode": "single",
  "indicator": "get_bollinger_band",
  "strategy": "momentum_const_signal",
  "trading_period": 365,
  "fee_bps": 5.0,
  "window": 20,
  "signal": 1.0
}
```

Response:
```json
{
  "strategy_metrics": {
    "Total Return": 1.45,
    "Annualized Return": 0.12,
    "Sharpe Ratio": 1.35,
    "Max Drawdown": 0.23,
    "Calmar Ratio": 0.52
  },
  "buy_hold_metrics": {
    "Total Return": 2.10,
    "Annualized Return": 0.18,
    "Sharpe Ratio": 0.85,
    "Max Drawdown": 0.55,
    "Calmar Ratio": 0.33
  },
  "equity_curve": [
    {"datetime": "2016-02-01", "cumu": 0.012, "buy_hold_cumu": 0.015, "dd": 0.0, "buy_hold_dd": 0.0},
    ...
  ]
}
```

### 3.5 Run Walk-Forward

```
POST /api/v1/backtest/walk-forward
```

Request: same as optimize + `split_ratio` field.

Response:
```json
{
  "best_window": 20,
  "best_signal": 1.0,
  "is_metrics": { "Sharpe Ratio": 1.50, ... },
  "oos_metrics": { "Sharpe Ratio": 1.10, ... },
  "overfitting_ratio": 0.27,
  "equity_curve": [
    {"datetime": "2016-02-01", "cumu": 0.012, "buy_hold_cumu": 0.015},
    ...
  ],
  "split_date": "2021-02-15"
}
```

---

## 4. Streamlit → React Component Mapping

| Streamlit (app.py) | React Component | Notes |
|---|---|---|
| Sidebar: symbol, dates, asset type, fee | `<Sidebar>` | Controlled form state |
| Sidebar: indicator, strategy, window, signal | `<Sidebar>` single-factor section | |
| Sidebar: grid search ranges (win/sig min/max/step) | `<Sidebar>` grid section | |
| Sidebar: multi-factor config (Add/Remove Factor) | `<Sidebar>` → dynamic `<FactorRow>` list | |
| Sidebar: conjunction radio (AND/OR) | `<Sidebar>` radio group | |
| Sidebar: walk-forward checkbox + split slider | `<Sidebar>` checkboxes section | |
| Mode radio (Single/Multi) | `<Sidebar>` or page-level toggle | |
| "Run Pipeline" button | `<PipelineRunner>` | Triggers POST or WebSocket |
| Progress bar (trial N / total) | `<PipelineRunner>` → progress bar | Fed by WebSocket stream |
| Best params success banner | `<OptGrid>` header alert | |
| Top 10 DataGrid | `<OptGrid>` with MUI DataGrid | **Row-click → fetch equity curve** |
| Sharpe Heatmap (single-factor) | `<Heatmap>` with Plotly `Heatmap` trace | |
| Slice Heatmaps (multi-factor) | `<Heatmap>` per factor | |
| Optuna contour / parallel-coords / importances | `<OptunaViz>` tabs | Render Plotly JSON from backend |
| Strategy / Buy-Hold metrics side-by-side | `<EquityCurve>` metrics cards | |
| Cumulative return line chart | `<EquityCurve>` Plotly `Scatter` | |
| Drawdown area chart | `<EquityCurve>` Plotly `Scatter` fill | |
| Walk-forward IS vs OOS table | `<WalkForward>` metrics table | |
| Walk-forward equity curve + split vline | `<WalkForward>` Plotly chart | |
| Overfitting ratio badge (green/yellow/red) | `<OverfitBadge>` | |
| CSV download buttons | Browser `<a download>` from in-memory blob | |

---

## 5. Row-Click Drill-In (Key New Feature)

The Top 10 table currently shows `window | signal | sharpe` rows. In TypeScript:

1. User clicks a row in `<OptGrid>`.
2. Frontend calls `POST /api/v1/backtest/performance` with that row's `window` + `signal`.
3. Response contains full equity curve + metrics.
4. `<EquityCurve>` re-renders below the table with the selected params.
5. A badge shows "Viewing: window=20, signal=1.0" above the chart.

For multi-factor, the row has `window_0, signal_0, ..., window_N, signal_N`. The request sends tuples.

This is the single most impactful UX improvement over Streamlit — interactive parameter exploration without re-running the full optimization.

---

## 6. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend framework | React 19 + TypeScript | Ecosystem, type safety |
| Build tool | Vite | Fast HMR, simple config |
| Charts | Plotly.js (`react-plotly.js`) | Already used in Streamlit; same trace types |
| Data table | MUI DataGrid | Row-click, sorting, filtering built-in |
| Styling | Tailwind CSS | Utility-first, consistent with modern React |
| State management | React Query (TanStack Query) | Server-state caching, auto-refetch |
| API client | Generated from OpenAPI spec | Type-safe, auto-sync with backend |
| Backend | FastAPI (Python) | Already in stack, async, auto-OpenAPI |
| Backend → src/ | Direct Python import | No duplication of backtest logic |
| WebSocket | FastAPI WebSocket | Optimization progress streaming |

---

## 7. Migration Phases

### M-1: FastAPI Backtest Endpoints

**Goal:** All `app.py` computation accessible via REST.

- Create `api/` directory with FastAPI app.
- Implement `POST /api/v1/backtest/data` (fetch data).
- Implement `POST /api/v1/backtest/optimize` (grid search, returns full grid + best + top10).
- Implement `POST /api/v1/backtest/performance` (single run, returns metrics + equity curve).
- Implement `POST /api/v1/backtest/walk-forward` (WF test, returns IS/OOS metrics + equity curve).
- Pydantic request/response models with OpenAPI schema auto-generation.
- Unit tests for each endpoint (mock `src/` modules, test HTTP contract).
- CORS middleware configured for `localhost:5173` (Vite dev server).

### M-2: WebSocket Progress

**Goal:** Real-time optimization progress.

- `WS /api/v1/backtest/optimize/ws` — streams `{completed, total}` per trial.
- Backend uses optuna callback (same pattern as `_on_trial` in app.py) → sends JSON frame.
- Frontend `<PipelineRunner>` connects, renders progress bar, closes on `complete` message.

### M-3: React Scaffold + Single-Page UI ✅

**Goal:** Full single-page application with collapsible config drawer.

**Implemented:**

- Vite + React + TypeScript scaffold in `frontend/`
- Tailwind CSS v4 (`@tailwindcss/vite`) + MUI v7 (`@mui/material`, `@mui/x-data-grid`)
- `<ConfigDrawer>` — slides in from left on "⚙ Configure" click
  - All form fields: symbol, date range, asset type (from `REFDATA.ASSET_TYPE`), fee bps
  - Mode toggle: Single Factor / Multi Factor
  - Indicator + Strategy dropdowns from `REFDATA.INDICATOR` / `REFDATA.SIGNAL_TYPE`
  - Window/Signal ranges **auto-fill** from `REFDATA.INDICATOR.WIN_MIN` etc. on indicator change
  - Multi-factor: dynamic Add/Remove Factor rows with per-factor indicator, strategy, ranges
- `<BacktestPage>` single-page layout:
  1. Topbar with "⚙ Configure" button
  2. On **Run**: drawer closes, optimization runs, best params auto-selected, analysis renders immediately
  3. Top 10 table (MUI DataGrid) — each row has **[View Analysis]** or **★ Best** button
  4. Clicking any row → `POST /backtest/performance` → replaces analysis section with 1 API call
  5. Analysis section: metric cards + Sharpe heatmap + equity curve + drawdown charts
- Vite dev server proxy: `/api` → `http://localhost:8000` (no CORS issues in dev)
- All dropdowns sourced exclusively from `GET /api/v1/refdata/{table}` (TanStack Query, staleTime=Infinity)

### M-4: Results Display

**Goal:** Full parity with current Streamlit output.

- `<OptGrid>` — Top 10 MUI DataGrid with row-click wiring.
- `<Heatmap>` — Plotly heatmap (single-factor) and slice heatmaps (multi-factor).
- `<EquityCurve>` — cumulative return + drawdown charts, strategy vs buy-hold metrics.
- `<WalkForward>` — IS vs OOS table, overfitting badge, equity curve with split line.
- CSV download via in-memory Blob → `<a download>`.

### M-5: Row-Click Drill-In

**Goal:** The key new feature.

- Click any row in `<OptGrid>` → `POST /backtest/performance` with that row's params.
- `<EquityCurve>` below the table updates to show that combo's equity curve.
- Multi-factor: sends tuple of windows/signals from the row's `window_N`/`signal_N` columns.

### M-6: Polish + Cutover

**Goal:** Replace Streamlit as default UI.

- Remove `app.py` from `src/` (or keep as legacy fallback).
- Update `README.md` — new launch instructions: `cd api && uvicorn main:app` + `cd frontend && npm run dev`.
- Update `setup.sh` to install Node.js deps.
- Update `.github/copilot-instructions.md` and `AGENTS.md` with new layout.

---

## 8. Pydantic Models (Backend)

```python
# api/schemas/backtest.py

from pydantic import BaseModel

class RangeParam(BaseModel):
    min: float
    max: float
    step: float

class FactorConfig(BaseModel):
    indicator: str          # e.g. "get_bollinger_band"
    strategy: str           # e.g. "momentum_const_signal"
    data_column: str = "price"
    window_range: RangeParam
    signal_range: RangeParam

class OptimizeRequest(BaseModel):
    symbol: str
    start: str              # "YYYY-MM-DD"
    end: str
    mode: str               # "single" | "multi"
    trading_period: int     # 365 | 252
    fee_bps: float = 5.0
    # Single-factor fields
    indicator: str | None = None
    strategy: str | None = None
    window_range: RangeParam | None = None
    signal_range: RangeParam | None = None
    # Multi-factor fields
    conjunction: str | None = None   # "AND" | "OR"
    factors: list[FactorConfig] | None = None

class PerformanceRequest(BaseModel):
    symbol: str
    start: str
    end: str
    mode: str
    trading_period: int
    fee_bps: float = 5.0
    # Single-factor
    indicator: str | None = None
    strategy: str | None = None
    window: int | None = None
    signal: float | None = None
    # Multi-factor
    conjunction: str | None = None
    factors: list[FactorConfig] | None = None
    windows: list[int] | None = None
    signals: list[float] | None = None

class WalkForwardRequest(OptimizeRequest):
    split_ratio: float = 0.5

class GridRow(BaseModel):
    sharpe: float | None
    # Dynamic keys: window/signal (single) or window_0/signal_0/... (multi)
    # Use dict for flexibility
    params: dict

class OptimizeResponse(BaseModel):
    total_trials: int
    valid: int
    best: dict
    top10: list[dict]
    grid: list[dict]

class EquityPoint(BaseModel):
    datetime: str
    cumu: float
    buy_hold_cumu: float
    dd: float
    buy_hold_dd: float

class PerformanceResponse(BaseModel):
    strategy_metrics: dict
    buy_hold_metrics: dict
    equity_curve: list[EquityPoint]

class WalkForwardResponse(BaseModel):
    best_window: int | list[int]
    best_signal: float | list[float]
    is_metrics: dict
    oos_metrics: dict
    overfitting_ratio: float
    equity_curve: list[EquityPoint]
    split_date: str
```

---

## 9. Open Questions

| # | Question | Options |
|---|----------|---------|
| 1 | **Optuna plots** — render server-side (return Plotly JSON) or client-side (return raw data)? | Server-side is simpler (Optuna has `plot_contour` etc. that return Plotly figures). Serialize `fig.to_json()` and render with `react-plotly.js`. |
| 2 | **Auth** — needed for MVP? | No. Add JWT/session auth when multi-user or Trade API goes live. |
| 3 | **Deployment** — single container or split? | Single Docker image with both FastAPI + static frontend for MVP. Split later for scale. |
| 4 | **Keep Streamlit?** — as fallback during migration? | Yes. Remove after M-6 is verified. |

---

## 10. Decommission Plan — `app.py` (Streamlit)

`src/app.py` stays in the repo throughout migration. When the TS frontend reaches parity (M-6), everything below can be removed in one go.

### 10.1 Deco Tag: `[DECO:STREAMLIT]`

All files and artefacts that exist **solely** for the Streamlit UI are tagged here. Nothing in `src/` library modules (`data.py`, `strat.py`, `perf.py`, `param_opt.py`, `walk_forward.py`) is tagged — those are shared with the FastAPI backend.

| Artefact | Type | Reason |
|----------|------|--------|
| `src/app.py` | File | Streamlit UI — entire file |
| `streamlit` | pip dep | Only used by `app.py` |
| `INDICATORS` dict in `app.py` | Code | Hardcoded registry → replaced by `REFDATA.INDICATOR` |
| `STRATEGY_FUNCS` / `STRATEGY_NAMES` dicts in `app.py` | Code | Hardcoded registry → replaced by `REFDATA.SIGNAL_TYPE` |
| `ASSET_TYPES` dict in `app.py` | Code | Hardcoded registry → replaced by `REFDATA.ASSET_TYPE` |
| `DATA_COLUMNS` dict in `app.py` | Code | Hardcoded registry → replaced by `REFDATA.DATA_COLUMN` |
| `INDICATOR_DEFAULTS` in `src/strat.py` | Code | Hardcoded grid defaults → replaced by `WIN_MIN`..`SIG_STEP` columns on `REFDATA.INDICATOR` |
| Conjunction `["AND", "OR"]` literals in `app.py` | Code | Hardcoded → replaced by `REFDATA.CONJUNCTION` |

### 10.2 One-Go Removal Checklist

When M-6 is verified:

1. Delete `src/app.py`
2. Remove `streamlit` from `requirements.txt`
3. Remove `INDICATOR_DEFAULTS` from `src/strat.py` (backend reads from REFDATA cache)
4. Remove Streamlit launch instructions from `README.md`
5. Update `setup.sh` — drop streamlit, add Node.js frontend build
6. Update `AGENTS.md` / `.github/copilot-instructions.md` layout table

---

## 11. REFDATA-Driven Dropdowns

Every dropdown / radio / selectbox in the current Streamlit UI maps to a `REFDATA` table. The TS frontend and FastAPI backend both consume REFDATA — the frontend fetches it via REST, the backend caches it at startup.

### 11.1 Mapping: Hardcoded → REFDATA

| UI Element | Hardcoded in `app.py` | REFDATA Table | Key Columns |
|---|---|---|---|
| Indicator selectbox | `INDICATORS` dict | `REFDATA.INDICATOR` | `DISPLAY_NAME` (label), `METHOD_NAME` (value) |
| Strategy selectbox | `STRATEGY_FUNCS` / `STRATEGY_NAMES` | `REFDATA.SIGNAL_TYPE` | `DISPLAY_NAME` (label), `FUNC_NAME` (value) |
| Asset type selectbox | `ASSET_TYPES` dict | `REFDATA.ASSET_TYPE` | `DISPLAY_NAME` (label), `TRADING_PERIOD` (value) |
| Data column selectbox | `DATA_COLUMNS` dict | `REFDATA.DATA_COLUMN` | `DISPLAY_NAME` (label), `COLUMN_NAME` (value) |
| Conjunction radio | `["AND", "OR"]` literal | `REFDATA.CONJUNCTION` | `DISPLAY_NAME` (label), `NAME` (value) |
| Grid search defaults | `INDICATOR_DEFAULTS` in `strat.py` | `REFDATA.INDICATOR` | `WIN_MIN`, `WIN_MAX`, `WIN_STEP`, `SIG_MIN`, `SIG_MAX`, `SIG_STEP` (columns on same table) |
| Broker selectbox (Phase 7) | not yet built | `REFDATA.APP` | `NAME` (label) |
| Ticker mapping (Phase 7) | not yet built | `REFDATA.TICKER_MAPPING` | `DATA_TICKER` → `BROKER_TICKER` |

### 11.2 REFDATA REST Endpoint

```
GET /api/v1/refdata/{table_name}
```

Returns all rows from the named REFDATA table. The backend validates `table_name` against an allow-list (same pattern as `SP_GET_ENUM`).

Response example (`GET /api/v1/refdata/indicator`):
```json
[
  {"indicator_id": 1, "name": "bollinger", "display_name": "Bollinger Band (z-score)", "method_name": "get_bollinger_band"},
  {"indicator_id": 2, "name": "sma", "display_name": "SMA", "method_name": "get_sma"},
  {"indicator_id": 3, "name": "ema", "display_name": "EMA", "method_name": "get_ema"},
  {"indicator_id": 4, "name": "rsi", "display_name": "RSI", "method_name": "get_rsi"}
]
```

Joined endpoint for indicator defaults:
```
GET /api/v1/refdata/indicator?include=defaults
```
```json
[
  {
    "indicator_id": 1, "name": "bollinger", "display_name": "Bollinger Band (z-score)",
    "method_name": "get_bollinger_band",
    "defaults": {"win_min": 10, "win_max": 100, "win_step": 5, "sig_min": 0.25, "sig_max": 2.50, "sig_step": 0.25}
  },
  ...
]
```

---

## 12. REFDATA Caching Layer

### 12.1 Problem

REFDATA tables are small (< 100 rows each), rarely change, and are read on every request (dropdown population, parameter validation, indicator lookup). Hitting PostgreSQL on every API call is unnecessary.

### 12.2 Design

```
                    ┌──────────────┐
                    │  PostgreSQL  │
                    │  :5433       │
                    └──────┬───────┘
                           │ startup + refresh
                    ┌──────▼───────┐
                    │ RefDataCache │  (in-process dict)
                    │ {table: rows}│
                    └──────┬───────┘
                           │ cache hit
              ┌────────────┼────────────┐
              │            │            │
      ┌───────▼──┐  ┌─────▼────┐  ┌───▼──────┐
      │ /refdata │  │ optimize │  │ validate │
      │ endpoint │  │ service  │  │ config   │
      └──────────┘  └──────────┘  └──────────┘
```

### 12.3 Implementation

```python
# api/services/refdata_cache.py

import logging
from functools import lru_cache
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

# Allow-list of tables the cache can load (prevents SQL injection)
REFDATA_TABLES = frozenset({
    "indicator", "signal_type", "asset_type", "data_column",
    "conjunction", "ticker_mapping", "app",
    "api_limit", "tm_interval", "order_state", "trans_state",
})


class RefDataCache:
    """In-process cache for REFDATA tables.

    Loaded once at startup, refreshable via .refresh().
    Thread-safe for reads (dict is immutable after load).
    """

    def __init__(self, conninfo: str):
        self._conninfo = conninfo
        self._store: dict[str, list[dict[str, Any]]] = {}

    def load_all(self) -> None:
        """Fetch all REFDATA tables into memory."""
        with psycopg.connect(self._conninfo) as conn:
            for table in REFDATA_TABLES:
                self._store[table] = self._fetch_table(conn, table)
        logger.info("RefDataCache loaded %d tables", len(self._store))

    def get(self, table: str) -> list[dict[str, Any]]:
        """Return cached rows for a REFDATA table."""
        if table not in REFDATA_TABLES:
            raise ValueError(f"Unknown REFDATA table: {table}")
        return self._store.get(table, [])

    def get_by_id(self, table: str, id_col: str, id_val: int) -> dict[str, Any] | None:
        """Lookup a single row by its ID column."""
        for row in self.get(table):
            if row.get(id_col) == id_val:
                return row
        return None

    def get_indicator_defaults(self) -> dict[str, dict]:
        """Return {method_name: {win_min, win_max, ...}} for backward compat."""
        result = {}
        for r in self.get("indicator"):
            result[r["method_name"]] = {
                "win_min": r["win_min"], "win_max": r["win_max"],
                "win_step": r["win_step"], "sig_min": float(r["sig_min"]),
                "sig_max": float(r["sig_max"]), "sig_step": float(r["sig_step"]),
            }
        return result

    def refresh(self) -> None:
        """Re-fetch all tables (call after REFDATA changes)."""
        self.load_all()

    @staticmethod
    def _fetch_table(conn, table: str) -> list[dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM refdata.{table}")  # table is from allow-list
            cols = [desc.name for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
```

### 12.4 FastAPI Integration

```python
# api/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from api.services.refdata_cache import RefDataCache

cache = RefDataCache(conninfo="host=localhost port=5433 dbname=quantdb ...")

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache.load_all()      # warm cache at startup
    yield                  # app runs
    # no cleanup needed

app = FastAPI(lifespan=lifespan)

def get_cache() -> RefDataCache:
    return cache

@app.get("/api/v1/refdata/{table_name}")
def get_refdata(table_name: str, cache: RefDataCache = Depends(get_cache)):
    return cache.get(table_name)

@app.post("/api/v1/refdata/refresh")
def refresh_refdata(cache: RefDataCache = Depends(get_cache)):
    cache.refresh()
    return {"status": "ok"}
```

### 12.5 Cache Properties

| Property | Value |
|---|---|
| Storage | In-process `dict[str, list[dict]]` |
| Warmup | `load_all()` at FastAPI startup via `lifespan` |
| Staleness | Acceptable — REFDATA changes are rare (admin-only). Manual refresh via `POST /refdata/refresh`. |
| Thread safety | Reads are safe (immutable snapshot). `refresh()` replaces the whole dict atomically. |
| DB target | `localhost:5433` (PostgreSQL via AWS SSM port-forward) |
| Fallback | If DB unreachable at startup, log error and fail fast — REFDATA is required for the app to function. |
| No TTL | No automatic expiry. REFDATA is admin-managed; changes are deployed then `POST /refdata/refresh`. |
