# Plan: Read-Only JSON Viewer for Backtest Queue Tab

## Overview

Add a **"Config"** button to the Backtest Queue table that opens a dialog showing the strategy configuration in a readable JSON format.

---

## Change Impact

| Layer | Change Required? | Reason |
|-------|------------------|--------|
| **Database** | ❌ No | Config data already exists in `BT.QUEUE.CONFIG_JSON` |
| **Backend API** | ❌ No | Endpoint `GET /backtest/jobs/{id}` already returns `config_json` |
| **Frontend UI** | ✅ Yes | Add new button + dialog component |

### Why No Database Change?

The `config_json` field is **already stored** when a job is created:
- Saved in `BT.QUEUE` table as JSONB
- Retrieved via existing `SP_GET_QUEUE` procedure
- Returned by existing API endpoint

We're just **displaying existing data** in a new way — no new storage needed.

### Summary

```
┌─────────────┬─────────────┬─────────────┐
│  Database   │   Backend   │   Frontend  │
├─────────────┼─────────────┼─────────────┤
│   ❌ None   │   ❌ None   │  ✅ Changes │
└─────────────┴─────────────┴─────────────┘
```

---

## Before vs After

### Before (Current)

| Aspect | Current State |
|--------|---------------|
| **View Config** | ❌ Not possible without clicking "Clone" |
| **Config Access** | Only via Clone button (opens editable drawer) |
| **User Experience** | Must pretend to edit just to see settings |
| **Read-Only View** | ❌ Does not exist |
| **Quick Reference** | ❌ Cannot quickly check what config was used |

**Current Actions Column:**
```
COMPLETED jobs:  [View] [Clone] [Promote]
FAILED jobs:     [Re-run]
```

### After (With This Change)

| Aspect | New State |
|--------|-----------|
| **View Config** | ✅ Dedicated "Config" button |
| **Config Access** | Read-only dialog with formatted display |
| **User Experience** | One click to see all settings |
| **Read-Only View** | ✅ Clean dialog, no edit confusion |
| **Quick Reference** | ✅ Instantly see symbol, indicator, ranges |

**New Actions Column:**
```
COMPLETED jobs:  [View] [Config] [Clone] [Promote]
FAILED jobs:     [Config] [Re-run]
```

---

## Comparison Table

| Feature | Before | After |
|---------|--------|-------|
| View job config | ❌ | ✅ |
| Read-only mode | ❌ | ✅ |
| Copy JSON to clipboard | ❌ | ✅ |
| See factor details | Only via Clone | ✅ Dedicated view |
| See walk-forward settings | Only via Clone | ✅ Dedicated view |
| Available for failed jobs | ❌ | ✅ |
| Human-readable format | ❌ | ✅ |
| Raw JSON view | ❌ | ✅ |

---

## Problem

**Currently**, users cannot easily view what configuration was used for a backtest job:

1. The only way to see config is clicking **"Clone"** which:
   - Opens the config drawer in **edit mode**
   - Confuses users who just want to look
   - Requires extra clicks to close without saving

2. For **failed jobs**, users cannot see what config caused the failure

3. No way to **copy the config** for sharing or documentation

---

## Solution

Add a **Config** button that opens a **read-only dialog** showing:
- Human-readable summary of settings
- Collapsible factor details  
- Raw JSON view (expandable)
- Copy to clipboard button

---

## UI Design

