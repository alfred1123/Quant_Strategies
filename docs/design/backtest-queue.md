# Design: Queued Background Backtests

**Status:** Draft — not yet implemented. Direction (Postgres-backed FIFO + LISTEN/NOTIFY) ratified in [decision #26](../decisions.md).
**Date:** 2026-04-25
**Scope:** `api/`, `frontend/`, `db/liquidbase/bt/`

## 1. Problem

Large backtests and parameter optimizations are CPU-heavy. A run with 20,000 iterations can take long enough that the current single-run UI becomes limiting:

1. The user can only focus on one optimization at a time.
2. There is no persistent queue of pending jobs.
3. There is no backend-managed notion of `queued`, `running`, `completed`, `failed`, or `cancelled`.
4. The UI cannot safely continue editing, adding, or removing queued strategies while one run is in progress.

There is also an implementation constraint:

1. Python threads do not provide useful CPU parallelism for heavy pure-Python or mixed pandas/numpy workloads because of the GIL.
2. A thread is still useful for request detachment or I/O orchestration, but not as the main scaling primitive for many large concurrent backtests.

## 2. Goals

### Functional goals

1. The backend accepts multiple backtest jobs and runs them one at a time in queue order.
2. The UI shows a queue table on the right side with `queued`, `running`, `completed`, `failed`, and `cancelled` jobs.
3. The running job shows progress as iterations completed vs total iterations remaining.
4. The user can add more jobs while another job is running.
5. The user can remove queued jobs while another job is running.
6. The running job automatically advances to the next queued job when complete.
7. Completed jobs retain summary and result references.

### UX goals

1. Editing the current strategy config must remain independent from submitted jobs.
2. The queue must update live without requiring manual refresh.
3. The user must be able to inspect the currently running job and completed jobs separately from the editable draft form.

### Technical goals

1. Use process-based execution for CPU-bound optimization work.
2. Persist queue state in PostgreSQL so jobs survive API restarts.
3. Reuse existing backtest pipeline and existing BT persistence procedures where possible.
4. Preserve the existing SSE model where practical.

## 3. Non-Goals

1. Running many backtests concurrently in the first version.
2. Distributed scheduling across many worker hosts.
3. Replacing the current optimization logic.
4. Introducing Celery, Redis, or external queue infrastructure in the first version.

## 4. Constraints and Observations

### Current backend

The current backend already supports per-trial progress streaming for a single optimization request through SSE and a worker thread. That is sufficient for interactive single-run feedback, but it is not a durable queue.

### Current frontend

The current page holds a single editable config and a single optimization result in local component state. This is good for interactive exploration, but it conflates:

1. draft config being edited now
2. submitted job waiting in queue
3. running job state
4. completed result history

### Concurrency model

Because heavy optimization is CPU-bound, the worker that executes jobs should use a separate process, not only a Python thread. The API process can still use threads or asyncio for coordination, SSE fanout, and DB polling.

## 5. Proposed Architecture

## 5.1 High-level model

Introduce three backend roles inside the same deployment unit:

1. API server
Accepts job submissions, queue mutations, queue queries, and job event streams.

2. Queue coordinator
Runs inside FastAPI lifespan. Polls the DB for due work, assigns the next queued job when no job is running, and maintains in-memory subscriber lists for SSE clients.

3. Backtest worker process
Executes exactly one backtest job at a time in a separate Python process. Reports progress back to the coordinator.

Version 1 keeps a single worker slot.

## 5.2 Why a single worker first

The requested behavior is explicitly serial:

1. one strategy backtest runs
2. when it completes, the next queued job starts

That matches a single-process worker model and avoids resource contention, duplicate data fetches, and multi-job CPU starvation.

## 5.3 Why process-based execution

1. It avoids GIL contention for CPU-heavy backtest loops.
2. It prevents a long optimization from blocking the API event loop.
3. It provides a cleaner failure boundary than running heavy work directly in the API process.

Recommended primitive:

1. `concurrent.futures.ProcessPoolExecutor(max_workers=1)` for initial implementation, or
2. `multiprocessing.Process` plus an IPC queue for explicit lifecycle control.

Recommendation: start with `multiprocessing.Process` because it makes cancellation, heartbeat, and explicit progress messaging easier to control than a pooled future.

## 6. Data Model

Add persistent queue tables under `BT`.

## 6.1 `BT.BACKTEST_JOB`

Purpose: durable queue item and job lifecycle record.

Proposed columns:

1. `BACKTEST_JOB_ID UUID`
2. `BACKTEST_JOB_VID INTEGER`
3. `BACKTEST_JOB_NM TEXT`
4. `JOB_STATE TEXT`
Allowed values: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`
5. `QUEUE_POS INTEGER`
6. `REQUEST_JSON JSONB`
Full optimize request payload submitted from the UI.
7. `SUMMARY_JSON JSONB`
User-facing summary for quick rendering in queue table.
8. `PROGRESS_JSON JSONB`
Current trial, total trials, best Sharpe, ETA if available.
9. `RESULT_JSON JSONB`
Small result summary only, not full chart payload.
10. `ERROR_JSON JSONB`
Failure details if the job fails.
11. `STARTED_AT TIMESTAMPTZ`
12. `FINISHED_AT TIMESTAMPTZ`
13. `USER_ID TEXT`
14. `CREATED_AT TIMESTAMPTZ`

Notes:

1. `REQUEST_JSON` is the authoritative replayable input.
2. `RESULT_JSON` is for queue/history display only; detailed analytics can still be loaded from BT result records or recomputed via existing endpoints.

## 6.2 `BT.BACKTEST_JOB_EVENT`

Purpose: append-only progress and audit log.

Proposed columns:

1. `BACKTEST_JOB_ID UUID`
2. `BACKTEST_JOB_EVENT_ID INTEGER GENERATED IDENTITY`
3. `EVENT_TYPE TEXT`
Examples: `ENQUEUED`, `STARTED`, `PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`
4. `EVENT_AT TIMESTAMPTZ`
5. `PAYLOAD_JSON JSONB`
6. `USER_ID TEXT`
7. `CREATED_AT TIMESTAMPTZ`

This table supports:

1. SSE replay from last event id if needed later
2. audit trail
3. debugging long-running jobs

## 6.3 Existing BT tables

Continue to use existing persistence for strategy/result snapshots:

1. strategy versioning via `BT.SP_INS_STRATEGY`
2. run metrics persistence via `BT.SP_INS_RESULT`

The queue tables do not replace those procedures. They orchestrate them.

## 7. Stored Procedures

Following the repository rule that application writes must go through stored procedures, add procedures such as:

1. `BT.SP_INS_BACKTEST_JOB`
2. `BT.SP_UPD_BACKTEST_JOB_STATE`
3. `BT.SP_UPD_BACKTEST_JOB_PROGRESS`
4. `BT.SP_CANCEL_BACKTEST_JOB`
5. `BT.SP_DEL_BACKTEST_JOB`
Only for queued jobs in first version
6. `BT.SP_INS_BACKTEST_JOB_EVENT`
7. `BT.SP_GET_BACKTEST_JOB`
8. `BT.SP_GET_BACKTEST_JOB_QUEUE`

State transition rules:

1. `QUEUED -> RUNNING`
2. `RUNNING -> COMPLETED`
3. `RUNNING -> FAILED`
4. `QUEUED -> CANCELLED`
5. `RUNNING -> CANCEL_REQUESTED` may be added later, but first version can disallow cancel of running jobs.

## 8. Backend API Design

## 8.1 New endpoints

### Queue mutation

1. `POST /api/v1/backtest/jobs`
Enqueue a new backtest job.

2. `DELETE /api/v1/backtest/jobs/{job_id}`
Remove a queued job.
If job is already running, return `409` in v1.

3. `POST /api/v1/backtest/jobs/{job_id}/cancel`
Cancel a queued job. Optional in v1 if delete is enough.

### Queue reads

1. `GET /api/v1/backtest/jobs`
Return queue and recent history.

2. `GET /api/v1/backtest/jobs/{job_id}`
Return detailed job status and summary.

3. `GET /api/v1/backtest/jobs/{job_id}/result`
Return persisted result summary or resolved BT result record.

### Live updates

1. `GET /api/v1/backtest/jobs/stream`
SSE stream for queue-level updates.

Event types:

1. `snapshot`
Full queue snapshot on connect.
2. `job_enqueued`
3. `job_started`
4. `job_progress`
5. `job_completed`
6. `job_failed`
7. `job_cancelled`
8. `job_removed`

## 8.2 Request shapes

### Enqueue request

```json
{
  "job_name": "BTC Bollinger 2016-now",
  "request": {
    "symbol": "BTC-USD",
    "start": "2016-01-01",
    "end": "2026-04-25",
    "mode": "single",
    "trading_period": 365,
    "fee_bps": 5,
    "data_source": "yahoo",
    "indicator": "bollinger",
    "strategy": "momentum",
    "window_range": { "min": 5, "max": 100, "step": 5 },
    "signal_range": { "min": 0.25, "max": 2.5, "step": 0.25 },
    "walk_forward": true,
    "split_ratio": 0.5
  }
}
```

### Queue row response

```json
{
  "job_id": "uuid",
  "job_name": "BTC Bollinger 2016-now",
  "state": "RUNNING",
  "queue_pos": 0,
  "submitted_at": "2026-04-25T12:00:00Z",
  "started_at": "2026-04-25T12:00:03Z",
  "summary": {
    "symbol": "BTC-USD",
    "mode": "single",
    "indicator": "bollinger",
    "strategy": "momentum"
  },
  "progress": {
    "trial": 734,
    "total": 20000,
    "remaining": 19266,
    "pct": 3.67,
    "best_sharpe": 1.4321
  }
}
```

## 9. Queue Coordinator Design

## 9.1 Startup

Create a `BacktestJobManager` in FastAPI lifespan. Responsibilities:

1. load initial queue snapshot
2. start a polling loop
3. own the worker-process handle
4. own SSE subscriber queues

## 9.2 Polling loop

Every short interval, for example 1 second:

1. if no running job exists, fetch the next queued job by queue position and creation time
2. atomically transition it to `RUNNING`
3. spawn worker process
4. consume progress messages from worker IPC queue
5. persist progress state periodically, not necessarily every trial
6. when worker exits, persist terminal state and start next job

## 9.3 IPC messages from worker

```json
{ "type": "started", "job_id": "..." }
{ "type": "progress", "job_id": "...", "trial": 10, "total": 20000, "best_sharpe": 1.02 }
{ "type": "completed", "job_id": "...", "result": { ... } }
{ "type": "failed", "job_id": "...", "error": { ... } }
```

## 9.4 Progress persistence policy

Do not write to DB on every trial for large jobs. That would create avoidable write pressure.

Persist progress on either:

1. every N trials, for example every 25 or 50, or
2. every T seconds, for example every 1 second, whichever comes first

SSE can still publish in-memory updates more frequently.

## 10. Execution Flow

## 10.1 Submit

1. User edits draft config in the UI.
2. User clicks `Add to Queue`.
3. Frontend sends enqueue request.
4. Backend persists `QUEUED` job.
5. SSE notifies all clients.

## 10.2 Run

1. Coordinator detects no active running job.
2. Coordinator claims the next queued job.
3. Worker process reconstructs the existing `OptimizeRequest`.
4. Worker calls the existing optimization pipeline.
5. Per-trial callback emits progress messages.
6. On completion:
   - persist strategy via `BT.SP_INS_STRATEGY`
   - persist result via `BT.SP_INS_RESULT`
   - update queue job to `COMPLETED`
   - publish completion event
7. Coordinator starts the next queued job.

## 10.3 Remove while another job runs

1. User removes a queued row from the right-side table.
2. Backend validates that the target job is still `QUEUED`.
3. Backend marks it `CANCELLED` or deletes it, depending on retention preference.
4. Queue positions are normalized.
5. Running job continues uninterrupted.

## 11. Frontend Design

## 11.1 State split

Split frontend state into three concerns:

1. `draftConfig`
The editable form in the drawer.

2. `queue`
Live list of backend job rows.

3. `selectedJob`
The queue/history row currently being inspected in the results panel.

Current `config` state in `BacktestPage.tsx` becomes `draftConfig`.

## 11.2 Layout

Current page is vertically stacked. Proposed layout:

1. left main column
Draft config, selected job results, charts, completed-job analysis.

2. right side panel
Queue table with pending/running/recent jobs.

Desktop layout:

1. main content: about 70%
2. queue panel: about 30%

Mobile layout:

1. queue panel collapses under main content or into a drawer.

## 11.3 Queue table columns

1. position
2. state
3. name
4. symbol
5. factor summary
6. submitted time
7. progress bar
8. trials left
9. best Sharpe so far
10. actions

Actions:

1. remove for queued jobs
2. inspect for completed/running jobs
3. retry for failed jobs later

## 11.4 Progress bar behavior

For running job:

1. `value = trial / total * 100`
2. label `734 / 20000`
3. secondary caption `19266 left`

For queued jobs:

1. empty bar or queued badge only

For completed jobs:

1. full bar with completed badge

## 11.5 Editable UI while jobs run

This requirement is critical. The UI must not bind the form directly to the running job.

Rules:

1. Editing the draft form never mutates already queued jobs.
2. Clicking `Add to Queue` snapshots the current draft into a new submitted job.
3. Removing a queued job affects only that queued item.
4. The results area shows the selected job, not necessarily the draft.

This means the form remains fully usable while one job is running and others are queued.

## 11.6 User actions

Primary CTA changes from `Run Optimization` to two actions:

1. `Run Now`
If no active running job and queue empty, enqueue and allow immediate start.

2. `Add to Queue`
Always enqueue the current draft.

Optional future action:

1. `Save Draft`

## 12. Live Update Transport

Use SSE for queue updates in version 1.

Reasons:

1. The app already uses SSE patterns for optimization progress.
2. Queue updates are server-to-client only.
3. Browser and FastAPI support is straightforward.

One queue stream endpoint broadcasts all queue changes. The frontend maintains local queue state by applying events.

## 13. Result Inspection Model

When a job completes:

1. queue row changes to `COMPLETED`
2. user can click the row
3. frontend loads detailed result payload for that job

Detailed result handling options:

1. store compact result pointers in `BT.BACKTEST_JOB.RESULT_JSON` and fetch detailed metrics/charts through a result endpoint
2. store enough rendered response JSON directly in the job record for quick inspection

Recommendation:

1. persist small summary in job table
2. persist canonical strategy/result in existing BT tables
3. load detailed analytics via dedicated API when the user selects a completed job

## 14. Failure Handling

### Job failure

If a job fails:

1. mark `FAILED`
2. persist error payload
3. publish `job_failed`
4. automatically continue to next queued job

### API restart

Because queue state is persisted:

1. queued jobs remain queued
2. a job previously marked `RUNNING` should be recovered on startup

Recovery policy in v1:

1. on startup, any stale `RUNNING` jobs become `FAILED` with restart reason, or
2. they are moved back to `QUEUED`

Recommendation: move stale `RUNNING` to `QUEUED` if no partial result persistence exists.

## 15. Performance Considerations

1. Single worker prevents CPU oversubscription.
2. DB progress writes should be throttled.
3. SSE payloads should be compact.
4. Queue list endpoint should return only current queue plus recent history, not all historical jobs.

## 16. Security and Multi-User Readiness

Even if current use is single-user, include `USER_ID` on queue rows so the design can later support:

1. per-user queues
2. filtered history
3. access control

## 17. Phased Implementation Plan

## Phase 1: Single-instance durable queue

1. Add queue tables and procedures
2. Add job manager in API lifespan
3. Add single worker process
4. Add enqueue/list/remove endpoints
5. Add queue SSE endpoint
6. Add right-side queue panel in frontend
7. Keep existing single-run analysis rendering for completed selected job

Outcome:

1. one running job
2. many queued jobs
3. add/remove while running
4. live progress bar and iterations left

## Phase 2: Better history and retry

1. add completed/failed tabs
2. add retry action
3. add queue reorder endpoint
4. add persisted event history view

## Phase 3: Running job cancel and resumability

1. cooperative cancel for running worker
2. heartbeat and stale job recovery
3. optional partial result persistence

## 18. Open Questions

1. Should removing a queued job hard-delete it, or mark it `CANCELLED` for auditability?
Recommendation: mark `CANCELLED`.

2. Should the queue be global or per user?
Recommendation: model for per-user now, even if initially filtered to one user.

3. Should we allow queue reorder in v1?
Recommendation: no. FIFO first.

4. Should the running job be cancellable in v1?
Recommendation: no. Defer until cooperative cancel is designed.

5. Should detailed chart data be stored in the queue table?
Recommendation: no. Store summaries in queue, canonical metrics in BT result tables.

## 19. Recommendation

Implement a durable FIFO queue with:

1. PostgreSQL-backed job state
2. a single process-based worker
3. SSE queue updates
4. frontend separation between editable draft and submitted jobs

## 20. Technology Choice — Why Postgres, Not Kafka or Redis

This section documents why the queue is built on PostgreSQL rather than a dedicated broker.

### 20.1 What we actually need

| Need | Required by Quant Strategies today |
|------|-----------------------------------|
| Durable job state across API restarts | Yes |
| FIFO ordering with backpressure | Yes |
| At-most-one worker pulling at a time | Yes (Phase 1) |
| Live progress events to one browser session | Yes (SSE) |
| Multi-consumer fan-out of the same event stream | No |
| Millions of events / second | No |
| Cross-service event distribution | No |
| Schema registry, partitions, consumer groups | No |

### 20.2 Why not Kafka

Kafka solves problems we do not have:

1. **Operational weight.** Kafka requires a broker cluster, KRaft (or ZooKeeper), partition planning, retention policies, and typically a schema registry. None of this is justified for a single-tenant FastAPI backend.
2. **Wrong primitive.** Kafka is a high-throughput append-only log designed for fan-out to many independent consumers. Our queue has exactly one consumer (the worker process) and needs `SELECT ... FOR UPDATE SKIP LOCKED` semantics, which a log does not natively provide.
3. **Volume mismatch.** A backtest job is one row every few seconds at most. Kafka starts to pay back at thousands of events per second.
4. **No existing dependency.** Adding Kafka means a new container, new credentials, new monitoring surface — versus reusing the Postgres cluster we already operate on AWS RDS.

Kafka would only become interesting if we later add (a) a live tick-data ingestion pipeline fanning out to multiple strategy processes, or (b) cross-service event distribution between FastAPI, a separate execution gateway, and an audit store.

### 20.3 Why not Redis (RQ / Streams)

Redis-based queues (RQ, Celery+Redis, Redis Streams) are a reasonable middle ground but were rejected for v1:

1. **New stateful service.** Redis would become a second piece of infrastructure that must be backed up, monitored, and access-controlled — for a workload Postgres can already handle.
2. **No transactional coupling.** A backtest job completion needs to (a) update job state, (b) write rows into `BT.RESULT` / `BT.API_REQUEST_PAYLOAD`. With Postgres-backed jobs this is one transaction. With Redis it becomes a two-phase coordination problem.
3. **Loss of SQL inspection.** Operators can already `SELECT * FROM BT.BACKTEST_JOB WHERE STATUS = 'failed'` from psql. With Redis we would need a separate inspection tool.

Redis becomes worth re-evaluating if (a) job submission rate grows past a few per second sustained, or (b) we need pub/sub fan-out for live progress to many browser tabs.

### 20.4 Why Postgres fits

1. **Already operated.** The cluster, credentials, backups, and migration tooling (Liquibase) are in place.
2. **`SELECT ... FOR UPDATE SKIP LOCKED`** gives exactly the dequeue semantics we need with no extra library.
3. **`LISTEN` / `NOTIFY`** can drive live SSE updates without a separate broker.
4. **Transactional integrity** between job state and result rows is free.
5. **No new failure mode** — if Postgres is down the API is already down.

Throughput ceiling on a single Aurora instance for this pattern is comfortably in the hundreds of jobs per second, well beyond our requirements.

### 20.5 Lighter still — when even a queue is overkill

If usage stays single-user and one optimization at a time is acceptable, a `concurrency_limit` semaphore in `api/services/backtest.py` is sufficient and adds zero schema. The full queue design in this document is justified once any of the following becomes true:

1. Multiple users submitting concurrently
2. The user wants to enqueue several runs and walk away
3. Optimizations routinely exceed a few minutes and tying up a uvicorn worker becomes painful

Until then, the queue can be implemented behind the same API surface (POST returns a job id immediately) so the migration is transparent to the frontend.

### 20.6 Decision

Postgres-backed FIFO queue, single worker, `LISTEN/NOTIFY` for live updates. Re-evaluate Redis if submission rate or fan-out grows; re-evaluate Kafka only if a live market-data ingestion pipeline is added.

This satisfies the user requirement that the UI remains editable while a long backtest is running, while also addressing the Python threading limitation correctly by using a separate process for CPU-bound execution.