"""BacktestJobManager — coordinator that lives inside the FastAPI lifespan.

Responsibilities:
  - Stale-job recovery on startup (RUNNING jobs with no live worker → FAILED).
  - Claim loop: when a job is enqueued (or a slot frees), find the next QUEUED
    job ordered by PRIORITY ASC / CREATED_AT ASC, transition it to RUNNING via
    SP_INS_QUEUE, then spawn a worker process.
  - Worker supervision: detect unclean exits and mark the job FAILED.
  - SSE fanout: broadcast queue events to all connected SSE subscribers.
  - 30-second watchdog: re-runs stale recovery and re-triggers the claim loop
    in case a wakeup was missed.

Submit flow (separation of concerns):
  1. Router (api/routers/backtest.py) — HTTP boundary only: parse + validate
     the request, call repo.submit(), notify the manager, return 202.
  2. BacktestJobRepo.submit() (src/jobs.py) — business logic: generate
     queue_id, resolve status, call SP_INS_QUEUE(QUEUED) → BT.QUEUE.
  3. manager.notify_enqueued() — posts a wakeup signal so the claim loop
     picks up the new job without waiting for the 30-second watchdog.

Wakeup mechanism:
  Uses asyncio.Queue[str] (not asyncio.Event) so wakeups never coalesce and
  the queue is safe to write from other threads via loop.call_soon_threadsafe.

No LISTEN/NOTIFY is wired yet — SP_INS_QUEUE does not emit pg_notify.
When SP_CLAIM_NEXT is added, replace _claim_next() with a single atomic
_call_write call and drop the two-connection SELECT + SP_INS_QUEUE pattern.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import uuid
from typing import Any

_WAKEUP_ENQUEUED = "enqueued"
_WAKEUP_WATCHDOG = "watchdog"

import psycopg

from src.data import RefDataCache
from src.jobs import BacktestJobRepo, QueueRow

logger = logging.getLogger(__name__)

_WATCHDOG_INTERVAL = 30  # seconds


class BacktestJobManager:
    def __init__(self, conninfo: str, refdata: RefDataCache) -> None:
        self._conninfo = conninfo
        self._repo = BacktestJobRepo(conninfo, refdata)
        self._worker: multiprocessing.Process | None = None
        self._worker_queue_id: uuid.UUID | None = None
        self._sse_subscribers: set[asyncio.Queue] = set()
        # asyncio.Queue is thread-safe via loop.call_soon_threadsafe — safe for
        # future multi-thread callers. Unlike Event, queued wakeups never coalesce.
        self._wakeup: asyncio.Queue[str] = asyncio.Queue()
        self._loop_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Called from FastAPI lifespan on startup."""
        await asyncio.get_running_loop().run_in_executor(None, self._recover_stale)
        await self._maybe_claim_and_spawn()
        self._loop_task = asyncio.create_task(self._event_loop(), name="bt-job-loop")
        self._watchdog_task = asyncio.create_task(self._watchdog(), name="bt-job-watchdog")
        logger.info("BacktestJobManager started")

    async def stop(self) -> None:
        """Called from FastAPI lifespan on shutdown."""
        for task in (self._loop_task, self._watchdog_task):
            if task:
                task.cancel()
        if self._worker and self._worker.is_alive():
            logger.warning("Terminating worker pid=%s on manager shutdown", self._worker.pid)
            self._worker.terminate()
            self._worker.join(timeout=5)
        logger.info("BacktestJobManager stopped")

    # ── public API for the router ──────────────────────────────────────────

    def notify_enqueued(self) -> None:
        """Router calls this after a successful SP_INS_QUEUE(ENQUEUE).
        Thread-safe: may be called from any thread via loop.call_soon_threadsafe.
        """
        self._wakeup.put_nowait(_WAKEUP_ENQUEUED)

    # ── SSE subscriber management ──────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._sse_subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._sse_subscribers.discard(q)

    async def broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self._sse_subscribers):
            await q.put(event)

    # ── internal tasks ─────────────────────────────────────────────────────

    async def _event_loop(self) -> None:
        while True:
            try:
                reason = await self._wakeup.get()
                logger.debug("Claim loop wakeup: %s", reason)
                await self._handle_worker_exit_if_done()
                await self._maybe_claim_and_spawn()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Unexpected error in job event loop")

    async def _watchdog(self) -> None:
        while True:
            try:
                await asyncio.sleep(_WATCHDOG_INTERVAL)
                await self._handle_worker_exit_if_done()
                await asyncio.get_event_loop().run_in_executor(None, self._recover_stale)
                self._wakeup.put_nowait(_WAKEUP_WATCHDOG)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Unexpected error in job watchdog")

    # ── worker management ──────────────────────────────────────────────────

    async def _maybe_claim_and_spawn(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return  # slot occupied
        row = await asyncio.get_event_loop().run_in_executor(None, self._claim_next)
        if row is None:
            return
        self._spawn_worker(row)

    def _claim_next(self) -> QueueRow | None:
        """Find the highest-priority QUEUED row and transition it to RUNNING.

        Uses a plain SELECT + SP_INS_QUEUE on separate connections.  FOR UPDATE
        is intentionally omitted: BacktestJobManager is the only writer of
        RUNNING rows in this single-manager design, so there is no concurrent
        claim race.  When a SP_CLAIM_NEXT stored procedure is added, replace
        this method with a single _call_write call that does both steps
        atomically.
        """
        with psycopg.connect(self._conninfo) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT q.QUEUE_ID, q.STRATEGY_ID, q.STRATEGY_VID, q.PRIORITY, q.USER_ID"
                "  FROM BT.QUEUE q"
                "  JOIN REFDATA.QUEUE_STATUS rs ON rs.QUEUE_STATUS_ID = q.QUEUE_STATUS_ID"
                " WHERE rs.NAME = 'QUEUED'"
                "   AND q.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'"
                " ORDER BY q.PRIORITY ASC, q.CREATED_AT ASC"
                " LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                return None
            queue_id, strategy_id, strategy_vid, priority, user_id = row

        running_id = self._repo.get_status_id("RUNNING")
        self._repo.insert_queue(
            queue_id=queue_id,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            queue_status_id=running_id,
            priority=priority,
            user_id=user_id,
        )
        logger.info("Claimed queue_id=%s strategy_id=%s → RUNNING", queue_id, strategy_id)

        rows = self._repo.query_queue(queue_id=queue_id, limit=1)
        return rows[-1] if rows else None

    def _spawn_worker(self, row: QueueRow) -> None:
        from api.queue.worker import run as run_worker

        self._worker_queue_id = row.queue_id
        self._worker = multiprocessing.Process(
            target=run_worker,
            args=(row.queue_id, self._conninfo),
            daemon=True,
            name=f"bt-worker-{row.queue_id}",
        )
        self._worker.start()
        logger.info(
            "Worker spawned — queue_id=%s strategy_id=%s pid=%s",
            row.queue_id, row.strategy_id, self._worker.pid,
        )
        asyncio.ensure_future(
            self.broadcast({"event": "job_started", "queue_id": str(row.queue_id)})
        )

    async def _handle_worker_exit_if_done(self) -> None:
        if self._worker is None or self._worker.is_alive():
            return
        exit_code = self._worker.exitcode
        queue_id = self._worker_queue_id
        self._worker = None
        self._worker_queue_id = None

        logger.info("Worker exited — queue_id=%s exit_code=%s", queue_id, exit_code)

        if queue_id is None:
            return

        # If worker crashed without writing a terminal state, mark FAILED.
        rows = self._repo.query_queue(queue_id=queue_id, limit=10)
        active = rows[-1] if rows else None
        if active and active.queue_status in ("QUEUED", "RUNNING"):
            failed_id = self._repo.get_status_id("FAILED")
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._repo.insert_queue(
                    queue_id=active.queue_id,
                    strategy_id=active.strategy_id,
                    strategy_vid=active.strategy_vid,
                    queue_status_id=failed_id,
                    priority=active.priority,
                    error_text=f"Worker crashed (exit code {exit_code})",
                    user_id=active.user_id,
                ),
            )
            logger.error(
                "Marked queue_id=%s as FAILED after worker crash (exit code %s)",
                queue_id, exit_code,
            )

        await self.broadcast({"event": "job_finished", "queue_id": str(queue_id), "exit_code": exit_code})
        # Free slot — attempt to claim next job.
        self._wakeup.put_nowait(_WAKEUP_ENQUEUED)

    # ── stale-job recovery ─────────────────────────────────────────────────

    def _recover_stale(self) -> None:
        """On startup (or watchdog): any RUNNING job with no live worker → FAILED.

        Does not auto-requeue — results may have been partially written.
        """
        running_rows = self._repo.query_queue(status_name="RUNNING")
        if not running_rows:
            return
        failed_id = self._repo.get_status_id("FAILED")
        for row in running_rows:
            # Skip if this is the currently supervised worker.
            if self._worker_queue_id == row.queue_id and self._worker and self._worker.is_alive():
                continue
            logger.warning(
                "Stale RUNNING job detected — queue_id=%s → FAILED", row.queue_id
            )
            self._repo.insert_queue(
                queue_id=row.queue_id,
                strategy_id=row.strategy_id,
                strategy_vid=row.strategy_vid,
                queue_status_id=failed_id,
                priority=row.priority,
                error_text="API restarted while job was running",
                user_id=row.user_id,
            )
