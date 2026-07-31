# Scheduler & trade execution — open questions

Design questions raised while building Phase 1.9 (scheduler + due deployments). Each section states the **problem**, **what a resolution would achieve**, and **current state** (DB vs app). No Python implementation is committed for the app-layer items below — DDL/procs may already exist.

---

## 1. Due check: elapsed time vs mixing “last batch” and “next batch”

**Question:** Why does `SP_GET_DUE_DEPLOYMENTS` (and its successors) combine last-run state with “who is due now” in one query? Isn’t that mixing last batch and next batch?

**Problem:** A single proc that joins `DEPLOYMENT`, anchor `EXECUTION_EVENT`, and `REFDATA.TM_INTERVAL.PERIOD_LENGTH` both **reads history** (last successful tick) and **decides eligibility** (interval elapsed). That felt wrong when adding intervals or cursors.

**What resolving it achieves:**

| Approach | Resolves |
|--------|----------|
| **Split read procs** — `SP_GET_MISSED_DUE_DEPLOYMENTS` (apply now) vs `SP_GET_NEXT_DUE_DEPLOYMENTS` (not yet due, UI preview) | Clear separation: poller only calls missed-due; UI/ops optionally calls next-due. No OR in one result set. |
| **Keep one proc, two cursors** | Same semantics, one round-trip — harder for Python `_call_get` (single cursor today). |
| **Materialize `NEXT_DUE_AT` on anchor row at write time** | Due read becomes `NEXT_DUE_AT <= NOW()` without joining interval at poll time — rejected so far (no new column). |

**Current state (DB):**

- `TRADE.DEPLOYMENT_SCHEDULE_STATUS` — append-only scheduler state (`SCHEDULED_TS` = next due; release `1.4.0`).
- `SP_GET_MISSED_DUE_DEPLOYMENTS` — `IN_TM_INTERVAL_ID`; enabled, not paused; returns `NEXT_SCHEDULED_TS`.
- `SP_GET_NEXT_DUE_DEPLOYMENTS` — `PENDING` and `SCHEDULED_TS > NOW()`.
- Advance = `SP_INS_DEPLOYMENT_SCHEDULE_STATUS` after apply (no batch advance proc) — see §9.
- The combined `SP_GET_DUE_DEPLOYMENTS` and the `EXECUTION_EVENT.IS_LAST_RUN_IND` anchor were both dropped while this design was still unreleased, so neither ships in `1.4.0`.

**Still open (app):** Poller GET per interval + SP_INS advance after apply; apply-time due gate (not wired).

---

## 2. `TRANSACT_AT` vs `CREATED_AT` on `EXECUTION_EVENT`

**Question:** Using `CREATED_AT` for scheduler anchor is risky — audit insert time could diverge from tick time.

**Resolution (1.4.0):** Scheduler moved to `TRADE.DEPLOYMENT_SCHEDULE_STATUS` (`SCHEDULED_TS`). `EXECUTION_EVENT.TRANSACT_AT` remains diary-only tick time. `CREATED_AT` on all tables stays audit-only — never exposed in API responses.

**Current state:** `SP_INS_EXECUTION_EVENT` accepts `IN_TRANSACT_AT` and `TradeRepo.sp_ins_execution_event` always sends one — the column is `NOT NULL` with no default. `LiveApplyOrchestrator` stamps the tick once per apply cycle and reuses it for every retry attempt, so the diary groups by tick rather than by insert time; the repo's now-UTC default only covers callers outside a cycle.

---

## 3. `SCHEDULE_TM_INTERVAL_ID` and REFDATA intervals

**Question:** Hardcoded `CASE` on interval id/name in the due proc cannot scale when adding intervals.

**Problem:** Every new interval (e.g. 4H) would require a proc change.

**What resolving it achieves:**

- **`REFDATA.TM_INTERVAL.PERIOD_LENGTH`** drives due arithmetic (`last + PERIOD_LENGTH`).
- New interval = one REFDATA seed row only.
- Backfill **`SCHEDULE_TM_INTERVAL_ID = 1` (DAILY)** on existing open deployments (release `1.4.0`) so scheduler has a cadence without NULL = manual ambiguity.

