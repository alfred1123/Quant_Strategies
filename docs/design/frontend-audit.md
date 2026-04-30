# Frontend Code Quality Audit

A prioritized review of issues in the React/TypeScript frontend (`frontend/`), with concrete file references and remediation suggestions.

!!! success "Status — Hardening pass complete"
    All **Critical** and **High-priority** items below, plus several **Medium** items, were addressed in the frontend hardening pass. Remaining work is captured at the bottom of this document under "Open follow-ups".

## TL;DR

The frontend is small and consistent (MUI + TanStack Query + thin axios client). It avoids many common pitfalls (no `useEffect` in `src/`, controlled drawer, REFDATA-driven selects). However, it has:

- **Loose domain types** (`Top10Row` index signature) forcing `as` casts at boundaries
- **Async race conditions** in the `BacktestPage` lifecycle (optimize stream + per-row perf)
- **No SSE payload validation**
- **TypeScript `strict` mode is OFF**
- **God-component pressure** in `BacktestPage.tsx` (~349 lines, 12 `useState`)
- **Tooling debt** (Tailwind installed but unused, platform-specific dep in `dependencies`)

## Architecture today

```mermaid
flowchart LR
    App[App.tsx] --> BrowserRouter
    BrowserRouter -->|/login| GuestOnly
    BrowserRouter -->|/| RequireAuth
    GuestOnly -->|loading| Spinner
    GuestOnly -->|authed| "Redirect /"
    GuestOnly -->|guest| LoginPage
    RequireAuth -->|loading| Spinner
    RequireAuth -->|guest| "Redirect /login"
    RequireAuth -->|authed| BacktestPage
    BacktestPage --> ConfigDrawer
    ConfigDrawer --> FactorCard
    ConfigDrawer --> ProductSelector
    BacktestPage --> Top10Table
    BacktestPage --> MetricsCards
    BacktestPage --> EquityCurveChart
    BacktestPage --> HeatmapChart
    BacktestPage -->|fetch SSE| backtestApi
    LoginPage -->|axios| authApi
    ConfigDrawer -->|useQuery| refdataApi
    backtestApi --> apiClient
    authApi --> apiClient
    refdataApi --> apiClient
```

## Critical issues — likely bug source / runtime risk

- ✅ **`Top10Row` index signature hides shape** *(was `frontend/src/types/backtest.ts` lines 120–125)* — Replaced with a discriminated union `SingleFactorRow | MultiFactorRow` and a `utils/top10.ts` accessor module (`isSingleFactorRow`, `readNumber`, `multiFactorParams`). All call sites (`requestBuilders.ts`, `Top10Table.tsx`, `HeatmapChart.tsx`, `format.ts`) read window/signal through these helpers — no `as number` casts remain.
- ✅ **SSE payload not validated** *(was `frontend/src/api/backtest.ts` lines 59–63)* — `runOptimizeStream` now hand-parses each event (`init`, `progress`, `result`, `error`) via dedicated narrowers. Malformed JSON or wrong-shape payloads reject with a precise error rather than crashing inside `processChunk`. (Zod was deliberately not added — see Decision below.)
- ✅ **`response.body!` non-null assertion** *(was `frontend/src/api/backtest.ts` line 37)* — Replaced with an explicit `if (!response.body) reject(...)` plus a `settled`/`reader.cancel()` guard so the loop can't double-resolve.
- ✅ **Concurrent `loadPerf` race** *(was `frontend/src/pages/BacktestPage.tsx` lines 67–81)* — Per-request `AbortController` plus a monotonic `perfReqId` counter. Late responses from a previous selection are dropped.
- ✅ **Optimize stream not aborted on unmount or new run** — `BacktestPage` owns an `optimizeAbort` ref. `handleRun` aborts any in-flight stream before starting a new one; an unmount effect aborts on navigation away. `AbortError`s are silently ignored downstream.

## High-priority issues — maintainability / change risk

