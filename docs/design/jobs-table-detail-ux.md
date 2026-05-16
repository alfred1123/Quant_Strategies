# Design: Jobs Table — Hover Preview vs Detail Drawer

**Status:** proposed (not yet implemented)  
**Date:** 2026-05-16  
**Related:** [Backtest Queue](backtest-queue.md) (`/api/v1/jobs/*`, `frontend/src/features/queue/`)

Hover preview and row-detail drawer **serve different jobs**. The recommendation is to ship **both**, with clearly separated roles rather than choosing one.

## Surface comparison

| Surface | Trigger | Purpose | Content depth |
|---------|---------|---------|----------------|
| **Hover preview** | Mouse over Strategy cell, ~400 ms delay | “Is this the run I think it is?” — glance check without losing table context | Strategy name, interval, asset, factor count, top 3 factors summarized |
| **Detail drawer** | Click row (anywhere except action buttons) | “Show me everything” — full audit, debug, copy/export, future re-run with edits | Full strategy + queue + result + JSON tab + actions |

## Why both (not one)

- **Hover-only** forces a hover-and-read pattern that hides everything beyond ~6 lines and cannot host actions (Cancel / Re-run / Copy JSON / Download). Power tasks need a real container.
- **Click-only** loses the “scan many rows quickly” affordance — every inspection costs navigation plus close.
- **Implementation overlap:** both can share the same **JobDetail** payload and the same React renderer with two layouts (**compact** vs **full**).

## Recommended UX shape

Use a **right-side drawer** (not a modal dialog, not a new route): MUI `Drawer` with `anchor="right"` and width **560px**.

```
┌─ Job · BTC-USD · Bollinger×RSI ──────── [×] ─┐
│ Status: COMPLETED   Priority: normal         │
│ Submitted: 2026-05-16 14:32   Duration: 8.4s │
│ Queue ID: a1b2…   Strategy VID: 3            │
├──────────────────────────────────────────────┤
│ [ Strategy ] [ Result ] [ Raw JSON ] [ Logs ]│  ← MUI Tabs
├──────────────────────────────────────────────┤
│ Strategy                                     │
│   Interval: daily   Source: yahoo            │
│   Date range: 2020-01-01 → 2026-05-15        │
│                                              │
│ Factor 1 · Bollinger Bands                   │
│   window=20  threshold=2.0  source=close     │
│ Factor 2 · RSI                               │
│   window=14  threshold=30   source=close     │
│ Conjunction: AND                             │
├──────────────────────────────────────────────┤
│ [ Copy JSON ]  [ Clone & edit ]  [ Re-run ]  │
└──────────────────────────────────────────────┘
```

### Key choices

1. **Drawer, not Dialog** — Non-blocking; the table stays visible behind it so the user can click another row to swap content. A modal breaks the “scan list” flow.
2. **Tabs inside the drawer** — **Strategy** (friendly), **Result** (performance metrics + chart link), **Raw JSON** (escape hatch), **Logs** (when worker logs are exposed). One drawer serves casual and power users.
3. **Row interaction** — Click anywhere on the row to open; keep **Cancel** / **Re-run** as row-level buttons (current behavior) **and** duplicate them in the drawer footer. Do not remove row actions — bulk Cancel without opening drawers stays faster.
4. **Hover preview** remains the “stop early” affordance: if hover already answers the question, no click is needed.
5. **Deep-link the drawer** — URL query `?job=<queue_id>` opens the drawer on load. Low cost, shareable links (Slack, issues), and aligns with future batch flows where each batch result links to its drawer.

## Tying to batch input / export

The drawer is the natural home for two future flows:

- **Clone & edit** — Opens the config drawer pre-filled from this job’s `config_json`. Preferred path for “re-run with one knob tweaked.”
- **Export selected as batch JSON** — Multi-select rows → bulk-export an array of `config_json` blobs. That array matches the format a future **batch import** accepts, with no extra schema.

**Contract:** one **StrategyConfig** JSON schema powers the enqueue endpoint, clone/edit, hover preview, drawer Strategy tab, Raw JSON tab, and batch import/export — single source of truth, no format drift.

## Suggested phasing

| Phase | Scope |
|-------|--------|
| **1** (~half day) | Include `config_json` in `GET /jobs` list response → hover tooltip with friendly summary + Copy JSON. |
| **2** | Detail drawer with tabs (Strategy / Raw JSON / Result). Row click opens; row buttons unchanged. |
| **3** | Wire **Clone & edit** (drawer → ConfigDrawer pre-fill). |
| **4** | Multi-select + bulk export, then batch-import upload (CSV/JSON drop zone behind a **New batch** entry point). |

**PR scoping:** Phase 1 can ship alone; Phase 2 uses the same data plumbing. Combining Phase 1 + 2 in one PR is reasonable if the team prefers fewer integration passes.