**Still open:** Whether `SCHEDULE_TM_INTERVAL_ID IS NOT NULL` filter stays in due procs — removed per discussion; JOIN to `TM_INTERVAL` implicitly excludes NULL schedule.

---

## 4. Double apply (poller + EventBridge, or overlapping polls)

**Question:** Once due, a deployment stays due until success — won’t poller / Lambda double-apply?

**Problem:** `SP_GET_MISSED_DUE_DEPLOYMENTS` is a **candidate list**, not a lock. A long-running apply can overlap the next poll.

**What resolving it achieves:**

| Layer | Resolves |
|-------|----------|
| **Apply-time due gate** | Scheduled `/apply` re-checks same rule; no-op if not due (handles EventBridge firing early). |
| **In-flight lease** | Claim deployment at apply start (DB row or advisory lock); second caller skips. |
| **Batch schedule advance after poll pass** | Poller applies all due rows, then one batch write bumps every `SCHEDULED_TS` — see §9. |

**Current state:** Neither gate nor lease implemented in Python.

---

## 5. Stuck deployment (bad config, permanent broker error)

**Question:** If deployment config is wrong, apply fails forever — what stops the retry loop?

**Problem:** Order failures used to block schedule advance (when anchor lived on `EXECUTION_EVENT`). With `DEPLOYMENT_SCHEDULE_STATUS`, advance policy is separate — see §9.

**Retry policy (app — pending):** Same `SCHEDULED_TS`, retry up to **3 times** when apply completes but fails (order rejected, broker error). Pre-completion aborts (missing strategy, bars, credentials) stay due without consuming the retry budget and without advance. After 3 failures: `SP_INS_DEPLOYMENT_SCHEDULE_STATUS` with `NEXT_SCHEDULED_TS` from GET cursor; leave `IS_ENABLED_IND` unchanged and wait for the next interval. Failures are diary-only in `EXECUTION_EVENT`; optional `FAILED` schedule status for history via `SP_INS`.

**What auto-pause would resolve:**

- After **permanent** broker failure or **exhausted retries**, set `IS_ENABLED_IND='N'` and `DEPLOYMENT_STATUS='PAUSED'`.
- Removes deployment from missed-due proc (`IS_ENABLED_IND='Y'` filter).
- Ops fixes config, dry-runs, re-enables manually.

**Current state:** Manual **Stop** or kill switch only. Auto-pause **not** in Python (reverted).

---

## 6. Pause button should flatten open positions

**Question:** UI “pause” only toggles kill switch — it should close positions for that deployment.

**Problem:** Disable/stop today are **DB-only** — no broker flatten. Exposure remains on the exchange.

**What resolving it achieves:**

- **`POST /deployments/{id}/pause`** (or equivalent): run apply with **`signal=0`** (existing `intended_side` → SELL / CLOSE_SHORT on full broker qty), then `PAUSED` + disabled.
- UI pause icon calls flatten+pause, not bare `PATCH enabled=false`.
- **Stop** vs **pause:** stop = disable without flatten (or optionally flatten too — product decision).

**Caveat:** Flatten uses **account-level** broker position on that symbol, not a per-deployment slice (see §7).

**Current state:** UI pause = kill switch only. Flatten-on-pause **not** implemented (reverted).

---

## 7. Two deployments, same asset — how to detect position?

**Question:** If two deployment strategies trade one asset (same credential + product), how should position be detected at retrieve time?

**Problem:** Two different notions of “position”:

| Source | Meaning |
|--------|---------|
| **`compute_latest_position`** | Strategy target from bars + config (−1/0/+1) — not broker state. |
| **`adapter.get_position_qty(symbol)`** | **Account-level** exchange position for that symbol. |
| **`TRADE.TRANSACTION`** | Per-`DEPLOYMENT_ID` fill audit — **not read** for live position today. |