- ✅ **TypeScript `strict` mode is OFF** — Enabled in `frontend/tsconfig.app.json` along with `noImplicitOverride`. Build is clean under strict rules.
- ✅ **Validation duplicated and divergent** — Consolidated into `frontend/src/utils/validate.ts` (`validateBacktestConfig`, `firstValidationError`). `BacktestPage.handleRun` and `ConfigDrawer` both consume it, so the missing-field list cannot drift.
- ✅ **`analysisTab` not reset on new run** — `handleRun` now sets `setAnalysisTab(0)` alongside the other state resets.
- ⏳ **SSE uses `fetch`, REST uses `axios`** — Not yet unified (would change call shape across the codebase). Mitigated for now: the SSE `fetch` was given `credentials: 'include'` so the auth cookie travels the same way as `axios.withCredentials`. A single transport facade is captured in **Open follow-ups** below.
- ✅ **`Plot.ts` interop relies on `any`** — Refactored to a typed `unknown` narrowing pattern (`hasDefault`). No `// eslint-disable @typescript-eslint/no-explicit-any` directive is needed anymore.
- ✅ **Fragile auth error string match** — `client.ts` now throws a typed `ApiError` carrying `status: number | null`. `fetchMe` checks `err instanceof ApiError && err.status === 401` instead of comparing `err.message === 'Not authenticated'`.

## Medium-priority issues — code smells

- ✅ **`Top10Table` assumes all non-`sharpe` columns are numeric** — Cell formatter now narrows with `typeof value === 'number' && Number.isFinite(value)`; non-numeric values pass through as empty string instead of crashing `toFixed`.
- ✅ **Heatmap is O(signals × windows × grid)** — `buildHeatmapMatrix` builds a single `Map` keyed by `${window}|${signal}` in one pass, then materializes the matrix in O(W × S). Extracted as a pure function with unit tests in `HeatmapChart.test.ts`.
- ✅ **Magic threshold drift** — `overfitColor` and `overfitLabel` now share a single `OVERFIT_THRESHOLDS = { LOW: 0.3, HIGH: 0.5 }` constant; tests in `format.test.ts` cover both bands.
- ⏳ **`BacktestConfig` has both top-level `indicator/strategy/ranges` AND `factors[]`** — Not yet removed (would touch the public form contract; deferred to the "Backtest feature module" redesign in **Open follow-ups**).
- ✅ **Misleading user copy `alert_internal_cusip`** — Replaced with "No product set on Factor N — will use the main trading product."
- ⏳ **`FactorCard` casts nullable REFDATA numbers** — Not addressed in this pass; tracked as **Open follow-ups**. Low impact today (defaults exist) but worth tightening once REFDATA types tighten.
- ✅ **`ErrorBoundary` "Try Again" only clears boundary state** — Now bumps an internal `resetKey` and renders children inside `<div key={resetKey}>`, which forces React to remount the entire subtree so a re-throwing child gets a fresh attempt.
- ⏳ **`MetricsCards` magic metric names** — Not addressed; deferred until the backend exposes a canonical metric-units endpoint or the UI gets per-metric formatting from REFDATA.

## Low-priority — nice-to-have

- Charts not memoized; large literal `layout` rebuilt every render.
- Accessibility gaps: icon-only buttons without `aria-label` (e.g. `frontend/src/components/ConfigDrawer.tsx` line 89).
- Mixed styling: MUI `sx` + raw `style` + `<div>` (e.g. `frontend/src/components/MetricsCards.tsx` lines 30–31).
- **Tailwind installed but unused** — `frontend/package.json` lines 29–30, 41 + `frontend/vite.config.ts`. Zero `className=` in TSX. Either remove or adopt.
- **Platform-specific dep** — `@rolldown/binding-linux-x64-gnu` in `dependencies` in `frontend/package.json`. Unusual; usually managed by bundler.
- ESLint uses recommended only (no `strictTypeChecked`).

## Note on "no strict OOP"

React idiomatically uses **functional components, not OOP** — that's not a bad practice in itself. The real gap isn't classes, it's:

- **Domain modeling** (e.g. discriminated `SingleFactorRow | MultiFactorRow` instead of `[key: string]: unknown`)
- **Validation/parsing at boundaries** (Zod or hand-written parsers for SSE/REST responses)
- **Explicit lifecycle ownership** (one hook owns the optimize run + abort + perf load)

