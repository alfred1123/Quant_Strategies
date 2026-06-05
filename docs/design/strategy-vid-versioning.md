# Strategy VID Versioning by Name

How to make repeated submissions of the **same strategy** increment
`STRATEGY_VID` instead of spawning a brand-new `STRATEGY_ID` at `VID=1` each
time, add a uniqueness guarantee, and clean up the duplicated rows already in
`BT.STRATEGY`.

## Symptom

Submitting the same configuration twice produces **two separate strategy cards**,
each showing `v1` / `Best`, instead of one card with `v1`, `v2`:

```
btcusdt.crypto · get_bollinger_band/momentum    v1  Best   (19:03:32)
btcusdt.crypto · get_bollinger_band/momentum    v1  Best   (19:03:46)
```

## Root cause

Identity is keyed on a **random** `STRATEGY_ID`, not on the strategy name.

- [`quant/api/services/jobs.py`](https://github.com/alfred1123/Quant_Strategies/blob/main/quant/api/services/jobs.py)
  mints `strategy_id = uuid.uuid4()` on **every** `enqueue()`.
- [`BT.SP_INS_STRATEGY`](https://github.com/alfred1123/Quant_Strategies/blob/main/db/liquidbase/bt/procedures/SP_INS_STRATEGY.sql)
  computes the next VID as
  `SELECT COALESCE(MAX(STRATEGY_VID),0)+1 WHERE STRATEGY_ID = IN_STRATEGY_ID`.

Because the incoming `STRATEGY_ID` is always new, the `MAX(VID)` lookup always
finds nothing and returns `VID=1`. The name (`STRATEGY_NM`) never participates in
version resolution.

## Target behaviour

- Same logical strategy (same **owner + name**) → **one** `STRATEGY_ID`, with
  `STRATEGY_VID` incrementing `1, 2, 3, …` on each resubmission.
- A uniqueness guarantee so duplicate `(name, vid)` rows cannot be created again.
- Existing duplicated rows collapsed into the correct version history.

!!! note "Scoping: per-user, not global"
    Strategies are owned (`BT.STRATEGY.USER_ID`, see
    [User isolation](user-isolation.md)). Two different users may legitimately
    pick the same `STRATEGY_NM`. A **global** `UNIQUE (STRATEGY_NM, VID)` would
    block user B from ever using a name user A already used. Scope identity and
    the unique key to **`(USER_ID, STRATEGY_NM, …)`**. The rest of this doc uses
    that scoping; drop `USER_ID` from the constraint only if names are meant to
    be globally unique.

## How to do it

There are two ways to bind identity to the name. **Design A is recommended.**

### Design A — Resolve `STRATEGY_ID` from the name inside the SP (recommended)

The procedure looks up an existing `STRATEGY_ID` for `(USER_ID, STRATEGY_NM)`;
if found it reuses that ID and increments the VID, otherwise it allocates a new
`STRATEGY_ID` at `VID=1`. Python stops generating an ID per enqueue.

**1. SP change** — `BT.SP_INS_STRATEGY` (new `db/liquidbase/bt/releases/*.xml`
changeset, `CREATE OR REPLACE PROCEDURE`):

```sql
-- Step 05: Resolve the logical strategy id from (USER_ID, STRATEGY_NM).
SELECT STRATEGY_ID
  INTO V_STRATEGY_ID
  FROM BT.STRATEGY
 WHERE USER_ID     = IN_USER_ID
   AND STRATEGY_NM = IN_STRATEGY_NM
 ORDER BY STRATEGY_VID DESC
 LIMIT 1;

IF V_STRATEGY_ID IS NULL THEN
    V_STRATEGY_ID := COALESCE(IN_STRATEGY_ID, gen_random_uuid());
END IF;

-- Step 10: Next VID for THIS logical strategy.
SELECT COALESCE(MAX(STRATEGY_VID), 0) + 1
  INTO V_VID
  FROM BT.STRATEGY
 WHERE STRATEGY_ID = V_STRATEGY_ID;
```

The existing Steps 20–30 (close prior active row, insert new active row) stay as
is but use `V_STRATEGY_ID`. Add an `OUT_STRATEGY_ID UUID` parameter so the caller
learns the resolved id (it is no longer the value it passed in).

**2. Python change** —
[`quant/api/services/jobs.py`](https://github.com/alfred1123/Quant_Strategies/blob/main/quant/api/services/jobs.py)
and the wrapper in
[`quant/queue/repo.py`](https://github.com/alfred1123/Quant_Strategies/blob/main/quant/queue/repo.py):
stop minting `strategy_id` per call; pass `NULL` and read back the resolved
`OUT_STRATEGY_ID` + `OUT_STRATEGY_VID`, then enqueue against that pair.

```python
# jobs.py — before
strategy_id = uuid.uuid4()
strategy_vid = self._repo.sp_ins_strategy(strategy_id=strategy_id, ...)

# after
strategy_id, strategy_vid = self._repo.sp_ins_strategy(
    strategy_nm=req.strategy_nm, config_json=req.config_json, user_id=user_id,
)
```

### Design B — Deterministic `STRATEGY_ID` from the name (alternative)

Keep the SP unchanged; make the **id deterministic** in Python so the existing
"existing id ⇒ increment" path fires:

```python
strategy_id = uuid.uuid5(STRATEGY_NS, f"{user_id}|{req.strategy_nm}")
```

Simpler (no SP change) but couples the id to the name permanently — renaming a
strategy creates a new lineage, and you cannot change the name of an existing
lineage. Prefer Design A unless renames are guaranteed never to happen.

## Add the uniqueness guarantee

Once the insert path is fixed, enforce it at the schema level. New
`db/liquidbase/bt/releases/*.xml` changeset:

```sql
ALTER TABLE BT.STRATEGY
    ADD CONSTRAINT UQ_STRATEGY_NM_VID
    UNIQUE (USER_ID, STRATEGY_NM, STRATEGY_VID);
```

!!! warning "Clean up data first"
    This `ALTER` **fails** while duplicate `(USER_ID, STRATEGY_NM, VID)` rows
    still exist. Run the cleanup below **before** adding the constraint.

## Clean up existing data

Today the same name maps to many `STRATEGY_ID`s, each at `VID=1`. Collapse each
`(USER_ID, STRATEGY_NM)` group into a **single** `STRATEGY_ID` with VIDs
renumbered by `CREATED_AT`. Do this as a **one-off deploy-time Liquibase
changeset** (the sanctioned place for direct DML — see `AGENTS.md`).

Approach:

1. **Pick a survivor id** per `(USER_ID, STRATEGY_NM)` — the earliest
   `CREATED_AT` row's `STRATEGY_ID`.
2. **Renumber** all rows in the group onto that survivor id, assigning
   `STRATEGY_VID` by `ROW_NUMBER() OVER (PARTITION BY USER_ID, STRATEGY_NM
   ORDER BY CREATED_AT)`.
3. **Repoint children** that reference `(STRATEGY_ID, STRATEGY_VID)` —
   `BT.QUEUE`, `BT.RESULT`, `BT.PROMOTION`, `TRADE.DEPLOYMENT` — to the new
   `(survivor_id, new_vid)`. **Inventory every FK first**; a missed child
   orphans rows.
4. **Fix `TRANSACT_TO_TS`** so only the highest VID per group stays active
   (`9999-12-31`); older VIDs get a closed timestamp.
5. **Fix `IS_BEST_IND`** so exactly one row per group is `'Y'` (keep the
   currently-best config, or default to the latest VID).
6. **Add the unique constraint** (previous section) in the **same** changelog,
   after the data fix, so the migration is atomic.

```sql
-- Sketch (run inside a transaction; validate counts before/after).
WITH ranked AS (
    SELECT ctid,
           FIRST_VALUE(STRATEGY_ID) OVER w  AS survivor_id,
           ROW_NUMBER()             OVER w  AS new_vid
      FROM BT.STRATEGY
    WINDOW w AS (PARTITION BY USER_ID, STRATEGY_NM ORDER BY CREATED_AT)
)
UPDATE BT.STRATEGY s
   SET STRATEGY_ID  = r.survivor_id,
       STRATEGY_VID = r.new_vid
  FROM ranked r
 WHERE s.ctid = r.ctid;
-- then: repoint BT.QUEUE / BT.RESULT / BT.PROMOTION / TRADE.DEPLOYMENT,
--       reset TRANSACT_TO_TS + IS_BEST_IND, then ADD CONSTRAINT.
```

!!! danger "Back up before migrating"
    Take a dump first (see [Database Dump & Restore](../guides/database-dump-restore.md)).
    Renumbering a PK that other tables reference is irreversible without a
    restore. Validate row counts and FK integrity in a staging copy before prod.

## Rollout order

1. **Back up** the database.
2. Deploy the **cleanup + unique-constraint** changelog (data fixed, duplicates
   gone, constraint live).
3. Deploy the **`SP_INS_STRATEGY`** change (Design A) — new submissions now
   increment VID.
4. Deploy the **Python** change so the API/worker read back the resolved
   `STRATEGY_ID` / `STRATEGY_VID`.
5. Update unit + integration tests
   ([`tests/unit/`](https://github.com/alfred1123/Quant_Strategies/tree/main/tests/unit),
   [`tests/integration/`](https://github.com/alfred1123/Quant_Strategies/tree/main/tests/integration))
   to assert a second submission of the same name returns `VID=2`.
6. Verify in the UI: resubmitting the same strategy now shows `v1`, `v2` under
   **one** card.

## Related

- [`BT.STRATEGY` table](https://github.com/alfred1123/Quant_Strategies/blob/main/db/liquidbase/bt/tables/STRATEGY.sql)
- [`BT.SP_INS_STRATEGY`](https://github.com/alfred1123/Quant_Strategies/blob/main/db/liquidbase/bt/procedures/SP_INS_STRATEGY.sql)
- [Best-VID Promotion](best-vid-promotion.md) — `IS_BEST_IND` semantics
- [User isolation](user-isolation.md) — why scoping is per-`USER_ID`

---

# UI: display strategies by name & owner

Once a strategy's identity is the `(USER_ID, STRATEGY_NM)` pair (above), the
Jobs and Promotion views should present strategies by **name + owner**, not by
opaque UUIDs. Users do not care about `QUEUE_ID` / `STRATEGY_ID`.

## Jobs table ("My Jobs")

[`frontend/src/components/JobsTable.tsx`](https://github.com/alfred1123/Quant_Strategies/blob/main/frontend/src/components/JobsTable.tsx)

- **Drop the `Queue ID` column.** Lead with **Strategy** (`strategy_nm`) and an
  **Owner** column (`user_id`). Keep `VID` (with the `Best` chip), `Status`,
  `Priority`, `Submitted`, `Error`.
- `queue_id` is still needed internally for row actions (Cancel / Re-run / View /
  Clone / Promote) and `getRowId` — keep it in the row **data**, just not as a
  visible column.

!!! note "Jobs is shared at the data layer — scoping is API-only"
    The queue is **already shareable**: `BT.SP_GET_QUEUE`'s `IN_USER_ID` is an
    **optional** filter (`IF IN_USER_ID IS NOT NULL THEN ... AND q.USER_ID =
    ...`). Passing `NULL` returns **every user's** rows — no SP change needed.
    The only thing scoping Jobs to one user today is the **API layer**:
    [`quant/api/routers/jobs.py`](https://github.com/alfred1123/Quant_Strategies/blob/main/quant/api/routers/jobs.py)
    calls `svc.list_for_user(user.app_user_id)`, and
    [`BtQueueRepo.list_for_user`](https://github.com/alfred1123/Quant_Strategies/blob/main/quant/queue/repo.py)
    always passes `user_id`.

### Make Jobs shared (like Promotion)

To show **all users'** jobs with a "Mine / All" toggle — the intended design:

1. **Repo** — add a global list path, e.g.
   `list_all(limit)` → `sp_get_queue(user_id=None, limit=...)`, or give
   `list_for_user` an optional `user_id=None` meaning "all".
2. **Service** —
   [`JobsService.list_for_user`](https://github.com/alfred1123/Quant_Strategies/blob/main/quant/api/services/jobs.py)
   gains a sibling that does not scope by user.
3. **Router** — `GET /backtest/jobs` accepts `?scope=all|mine` (default per the
   shared-strategy product decision); `mine` passes the caller's
   `app_user_id`, `all` passes `NULL`. Keep **ownership enforcement** on
   mutations (cancel / re-run) via `get_active(..., user_id=...)` — sharing is
   read-only visibility, not write access.
4. **Frontend** — `JobsTable` adds the **Mine / All** toggle and the **Owner**
   column (same pattern as Promotion §3 below).

!!! warning "Mutation guard stays user-scoped"
    Making the **list** global must not make **actions** global. Cancel,
    re-run, and clone already resolve rows through `get_active(queue_id,
    user_id=...)`; keep that ownership check so a shared (visible) job cannot be
    cancelled by a non-owner. Visible ≠ editable (see
    [User isolation](user-isolation.md)).

## Promotion view

[`frontend/src/components/PromotionTab.tsx`](https://github.com/alfred1123/Quant_Strategies/blob/main/frontend/src/components/PromotionTab.tsx)

The Promotion log is **global** today (`PromotionRepo.get_log(strategy_id=None)`
returns every user's decisions), and the UI already groups decisions into
collapsible blocks. Required changes:

### 1. Group by `(user_id, strategy_nm)`, not `strategy_id`

`StrategyList` currently groups by `strategy_id`. After the VID fix one
`strategy_id` == one logical strategy, so grouping by `strategy_id` becomes
correct — but key the **block header** off `strategy_nm` + `user_id` so the
label is human-readable and two users with the same name stay distinct:

```
btcusdt.crypto · get_bollinger_band/momentum   ·  alice          5 decisions  ▸
```

Show the owner (`user_id`) in the block header next to the name.

### 2. Collapse all blocks by default

Change the `Accordion` from `defaultExpanded` to **collapsed by default** so a
long shared list is scannable. Optionally auto-expand only the block containing
the **Recommended** row.

### 3. "Mine / All" filter

Add a toggle (default **All**, per the product decision that strategies are
shared) that filters groups to `user_id === me` using
[`useMe()`](https://github.com/alfred1123/Quant_Strategies/blob/main/frontend/src/api/auth.ts).
This is display-only; **editing** rights are a separate question (a shared
strategy being *visible* to everyone does not imply everyone may edit it — see
[User isolation](user-isolation.md)).

### 4. Per-block VID preview + full history

Each collapsed block previews a short VID list; expanding reveals the rest.

**Recommendation:** preview the **latest 5 VIDs by `created_at` desc**, but
**always pin the `IS_BEST_IND='Y'` row** even if it falls outside the latest 5
(the current best is the most decision-relevant row and must never be hidden).
If a block has ≤ 5 VIDs, show them all and omit the expander.

```
get_bollinger_band/momentum · alice                     ▸ (collapsed)
  ── expand ──
  VID   Outcome   Sharpe   Calmar   When
  v7 ★  Kept      1.21     1.40     2026/06/04 19:03      ← Best, pinned
  v6    Demoted   1.18     1.31     2026/06/03 …
  v5    Kept      1.20     1.35     2026/06/02 …
  v4    Kept      1.15     1.28     2026/06/01 …
  v3    Kept      1.10     1.22     2026/05/30 …
  [ Show all 7 versions ]                               ← expander
```

Implementation notes:
- Sort each group's decisions `created_at` desc, take the first 5, then union
  the pinned best row (dedupe by `promotion_id`), preserving VID-desc order.
- The expander toggles between the preview slice and the full `decisions` array
  (already available in the group) — no extra API call.
- Keep row-click → `ComparisonPanel` behaviour unchanged.

## Out of scope

- **Edit permissions** for shared strategies (who may re-run / rename / cancel
  another user's strategy) — separate decision. Both Jobs and Promotion sharing
  here are **read-only visibility**; mutations stay owner-scoped via
  `get_active(..., user_id=...)`.
