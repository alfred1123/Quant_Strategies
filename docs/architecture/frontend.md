# React Frontend

A single-page React + TypeScript application that replaces the Streamlit dashboard as the primary UI.

## Starting the Dev Server

```bash
# Requires the FastAPI backend running on :8000
cd frontend && npm run dev
```

Open `http://localhost:5173`

## Features

- **Configure** button in the topbar opens a collapsible left drawer with all backtest settings
- **Dropdowns** (indicator, strategy, asset type, conjunction, data column) populated live from `REFDATA` tables
- Selecting an **indicator** auto-fills window and signal range defaults from `REFDATA.INDICATOR`
- **Data Column** selector per factor — choose Price or Volume as the indicator input
- **Single-factor** and **multi-factor** modes — add up to 2 factors per run
- **Conjunction** selector (AND / OR / FILTER) between factors
- **Trial count** shown before running — displays actual trial count with cap awareness (max 10,000)
- On **Run**: drawer closes, **SSE progress bar** streams real-time trial progress
- **Top-10 results table** (MUI DataGrid) — best row highlighted; each row has a **View Analysis** button
- Analysis panel: side-by-side metrics cards + Sharpe heatmap + equity curve + drawdown chart
- **CSV download** of full grid search results

## Project Structure

```
frontend/src/
├── api/              # Axios client + TanStack Query hooks (backtest, refdata, SSE streaming)
├── components/       # ConfigDrawer, Top10Table, MetricsCards, HeatmapChart, EquityCurveChart
├── pages/            # BacktestPage (single-page layout with SSE progress bar)
├── types/            # TypeScript types for backtest, refdata, and SSE progress
├── lib/              # Shared utilities
└── utils/            # Helper functions
```

## REFDATA Integration

All dropdowns are populated from the backend `GET /api/v1/refdata/{table_name}` endpoint. The frontend caches these with TanStack Query (`staleTime: Infinity` — REFDATA rarely changes).

| Dropdown | Hook | REFDATA Table |
|----------|------|---------------|
| Indicator | `useIndicators()` | `REFDATA.INDICATOR` |
| Strategy | `useSignalTypes()` | `REFDATA.SIGNAL_TYPE` |
| Asset Type | `useAssetTypes()` | `REFDATA.ASSET_TYPE` |
| Conjunction | `useConjunctions()` | `REFDATA.CONJUNCTION` |
| Data Column | `useDataColumns()` | `REFDATA.DATA_COLUMN` |

## Build for Production

```bash
cd frontend && npm run build
# Outputs to frontend/dist/ — serve via FastAPI's StaticFiles or any CDN
```