Whether implemented as classes, functions, or modules is a style choice. Adding classes for class's sake would not improve this codebase.

## Three larger redesign directions

1. **Backtest feature module + run-state hook** — Extract `useBacktestRun()` (or lightweight Zustand store) that owns: config snapshot, optimize stream with `AbortController`, perf load with abort/id, derived flags, and tab state derived from available analyses. Removes god-component pressure and fixes race/tab bugs systematically. **Touches:** `BacktestPage.tsx`, new `features/backtest/` folder.

2. **Typed API boundary + schema validation** — Replace ad hoc `as` casts with Zod schemas (or OpenAPI-generated types) shared between runtime parsing and tests. Single transport layer wrapping axios + streaming `fetch` with identical auth/error handling. Eliminates `Top10Row` escape hatch and SSE `as OptimizeResponse`. **Touches:** `api/`, `types/`.

3. **Presentation vs domain split for charts/tables** — Extract pure functions: "heatmap matrix from grid", "columns from Top10Row union", "equity plot specs from series". Components become thin and testable without Plotly/DataGrid. **Touches:** `components/HeatmapChart.tsx`, `Top10Table.tsx`, `EquityCurveChart.tsx`, new `domain/` helpers.

## Suggested remediation paths

Three options in increasing scope:

- **Surgical fixes** — Critical issues only. Small focused PR. Highest bug-prevention per hour invested.
- **Hardening pass** ✅ *delivered* — Critical + High. Adds strict TS, validation module, abort plumbing.
- **Full redesign** — All three redesigns above, staged over 3–4 PRs. Best long-term shape but the largest effort.

## Open follow-ups

Items deferred from the hardening pass, ordered by approximate impact:

1. **Single transport facade** — Wrap axios + streaming `fetch` so headers, credentials, error normalisation and `ApiError` shape live in one file. Today the SSE `fetch` mirrors the axios policy by hand (`credentials: 'include'`).
2. **Drop legacy top-level config fields** — `BacktestConfig.indicator/strategy/windowRange/signalRange` are no longer edited by the UI; the form drives `factors[]` exclusively. Removing them is a typed refactor and an opportunity to formalise the request contract.
3. **Backtest feature module + run-state hook** — Extract `useBacktestRun()` (or a small Zustand store) that owns the optimize stream, abort plumbing, perf load, derived flags and tab state. Removes the remaining god-component pressure in `BacktestPage.tsx`.
4. **REFDATA-driven metric formatting** — Replace `MetricsCards.PERCENT_KEYS` and `FactorCard`'s nullable `sig_min/max` defaults with values fetched from REFDATA (per the workspace's "REFDATA as Single Source of Truth" decision).
5. **Bundle/codesplitting** — Vite warns the production bundle exceeds 500 KB; lazy-load `react-plotly.js` and `@mui/x-data-grid` to drop initial JS.
6. **Tooling debt** — Either adopt Tailwind or remove it (zero `className=` usage today). Move `@rolldown/binding-linux-x64-gnu` out of `dependencies` once the Node 20 / rolldown native binding bug is resolved upstream.

## Decisions made during the hardening pass

- **No Zod** — SSE payloads are validated with hand-written narrowers. Adding a runtime-schema dependency is overkill for four event shapes; if a fifth or sixth event type appears the calculus may flip.
- **`ApiError` over status codes only** — `apiClient` throws `ApiError(message, status)` so callers can branch on either `instanceof ApiError` or `err.status === 401`. Keeps backward-compat with consumers that just want `err.message` for display.
- **Discriminated union over Zod-style parser for `Top10Row`** — The shape is fixed by the backend; a TypeScript discriminated union plus `utils/top10.ts` accessors gives compile-time safety without runtime overhead.
- **`react-router-dom` for route separation** — Login (`/login`) and backtest (`/`) now live at distinct URLs via `BrowserRouter`. `RequireAuth` and `GuestOnly` route wrappers handle redirects. `BacktestPage` reads `currentUser` from `useMe()` directly (no prop drilling). Logout and 401 interceptor both navigate to `/login`. Nginx `try_files` already covers client-side routing fallback.
