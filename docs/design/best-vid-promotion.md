# Best-VID Promotion Model

## Current Problem

`SP_INS_STRATEGY` always makes the newest VID active (`TRANSACT_TO_TS = 9999-12-31`) and closes the previous one — even if the new VID performs worse. There is no way to distinguish "latest version" from "best version".

## Design — `IS_BEST_IND` column

Separate two concerns:
- **`TRANSACT_TO_TS`** = temporal versioning (which version is the latest/current) — unchanged
- **`IS_BEST_IND`** = quality flag (which version performed best) — new column

```mermaid
flowchart TD
    subgraph insert [Strategy Insert]
        A["SP_INS_STRATEGY"] --> B{First VID?}
        B -->|Yes| C["IS_BEST_IND = 'Y'\nNo baseline to compare"]
        B -->|No| D["IS_BEST_IND = 'N'\nAwaits backtest result"]
    end
    subgraph promote [After Backtest]
        E["Worker completes backtest"] --> F{"Current best\nhas a RESULT?"}
        F -->|No| G["Set IS_BEST_IND = 'Y'"]
        F -->|Yes| H{"New metric\nbetter?"}
        H -->|Yes| G
        H -->|No| I["Keep current best\nLog decision"]
        G --> J["SP_PROMOTE_STRATEGY\nFlip IS_BEST_IND"]
    end
    subgraph manual [Manual Override]
        K["POST /strategies/{id}/promote"] --> J
    end
```

### Key semantics

- `TRANSACT_TO_TS = 9999-12-31` = **latest version** (temporal, unchanged behavior)
- `IS_BEST_IND = 'Y'` = **best-performing version** (exactly one per `STRATEGY_ID`)
- VID 1 is always best by default (no baseline)
- VID 2+ starts as `IS_BEST_IND = 'N'` — promoted only after beating the current best
- Comparison only ever compares the new VID vs the one row with `IS_BEST_IND = 'Y'`

## 1. Database Changes

### 1a. Add column to `BT.STRATEGY`

```sql
IS_BEST_IND  CHAR(1) NOT NULL DEFAULT 'N'
```

Backfill: set `IS_BEST_IND = 'Y'` for every row where `TRANSACT_TO_TS = 9999-12-31` (current active row = presumed best since no comparison data exists yet).

### 1b. Modify `SP_INS_STRATEGY`

Insert column added. No change to the `TRANSACT_TO_TS` close-and-insert logic.

- **VID 1**: `IS_BEST_IND = 'Y'`
- **VID 2+**: `IS_BEST_IND = 'N'`

### 1c. New `SP_PROMOTE_STRATEGY`

Signature:
```
IN  IN_STRATEGY_ID   UUID
IN  IN_STRATEGY_VID  INTEGER   -- the VID to promote
IN  IN_USER_ID       TEXT      -- audit
OUT status triplet
```

Logic:
1. Verify target VID exists and is not already best
2. `UPDATE BT.STRATEGY SET IS_BEST_IND = 'N' WHERE STRATEGY_ID = IN_STRATEGY_ID AND IS_BEST_IND = 'Y'`
3. `UPDATE BT.STRATEGY SET IS_BEST_IND = 'Y' WHERE STRATEGY_ID = IN_STRATEGY_ID AND STRATEGY_VID = IN_STRATEGY_VID`

### 1d. Update `SP_GET_STRATEGY`

Add `IS_BEST_IND` to all cursor SELECT lists so the cache and callers can see it.

### 1e. Liquibase changeset `1.6.0-promote-strategy.xml`

- changeSet 001: `ALTER TABLE BT.STRATEGY ADD COLUMN IS_BEST_IND` + backfill
- changeSet 002: `SP_INS_STRATEGY` (add IS_BEST_IND to INSERT)
- changeSet 003: `SP_PROMOTE_STRATEGY` (new)
- changeSet 004: `SP_GET_STRATEGY` (add IS_BEST_IND to cursors)

