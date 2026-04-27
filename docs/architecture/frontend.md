# React Frontend

A single-page React + TypeScript application that replaces the Streamlit dashboard as the primary UI.

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| UI Framework | React | 19 |
| Build Tool | Vite | 8 |
| Language | TypeScript | 6 |
| Component Library | MUI (Material UI) | 9 |
| CSS | Tailwind CSS | 4 |
| Data Fetching | TanStack React Query | 5 |
| HTTP Client | Axios | 1 |
| Charting | Plotly.js (react-plotly.js) | 3 |

## Starting the Dev Server

```bash
# Requires the FastAPI backend running on :8000
cd frontend && npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/v1` requests to the backend.

## Features

- **Configure** button in the topbar opens a top drawer with all backtest settings
- **Dropdowns** (indicator, strategy, asset type, conjunction, data column) populated live from `REFDATA` tables
- Selecting an **indicator** auto-fills window and signal range defaults from `REFDATA.INDICATOR`
- **Data Column** selector per factor — choose Price or Volume as the indicator input
- **Single-factor** and **multi-factor** modes — add up to 2 factors per run
- **Conjunction** selector (AND / OR / FILTER) between factors
- **Trial count** shown before running — displays actual trial count with cap awareness (max 10,000)
- On **Run**: drawer closes, **SSE progress bar** streams real-time trial progress
- **Top-10 results table** (MUI DataGrid) — best row highlighted; each row has a **View Analysis** button
- Analysis panel: side-by-side metrics cards + Sharpe heatmap + equity curve + drawdown chart
- **Walk-forward analysis** — in-sample vs out-of-sample comparison with overfitting ratio
- **CSV download** of full grid search results
- **Authentication** — cookie-based login; 401 interceptor auto-redirects to login page

## Project Structure

```
frontend/src/
├── main.tsx              # React root — mounts <App />
├── App.tsx               # Theme, auth gate, top-level layout
├── index.css             # Global styles
│
├── types/                # TypeScript interfaces (no logic)
│   ├── backtest.ts       # BacktestConfig, FactorConfig, API request/response types
│   └── refdata.ts        # IndicatorRow, AssetTypeRow, ProductRow, etc.
│
├── api/                  # HTTP + data-fetching layer
│   ├── client.ts         # Axios instance (baseURL, credentials, 401 interceptor)
│   ├── refdata.ts        # React Query hooks: useIndicators(), useAssetTypes(), etc.
│   ├── inst.ts           # useProducts() hook
│   ├── backtest.ts       # runOptimizeStream() (SSE), runPerformance(), runWalkForward()
│   └── auth.ts           # useMe(), login(), logout()
│
├── lib/                  # Shared singletons
│   ├── queryClient.ts    # TanStack Query client (shared so interceptors can mutate cache)
│   └── Plot.ts           # Plotly CJS interop wrapper
│
├── utils/
│   └── grid.ts           # countSteps() — calculates grid search trial count
│
├── components/           # Reusable UI components
│   ├── ConfigDrawer.tsx  # Top drawer — composes ProductSelector + FactorCards
│   ├── config/
│   │   ├── ProductSelector.tsx  # Product autocomplete with vendor symbol override
│   │   ├── FactorCard.tsx       # Indicator/strategy/ranges for one factor
│   │   └── RangeFields.tsx      # Min/max/step input group
│   ├── Top10Table.tsx    # MUI DataGrid for top-10 results
│   ├── MetricsCards.tsx  # Strategy vs buy-hold metric cards
│   ├── HeatmapChart.tsx  # Plotly Sharpe heatmap (window × signal)
│   ├── EquityCurveChart.tsx  # Plotly equity + drawdown chart
│   ├── UserMenu.tsx      # User avatar + logout
│   └── ErrorBoundary.tsx # React error boundary
│
└── pages/
    ├── BacktestPage.tsx  # Main page — orchestrates config, optimization, results
    └── LoginPage.tsx     # Login form
```

## Reading Guide — Where to Start

Read the code in this order. Each layer builds on the previous one.

### Layer 1: Types (`types/`) — read first

These files contain only TypeScript `interface` definitions — no logic, no imports. They define the shape of every data object in the app.