Two enabled deployments on the same `(api_credential_id, internal_cusip, paper/live)` would **share one broker position** and can **fight** each other (one applies BUY, other sees long and HOLDs).

**What resolving it achieves:**

| Approach | Resolves |
|----------|----------|
| **One enabled deployment per slot** — reject create/enable when another enabled row shares credential + cusip + paper | Prevents the conflict class at source. |
| **Deployment-attributed qty** — derive net from `TRANSACTION` per deployment | Theoretical attribution; breaks if manual trades or sibling deployment on same account. |
| **Separate credentials per deployment** | Operational isolation — same product, different sub-accounts. |

**Recommendation documented:** Enforce **one active slot per `(api_credential_id, internal_cusip, is_paper_ind)`** at create/enable; live apply continues to use **broker `get_position_qty`** at tick time (full account exposure on symbol).

**Current state:** No duplicate guard in Python (reverted). Broker read path unchanged.

---

## 8. Do we need `SP_GET_NEXT_DUE_DEPLOYMENTS`?

**Question:** Is a second proc/cursor for “next due” needed, or can UI compute it?

**Problem:** Extra proc + dual-cursor drain in Python for display-only data.

**What resolving it achieves:**

- **Poller:** missed-due proc only.
- **UI:** `SP_GET_DEPLOYMENT` already exposes `LAST_RUN_AT`; API computes `next_due = last_run_at + period` from Redis REFDATA — no second proc.
- **Ops dashboard** batch “coming up in N hours” might still justify `SP_GET_NEXT_DUE_DEPLOYMENTS`.

**Current state:** Proc exists for optional use; not required for Phase 1.9 poller. `LAST_RUN_AT` in that proc was removed — `NEXT_DUE_AT` (= `SCHEDULED_TS`) is sufficient.

---

## 9. Schedule advance — GET + SP_INS

**Question:** How should the poller bump `SCHEDULED_TS` after a tick?

**Resolved:** No batch advance proc. Per interval tick:

1. `SP_GET_MISSED_DUE_DEPLOYMENTS(IN_TM_INTERVAL_ID)` — enabled, not `PAUSED`/`STOPPED`, current `PENDING` due row; cursor includes `NEXT_SCHEDULED_TS`.
2. Apply each row (retry up to 3× on failure — app counter, same `SCHEDULED_TS`).
3. On interval close (success or retries exhausted): `SP_INS_DEPLOYMENT_SCHEDULE_STATUS(deployment_id, deployment_id, vid, 'PENDING', next_scheduled_ts, user_id)`.

Pre-completion aborts do not call SP_INS — row stays due.

**Current state:** `SP_ADVANCE_DEPLOYMENT_SCHEDULE` was dropped before it ever shipped, so it is absent from release `1.4.0`. `TradeRepo` now exposes `sp_get_missed_due_deployments`, `sp_get_next_due_deployments`, and `sp_ins_deployment_schedule_status`, so the three calls above are available; the poller that sequences them is **not** written yet.


---

## Summary — implemented vs pending

| Item | DB / procs | Python / UI |
|------|------------|-------------|
| `PERIOD_LENGTH` in REFDATA | Done | — |
| `TRANSACT_AT` on `EXECUTION_EVENT` (diary) | Done | Done — one apply-cycle tick time shared by every attempt |
| `DEPLOYMENT_SCHEDULE_STATUS` + GET/SP_INS advance | Done | Repo done; poller wiring (pending) |
| Missed / next due split procs | Done | Repo done; poller wiring (pending) |
| `SCHEDULE_TM_INTERVAL_ID` on create / update | Done | Repo + service + API done; UI (pending) |
| Schedule backfill DAILY | Done | — |
| Apply-time due gate | — | Pending |
| In-flight lease | — | Pending |
| Auto-pause on failure | — | Pending |
| Pause = flatten + disable | — | Pending |
| One deployment per credential+product slot | — | Pending |
| `ScheduleTrigger` / EventBridge sync | — | Pending |

See also: [Scheduler & Price Bars](scheduler-price-bars.md).