## 2. Promotion Metric Configuration

### Where to store the promotion policy

Add an optional `promotion` block to `CONFIG_JSON` in the strategy:

```json
{
  "indicators": [...],
  "promotion": {
    "metric": "Sharpe Ratio",
    "direction": "higher_is_better"
  }
}
```

- **Default** (when `promotion` key absent): `Sharpe Ratio`, `higher_is_better`
- Supported metrics: `Sharpe Ratio`, `Calmar Ratio`, `Total Return`, `Max Drawdown` (lower is better), `Annualized Return`
- These keys match `performance.strategy_metrics` in `PAYLOAD_JSON`

### Add a REFDATA.PROMOTION_METRIC table

Dropdown values for the UI:

| DISPLAY_NAME | METRIC_KEY | DIRECTION |
|---|---|---|
| Sharpe Ratio | Sharpe Ratio | higher_is_better |
| Calmar Ratio | Calmar Ratio | higher_is_better |
| Total Return | Total Return | higher_is_better |
| Max Drawdown | Max Drawdown | lower_is_better |

## 3. Python — Auto-Promote in Worker

### 3a. Promotion helper (`quant/queue/promote.py` — new)

```python
def should_promote(
    new_result: dict,
    best_result: dict | None,
    metric: str = "Sharpe Ratio",
    direction: str = "higher_is_better",
) -> bool:
```

- Extracts `performance.strategy_metrics[metric]` from both `PAYLOAD_JSON` blobs
- `best_result is None` → always promote (no baseline to beat)
- Handles NaN / missing gracefully (don't promote if new metric is NaN)

### 3b. Worker completion (`quant/queue/worker.py`)

After writing `BT.RESULT` and before marking COMPLETED:

1. Read promotion config from `CONFIG_JSON.promotion` (default Sharpe)
2. Find current best VID for this `strategy_id` — the row with `IS_BEST_IND = 'Y'` (from `StrategyCatalogCache`)
3. If best VID has a `BT.RESULT` → fetch its `PAYLOAD_JSON`
4. Call `should_promote()` comparing new vs best
5. If promote → `CALL BT.SP_PROMOTE_STRATEGY(strategy_id, new_vid, user_id)`
6. Refresh `StrategyCatalogCache`
7. Log the decision either way

### 3c. `BtQueueRepo` wrapper

Add `sp_promote_strategy(strategy_id, strategy_vid, user_id)` to `quant/queue/repo.py`.

Add a lookup to fetch a RESULT by `(strategy_id, strategy_vid)` — joins QUEUE → RESULT.

### 3d. `StrategyCatalogCache` updates (`quant/data/strategy_catalog.py`)

Add `get_best_for_strategy(strategy_id) -> dict | None` — returns the row where `IS_BEST_IND = 'Y'` for a given `strategy_id`.

## 4. Manual Promote API

### 4a. New endpoint in `quant/api/routers/jobs.py`

```
POST /api/v1/backtest/strategies/{strategy_id}/promote
Body: { "strategy_vid": 3 }
```

- Validates user owns the strategy (via `get_for_user`)
- Calls `SP_PROMOTE_STRATEGY`
- Refreshes cache
- Returns new active VID

## 5. Shared Strategy Pool

Currently list mode requires `IN_USER_ID` and scopes to that user's rows. For the shared pool:
- When `IN_USER_ID` is supplied → returns that user's active strategies (current behavior, for "my strategies")
- Add a new mode or endpoint for "all active strategies" (shared pool browser)

Separate concern — defer to a follow-up.

## Open Questions

- **Re-versioning flow**: The current enqueue endpoint always generates a fresh `strategy_id` (VID is always 1). To create VID 2+ under an existing strategy, `EnqueueRequest` needs an optional `strategy_id` field.
- **Calmar / Max Drawdown correctness**: Calmar ratio and max drawdown calculations may be incorrect — fix before wiring into promotion decisions.