- **`backtest.ts`** — `BacktestConfig` (form state), `FactorConfig` (one factor's settings), `OptimizeRequest` / `OptimizeResponse` (API contracts), `Top10Row`, `EquityPoint`
- **`refdata.ts`** — `IndicatorRow`, `SignalTypeRow`, `AssetTypeRow`, `ConjunctionRow`, `DataColumnRow`, `AppRow`, `ProductRow`, `XrefRow`

Once you know these shapes, every function signature and component prop makes sense.

### Layer 2: API (`api/`) — how data is fetched

- **`client.ts`** — Creates an Axios instance with `baseURL: '/api/v1'` and `withCredentials: true`. The response interceptor normalises errors and evicts the auth cache on 401.
- **`refdata.ts`** — One React Query hook per REFDATA table. Each hook calls `GET /api/v1/refdata/{table}` and caches forever (`staleTime: Infinity`).
- **`inst.ts`** — `useProducts()` — same pattern for the product list.
- **`backtest.ts`** — `runOptimizeStream()` opens an SSE stream (`POST /backtest/optimize/stream`), calls `onProgress` per trial, and resolves with the final result. `runPerformance()` and `runWalkForward()` are simple POST calls.
- **`auth.ts`** — `useMe()` probes `GET /auth/me` on mount. `login()` / `logout()` hit POST endpoints.

### Layer 3: Utilities (`lib/`, `utils/`)

- **`queryClient.ts`** — Shared TanStack Query client. Exported separately so the Axios 401 interceptor can mutate the auth cache from outside React.
- **`Plot.ts`** — Handles CJS/ESM interop for `react-plotly.js`.
- **`grid.ts`** — `countSteps({ min, max, step })` returns how many discrete values a range produces.

### Layer 4: Components (`components/`) — UI building blocks

- **`config/RangeFields.tsx`** — Three `<TextField>` inputs (min, max, step). Smallest unit.
- **`config/FactorCard.tsx`** — One factor: indicator dropdown, strategy dropdown, data column, window range, signal range. Uses `RangeFields`.
- **`config/ProductSelector.tsx`** — Autocomplete for picking a product or entering a vendor symbol directly.
- **`ConfigDrawer.tsx`** — Composes `ProductSelector` + 1–2 `FactorCard`s + date/fee/walk-forward controls. The `set()` helper merges partial updates into config state.
- **`Top10Table.tsx`**, **`MetricsCards.tsx`**, **`HeatmapChart.tsx`**, **`EquityCurveChart.tsx`** — Results display. Each receives data via props.

### Layer 5: Pages (`pages/`) — orchestration

- **`BacktestPage.tsx`** — The main page. Owns all state (`useState` for config, results, progress, errors). Wires `ConfigDrawer` → `buildOptimizeRequest()` → `runOptimizeStream()` → results components. This is the file to read to understand the full data flow.
- **`App.tsx`** — Auth gate: loading spinner → `LoginPage` → `BacktestPage`. Also sets up the MUI dark theme.
- **`main.tsx`** — Mounts `<App />` inside `<QueryClientProvider>` and `<StrictMode>`.

## Key Patterns

### Custom hooks for data fetching

```typescript
const { data: indicators = [] } = useIndicators();
```

Each `use*()` hook wraps a TanStack Query call. The `= []` provides a default while loading. The hook handles caching, deduplication, and error state automatically.

### Immutable state updates with patch objects

```typescript
const set = (patch: Partial<BacktestConfig>) =>
  onChange(prev => ({ ...prev, ...patch }));
```

`set({ feeBps: 10 })` merges `{ feeBps: 10 }` into the existing config, leaving all other fields untouched. The same pattern applies to `updateFactor()` for nested factor updates.

### SSE streaming for optimization progress

`runOptimizeStream()` in `api/backtest.ts` uses the Fetch API's `ReadableStream` to parse Server-Sent Events. The stream emits three event types:

1. `init` / `progress` → updates the progress bar
2. `result` → resolves the promise with the final `OptimizeResponse`
3. `error` → rejects with an error message

### Auth via cookie + interceptor

Login sets an `HttpOnly` cookie (`qs_token`). The Axios interceptor watches for 401 responses and clears the cached user (`queryClient.setQueryData(['auth', 'me'], null)`), which triggers React to re-render the login page.

## REFDATA Integration

All dropdowns are populated from the backend `GET /api/v1/refdata/{table_name}` endpoint. The frontend caches these with TanStack Query (`staleTime: Infinity` — REFDATA rarely changes).

| Dropdown | Hook | REFDATA Table |
|----------|------|---------------|
| Indicator | `useIndicators()` | `REFDATA.INDICATOR` |
| Strategy | `useSignalTypes()` | `REFDATA.SIGNAL_TYPE` |
| Asset Type | `useAssetTypes()` | `REFDATA.ASSET_TYPE` |
| Conjunction | `useConjunctions()` | `REFDATA.CONJUNCTION` |
| Data Column | `useDataColumns()` | `REFDATA.DATA_COLUMN` |
| App (data source) | `useApps()` | `REFDATA.APP` |

## Build for Production

```bash
cd frontend && npm run build
# Outputs to frontend/dist/ — serve via FastAPI's StaticFiles or any CDN
```

Available npm scripts:

| Command | What it does |
|---------|-------------|
| `npm run dev` | Start Vite dev server (hot reload) |
| `npm run build` | Type-check with `tsc -b` then build for production |
| `npm run lint` | Run ESLint |
| `npm run preview` | Preview the production build locally |
