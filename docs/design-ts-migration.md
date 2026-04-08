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
frontend/               # React / TypeScript SPA (Vite)
  src/
    api/                # Generated API client (openapi-typescript-codegen)
    components/
      Sidebar.tsx       # Config panel (symbol, indicator, strategy, grid ranges)
      PipelineRunner.tsx# "Run Pipeline" button + progress bar
      OptGrid.tsx       # Top 10 table (DataGrid) + row-click drill-in
      Heatmap.tsx       # Plotly heatmap (single-factor & slice)
      EquityCurve.tsx   # Cumulative return + drawdown charts
      WalkForward.tsx   # IS vs OOS metrics comparison + split-line chart
      OverfitBadge.tsx  # Colour-coded overfitting ratio
    pages/
      BacktestPage.tsx  # Unified pipeline page (replaces app.py flow)
      StrategiesPage.tsx# CRUD list of saved strategies (Phase 7)
      DeployPage.tsx    # One-click deploy form (Phase 7)
    types/
      backtest.ts       # Request/response types (generated from OpenAPI)
    App.tsx
    main.tsx
  vite.config.ts
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

### M-3: React Scaffold + Sidebar

**Goal:** Basic SPA that can configure and submit a backtest.

- Vite + React + TypeScript scaffold in `frontend/`.
- `<Sidebar>` with all form fields matching app.py sidebar.
- API client generated from FastAPI OpenAPI spec.
- `<PipelineRunner>` button → calls optimize endpoint via WebSocket.
- Progress bar renders from WS stream.

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