### Button Placement (After)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Queue ID     │ Strategy        │ Status    │ Actions                     │
├──────────────┼─────────────────┼───────────┼─────────────────────────────┤
│ abc123...    │ BTC momentum    │ COMPLETED │ [View] [Config] [Clone] [+] │
│ def456...    │ ETH bollinger   │ FAILED    │ [Config] [Re-run]           │
│ ghi789...    │ AAPL rsi        │ RUNNING   │ [Cancel]                    │
│ jkl012...    │ SPY sma         │ QUEUED    │ [Cancel]                    │
└──────────────┴─────────────────┴───────────┴─────────────────────────────┘
```

### Config Dialog (New)

```
┌──────────────────────────────────────────────────────────┐
│  Strategy Configuration              [Strategy Name] [X] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  GENERAL SETTINGS                                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Symbol         btcusdt.crypto                      │  │
│  │ Data Source    yahoo                               │  │
│  │ Date Range     2016-01-01 → 2026-07-26             │  │
│  │ Asset Type     crypto                              │  │
│  │ Fee (bps)      10.0                                │  │
│  │ Walk-Forward   ✓ (50% train)                       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  FACTORS                                         [AND]   │
│  ┌────────────────────────────────────────────────────┐  │
│  │ ▼ Factor 1                  [bollinger_zscore]     │  │
│  │   Indicator      bollinger_zscore                  │  │
│  │   Strategy       momentum                          │  │
│  │   Data Column    price                             │  │
│  │   Window Range   5 → 100 (step 5)                  │  │
│  │   Signal Range   0.25 → 2.5 (step 0.25)            │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ▶ RAW JSON (click to expand)                            │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                        [📋 Copy JSON]         [Close]    │
└──────────────────────────────────────────────────────────┘
```

---

## Implementation

### Files to Create

| File | Description |
|------|-------------|
| `frontend/src/components/StrategyConfigDialog.tsx` | New reusable dialog component |

### Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/components/JobsTable.tsx` | Add Config button + dialog state |

---

## Button Visibility by Job Status

| Status | Before | After |
|--------|--------|-------|
| QUEUED | [Cancel] | [Cancel] |
| RUNNING | [Cancel] | [Cancel] |
| COMPLETED | [View] [Clone] [Promote] | [View] **[Config]** [Clone] [Promote] |
| FAILED | [Re-run] | **[Config]** [Re-run] |
| CANCELLED | [Re-run] | **[Config]** [Re-run] |

---

## Data Flow

```
User clicks "Config"
       │
       ▼
fetchJob(queue_id)  ──────►  GET /api/v1/backtest/jobs/{queue_id}
       │
       ▼
Returns JobDetail with config_json
       │
       ▼
Open StrategyConfigDialog with config_json
       │
       ▼
User views config (read-only)
       │
       ▼
User clicks "Close" or "Copy JSON"
```

---

## Technical Notes

### Existing API (No Changes Needed)

The `config_json` is already available via:
```typescript
// frontend/src/api/jobs.ts
async function getJob(queueId: string): Promise<JobDetail> {
  const { data } = await apiClient.get<JobDetail>(`/backtest/jobs/${queueId}`);
  return data;
}
```

### Config JSON Structure

```typescript
interface ConfigJson {
  symbol?: string;
  vendor_symbol?: string;
  data_source?: string;
  start?: string;
  end?: string;
  asset_type?: string;
  fee_bps?: number;
  conjunction?: string;
  factors?: FactorConfig[];
  walk_forward?: boolean;
  split_ratio?: number;
}

interface FactorConfig {
  indicator?: string;
  strategy?: string;
  data_column?: string;
  window_range?: { min: number; max: number; step: number };
  signal_range?: { min: number; max: number; step: number };
}
```

---

## Acceptance Criteria

- [ ] Config button appears for COMPLETED, FAILED, CANCELLED jobs
- [ ] Clicking Config opens a dialog with the strategy config
- [ ] General settings are displayed in readable format
- [ ] Factors are shown with collapsible cards
- [ ] Raw JSON is available (collapsed by default)
- [ ] Copy JSON button works
- [ ] Dialog is read-only (no edit functionality)
- [ ] Dialog closes properly

---

## Summary

| Before | After |
|--------|-------|
| No way to view config without editing | ✅ Dedicated read-only Config button |
| Can't see failed job configs easily | ✅ Config visible for all terminal states |
| No copy functionality | ✅ One-click copy JSON |
| Only raw data in database | ✅ Human-readable formatted view |

---

## Status

**Ready for implementation** ✅
