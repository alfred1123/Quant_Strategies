# React Frontend

A single-page React + TypeScript application that replaces the Streamlit dashboard as the primary UI.

See [System Overview](overview.md) for product surfaces and [Trade UI](#trade-ui-phase-14) below for the live-trading shell.

!!! note "See also"
    The [Frontend Code Audit](../design/frontend-audit.md) lists known design issues and remediation directions.

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| UI Framework | React | 19 |
| Build Tool | Vite | 8 |
| Language | TypeScript | 6 |
| Component Library | MUI (Material UI) | 9 |
| Icons | @mui/icons-material | 9 |
| Data Fetching | TanStack React Query | 5 |
| Routing | React Router | 8 |
| HTTP Client | Axios | 1 |
| Charting | Plotly.js 3 + react-plotly.js 2 | — |
| Tests | Vitest 4 + Testing Library + happy-dom | — |

See `frontend/package.json` for exact pinned versions.

## Theming

All design tokens live in `src/theme.ts` — a single MUI dark theme (deep-navy surfaces, blue accent, Inter font stack loaded in `index.html`, softened corners, sentence-case buttons, styled scrollbars). Components must use theme tokens (`background.paper`, `divider`, `primary.main`) rather than hard-coded colors, and MUI icons (`@mui/icons-material`) rather than emoji glyphs. The shared `BrandMark` component renders the gradient app logo in the login card and both top bars.

## Starting the Dev Server

```bash
# Requires the FastAPI backend running on :8000
cd frontend && npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` requests to the backend (default `http://localhost:8000`, overridable via `VITE_API_URL`).

## Pipeline Tab Model

The Backtest SPA uses a four-tab pipeline. Each tab represents a stage in the strategy lifecycle:

| Tab | Route | Purpose |
|-----|-------|---------|
| **Backtest** | `/backtest` (tab 0) | Configure params, submit optimization job |
| **Queue** | `/backtest` (tab 1) | Monitor job status, view results, clone, manual promote |
| **Promotion** | `/backtest` (tab 2) | Compare VIDs, see gate results, recommended picks, re-backtest to improve, deploy to Trade |
| **Trade** | `/trade/*` | Config (exchange accounts), Apply (deploy strategy, execution log) |

See [Best-VID Promotion §5](../design/best-vid-promotion.md#5-ui-pipeline-tab-model) for the Promotion tab design.

## Features

- **Configure** button in the topbar opens a top drawer with all backtest settings
- **Dropdowns** (indicator, strategy, asset type, conjunction, data column) populated live from `REFDATA` tables
- Selecting an **indicator** auto-fills window and signal range defaults from `REFDATA.INDICATOR`
- **Data Column** selector per factor — choose Price or Volume as the indicator input
- **Factor list** — add up to 2 factors per run (1 = single factor, 2 = multi factor); the request always serializes as a `factors: [...]` list, never with separate top-level indicator/window fields
- **Conjunction** selector (AND / OR / FILTER) — surfaced only when there are 2+ factors. FILTER labels the cards **Gate / Signal** (factor 1 gates, factor 2 directs; Decision #6)
- **Trial count** shown before running — displays actual trial count with cap awareness (max 10,000)
- On **Run**: drawer closes, **SSE progress bar** streams real-time trial progress
- **Top-10 results table** (MUI DataGrid) — best row highlighted; each row has a **View Analysis** button
- Analysis panel: side-by-side metrics cards + Sharpe heatmap + equity curve + drawdown chart
- **Walk-forward analysis** — in-sample vs out-of-sample comparison with overfitting ratio
- **CSV download** of full grid search results
- **Queue tab** — jobs table with VID column (`v{N}` + "Best" chip), status filter chips, View/Clone/Promote actions
- **Authentication** — cookie-based login; 401 interceptor auto-redirects to `/login`
- **Client-side routing** — `/login` (guest-only), `/backtest`, `/trade/config`, `/trade/apply` (auth-required) via `react-router`
- **Trade UI (Phase 1.4+)** — multi-broker layout with compact Exchange / Account filters, Paper / Live toggle, accounts table on Config (credentials CRUD), deployments table on Trade (see [Trade UI](#trade-ui-phase-14) below)

## Trade UI (Phase 1.4+)

Routes under `/trade` (auth-required). `AppModeSwitch` in the header toggles Backtest vs Trade mode.

| Route | Page | Purpose |
|-------|------|---------|
| `/trade/config` | `TradeConfigPage` | Register broker accounts — table + compact add form |
| `/trade/apply` | `TradeApplyPage` | Strategy picker, live account snapshot, deployments table, dry-run / apply buttons |

**Layout:** `TradeLayout` — permanent sidebar (Config \| Trade), **filter toolbar** (`TradeNavBar`), main content (`<Outlet />`), bottom **`ExecutionLogPanel`** (release 1.8.0 — order attempts + fills via `GET /trade/execution-events` / `/trade/transactions`; placeholder until that release deploys).

**Session state:** `TradeSessionProvider` (`trade/TradeSessionContext.tsx`; the `useTradeSession` / `useTradeSessionFilters` hooks live in `trade/useTradeSession.ts`) holds:

- `brokerFilter` / `accountFilter` — toolbar Exchange and Account dropdowns (`ALL_BROKERS` / `ALL_ACCOUNTS` = no filter)
- `tradingMode` — `'paper' | 'live'` toggle
- `accounts` — from `useBrokerAccounts()` → `GET /api/v1/credentials`
- `matchesSession()` — filters deployment rows by toolbar selection

**Components:**

| Component | Role |
|-----------|------|
| `TradeNavBar` | Compact Exchange (~160px) + Account (~200px) selects; Paper / Live `ToggleButtonGroup` |
| `BrokerAccountsTable` | Exchange · Account · masked key · Status; **Rotate** / **Revoke** dialogs; row click sets account filter |
| `TradeConfigPage` | Accounts table + add-account form wired to credentials API (create) |
| `StrategyPicker` | Selectable caller-owned `BT.STRATEGY` catalog via `GET /api/v1/strategies` |
| `DeploymentDialog` | Create deployment — strategy, account, qty, schedule dropdown, live/paper confirmation |
| `ScheduleCell` | Cadence per deployment row, editable in place; `useTmIntervals()` + `PATCH /trade/deployments/{id}` |
| `ExecutionLogPanel` | Recent order attempts and fills across the session's deployments |
| `AccountSnapshotPanel` | Live cash + open positions for the selected account via `useAccountSnapshot()`; read-only |
| `TradeApplyPage` | Strategy picker + Deploy button + account snapshot + deployments table; `useDeployments()` |

**Account snapshot panel**

Sits above the deployments table and reads
`GET /api/v1/trade/accounts/{id}/snapshot`, so it shows the exchange's own view
of the account rather than ours — including positions no deployment opened.

It takes both inputs from the existing toolbar rather than adding controls:
`accountFilter` picks the credential and the Paper / Live toggle picks the
environment. A snapshot is one call to one exchange account, so `ALL_ACCOUNTS`
has no sensible answer; the panel then asks the user to choose an account and
sets `accountFilter` from its own selector.

Deliberately not polled — each render would be a rate-limited exchange call.
The query key includes the paper flag, so demo and real accounts never share a
cache entry, and refresh is manual behind a 30s stale window.

**Schedule control — the one switch that automates a deployment**

`DeploymentDialog` sets the cadence on create and the Schedule column's
`ScheduleCell` edits it afterwards, both offering *Manual* plus every
`REFDATA.TM_INTERVAL` row (`DISPLAY_NAME` for the label, `NAME` as a fallback for
a database predating that column). **Manual is the default and a real option, not
an empty one** — picking it sends an explicit `null`, which the backend
distinguishes from an omitted field.

Choosing a cadence is also what puts the product's price data on the platform's
hourly warm, because `SP_GET_SCHEDULED_INSTRUMENTS` returns exactly the enabled,
non-manual deployments. There is deliberately no separate "sync price data"
toggle for a deployed product.

Automating a **live** deployment asks a second time — its own checkbox in the
dialog, a `window.confirm` on the inline edit — because the existing live
confirmation covers one attended order, not an unattended hourly cadence.
Switching Paper / Live re-arms it.

**Strategy picker — not Backtest config UI**

The Backtest **Strategy** dropdown in `FactorCard` is a REFDATA `signal_type` (momentum, etc.) used to *build* an optimize request. The Trade/Promotion picker selects a **persisted** `BT.STRATEGY` row (`strategy_id`, `strategy_vid`, `strategy_nm`) for deployment or comparison. Do not reuse `ConfigDrawer` / `FactorCard`.

| Backtest | Trade / Promotion picker |
|----------|--------------------------|
| `FactorCard` → REFDATA signal type | `StrategyPicker` → caller-owned `BT.STRATEGY` rows |
| Creates config for new job | Selects existing strategy for deploy or comparison |
| `POST /api/v1/backtest/jobs` | `GET /api/v1/strategies` |

The picker lists only the caller's own `BT.STRATEGY` rows (`SP_GET_STRATEGY_LIST`
filters by `IN_USER_ID`). [Decision #42](../decisions.md) describes a shared pool
as the long-term intent; the current API and UI are owner-scoped. See
[Best-VID Promotion §6](../design/best-vid-promotion.md#6-shared-strategy-pool).

Dropdowns use MUI `size="small"` and fixed widths — not full-width form fields.

## Project Structure

```
frontend/src/
├── main.tsx              # React root — mounts <App />
├── App.tsx               # BrowserRouter, RequireAuth/GuestOnly route guards
├── theme.ts              # MUI dark theme — single source of design tokens
├── index.css             # Global styles (font smoothing, selection, tabular-nums)
│
├── types/                # TypeScript interfaces (no logic)
│   ├── backtest.ts       # BacktestConfig, FactorConfig, API request/response types
│   ├── credentials.ts    # BrokerAccount, TradingMode, filter constants
│   ├── jobs.ts           # JobRow, JobDetail, JobStatus — queue table types
│   ├── promotion.ts      # PromotionRow — Promotion tab types
│   ├── refdata.ts        # IndicatorRow, AssetTypeRow, ProductRow, AppRow, etc.
│   ├── strategies.ts     # StrategyListRow — strategy picker types
│   └── trade.ts          # DeploymentRow, create-deployment request (Phase 1.2)
│
├── api/                  # HTTP + data-fetching layer
│   ├── client.ts         # Axios instance (baseURL, credentials, 401 interceptor)
│   ├── refdata.ts        # React Query hooks: useIndicators(), useAssetTypes(), etc.
│   ├── inst.ts           # useProducts() hook
│   ├── backtest.ts       # runOptimizeStream() (SSE), runPerformance(), runWalkForward()
│   ├── auth.ts           # useMe(), login(), logout()
│   ├── jobs.ts           # useJobs(), useEnqueueJob(), useCancelJob(), usePromoteStrategy(), fetchJob()
│   ├── promotion.ts      # usePromotions() — Promotion tab
│   ├── strategies.ts     # useStrategies() — strategy picker
│   ├── trade.ts          # useDeployments(), useCreateDeployment(), useExecutionEvents(), useAccountSnapshot()
│   └── credentials.ts    # useBrokerAccounts(), useCreateCredential(), useRotateCredential(), useRevokeCredential()
│
├── trade/
│   ├── TradeSessionContext.tsx  # TradeSessionProvider component (Phase 1.4)
│   └── useTradeSession.ts       # Context + useTradeSession / useTradeSessionFilters hooks
│
├── lib/                  # Shared singletons
│   ├── queryClient.ts    # TanStack Query client (shared so interceptors can mutate cache)
│   └── Plot.ts           # Plotly CJS interop wrapper
│
├── utils/
│   ├── grid.ts            # countSteps() — calculates grid search trial count
│   ├── format.ts          # overfitColor/Label, formatMetric, rowLabel
│   ├── heatmap.ts         # buildHeatmapMatrix() — pure Sharpe-matrix builder
│   ├── requestBuilders.ts # effectiveSymbol, buildOptimizeRequest, buildPerformanceRequest
│   ├── top10.ts           # isSingleFactorRow, readNumber, multiFactorParams (type-safe Top10Row accessors)
│   └── validate.ts        # validateBacktestConfig, firstValidationError
│
├── test/
│   ├── setup.ts           # Vitest global setup (jest-dom matchers)
│   └── wrapper.tsx        # renderWithProviders helper (QueryClient + MUI theme)
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
│   ├── JobsTable.tsx     # Queue tab — MUI DataGrid with VID/Best chip, status filters, actions
│   ├── PromotionTab.tsx  # Promotion tab — VID comparison, gate results, deploy link
│   ├── UserMenu.tsx      # User avatar + logout
│   ├── AppModeSwitch.tsx # Backtest | Trade header toggle
│   ├── BrandMark.tsx     # Gradient app logo — login card + top bars
│   ├── ErrorBoundary.tsx # React error boundary
│   └── trade/
│       ├── TradeNavBar.tsx         # Exchange / Account filters + Paper / Live toggle
│       ├── BrokerAccountsTable.tsx # Multi-broker accounts table (Config page)
│       ├── StrategyPicker.tsx      # BT.STRATEGY catalog table (Phase 1.6)
│       ├── DeploymentDialog.tsx    # Create deployment + schedule dropdown
│       ├── ApplyConfirmDialog.tsx  # Live apply confirmation
│       ├── DryRunReportDialog.tsx  # Dry-run report viewer
│       ├── AccountSnapshotPanel.tsx # Live cash + open positions (Apply page)
│       ├── ScheduleCell.tsx         # Per-deployment cadence, editable in place
│       └── ExecutionLogPanel.tsx    # Recent order attempts and fills
│
├── layouts/
│   └── TradeLayout.tsx   # Trade shell — sidebar, toolbar, outlet, execution log
│
└── pages/
    ├── BacktestPage.tsx  # Main page — orchestrates config, optimization, results
    ├── LoginPage.tsx     # Login form
    └── trade/
        ├── TradeConfigPage.tsx  # Exchange accounts table + add form
        └── TradeApplyPage.tsx   # StrategyPicker + account snapshot + deployments table
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
- **`interval.ts`** — Parses `TM_INTERVAL.PERIOD_LENGTH` into `barsPerDay`. `scaleWindowRange` multiplies a daily-bar `WIN_*` grid by that factor so lookback stays in calendar days when the cadence is not daily.

### Layer 4: Components (`components/`) — UI building blocks

- **`config/RangeFields.tsx`** — Three `<TextField>` inputs (min, max, step). Smallest unit.
- **`config/FactorCard.tsx`** — One factor: indicator dropdown, strategy dropdown, data column, window range, signal range. Uses `RangeFields`. Picking an indicator applies REFDATA defaults; the window grid is scaled by bars-per-day.
- **`config/ProductSelector.tsx`** — Autocomplete for picking a product or entering a vendor symbol directly.
- **`ConfigDrawer.tsx`** — Composes `ProductSelector` + 1–2 `FactorCard`s + date/fee/walk-forward controls. The `set()` helper merges partial updates into config state. Changing Bar Interval rescales `trading_period` and every factor's `window_range` by bars-per-day.
- **`Top10Table.tsx`**, **`MetricsCards.tsx`**, **`HeatmapChart.tsx`**, **`EquityCurveChart.tsx`** — Results display. Each receives data via props.

### Layer 5: Pages (`pages/`) — orchestration

- **`BacktestPage.tsx`** — The main page. Owns all state (`useState` for config, results, progress, errors). Wires `ConfigDrawer` → `buildOptimizeRequest()` → `runOptimizeStream()` → results components. This is the file to read to understand the full data flow. Reads `currentUser` from `useMe()` hook directly.
- **`App.tsx`** — Sets up `BrowserRouter`, the shared MUI dark theme (`theme.ts`), and `ErrorBoundary`. Routes: `/login`, `/backtest`, `/trade/config`, `/trade/apply` (nested under `TradeLayout`). `RequireAuth` / `GuestOnly` wrappers gate auth.
- **`LoginPage.tsx`** — Login form. On success, navigates to `/` (or the page that triggered the auth redirect via `location.state.from`).
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

### Auth via cookie + interceptor + routing

Login sets an `HttpOnly` cookie (`qs_token`). The Axios interceptor watches for 401 responses, clears the cached user (`queryClient.setQueryData(['auth', 'me'], null)`), and calls `window.location.replace('/login')` to redirect the browser. The `RequireAuth` route wrapper in `App.tsx` also redirects unauthenticated users to `/login` on initial page load, preserving the original URL in `location.state.from` so the user returns there after signing in.

## REFDATA Integration

All dropdowns are populated from the backend `GET /api/v1/refdata/{table_name}` endpoint. The frontend caches these with TanStack Query (`staleTime: Infinity` — REFDATA rarely changes).

| Dropdown | Hook | REFDATA Table |
|----------|------|---------------|
| Indicator | `useIndicators()` | `REFDATA.INDICATOR` |
| Strategy | `useSignalTypes()` | `REFDATA.SIGNAL_TYPE` |
| Asset Type | `useAssetTypes()` | `REFDATA.ASSET_TYPE` |
| Conjunction | `useConjunctions()` | `REFDATA.CONJUNCTION` |
| Data Column | `useDataColumns()` | `REFDATA.DATA_COLUMN` |
| App (data source / exchange) | `useApps()` | `REFDATA.APP` (`IS_EXCHANGE_IND` filters broker dropdown on Trade Config) |

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
| `npm test` | Run all Vitest tests once |
| `npm run test:watch` | Vitest in watch mode |
