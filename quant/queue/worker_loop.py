"""Long-lived backtest worker loop — Phase A of v6.

See ``docs/design/backtest-queue.md`` §0 (v6 plan) and §10 (worker contract).

Replaces ``coordinator/src/queue/{manager,spawn}.ts``. One process per
container; bump ``MAX_CONCURRENT_WORKERS`` to spawn multiple worker
subprocesses per loop.

Lifecycle:

    1. Boot: mark every active ``RUNNING`` row as ``FAILED`` (orphan recovery).
       Single-replica assumption — see ``recover_stale`` docstring.
    2. Loop:
         - Reap finished children (non-blocking).
         - While ``len(active) < max_concurrent``:
             - ``claim_next()`` — if Some(job), spawn worker subprocess.
             - else break.
         - ``wait_for_wake(timeout=BLPOP_TIMEOUT_S)`` — blocks until a
           producer pushes to ``bt:queue:wake`` or the safety timeout fires.

Crash isolation: each worker runs as a ``subprocess.Popen([python, -m,
quant.queue.worker, queue_id])``, so a numpy/pandas crash kills only
that child, not the loop.

Invocation::

    python -m quant.queue.worker_loop
"""

import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from typing import Callable

import redis

from quant.api.config import get_redis_url, load_config
from quant.queue.repo import BtQueueRepo
from quant.queue.wake import wait_for_wake
from quant.refdata.reader import RedisRefData

logger = logging.getLogger(__name__)


class WorkerLoopRepo(BtQueueRepo):
    """DB calls used by the loop: claim head, list-by-status, mark FAILED."""

    def list_by_status(self, queue_status_id: int, *, limit: int = 1000) -> list[dict]:
        """Active QUEUE rows with the given status, dequeue-ordered.

        Wraps :meth:`BtQueueRepo.sp_get_queue` with ``queue_id=None`` so the
        SP scopes to active rows ordered ``(PRIORITY ASC, CREATED_AT ASC)``
        — the dequeue ranking per ``docs/design/backtest-queue.md`` §6.1.
        """
        return self.sp_get_queue(queue_status_id=queue_status_id, limit=limit)

    def claim_next(self, queued_status_id: int, running_status_id: int) -> dict | None:
        """Pop the head of the QUEUED ranking → transition RUNNING.

        Phase A pattern (per ``docs/design/backtest-queue.md`` §9.4): read
        head + write RUNNING in two statements. NOT atomic across multiple
        loops — single-replica only. Multi-replica deployments need a
        future ``BT.SP_CLAIM_NEXT`` that does both inside one SP.

        Returns the claimed job row (dict) or ``None`` when the queue is
        empty. ``BT.FN_GET_QUEUE_FOR_TERMINAL`` is reserved for UI display
        — the worker uses ``BT.SP_GET_QUEUE`` (REFCURSOR) instead.
        """
        rows = self.list_by_status(queued_status_id, limit=1)
        if not rows:
            return None
        row = rows[0]
        self.sp_ins_queue(
            queue_id=row["queue_id"],
            strategy_id=row["strategy_id"],
            strategy_vid=int(row["strategy_vid"]),
            status_id=running_status_id,
            priority=int(row["priority"]),
            user_id=row["user_id"],
        )
        return row

    def mark_failed(
        self,
        queue_id,
        strategy_id,
        strategy_vid: int,
        priority: int,
        user_id: str,
        failed_status_id: int,
        error_text: str,
    ) -> None:
        self.sp_ins_queue(
            queue_id=queue_id,
            strategy_id=strategy_id,
            strategy_vid=int(strategy_vid),
            status_id=failed_status_id,
            priority=int(priority),
            user_id=user_id,
            error_text=error_text,
        )


SpawnFn = Callable[[uuid.UUID], subprocess.Popen]


def default_spawn(queue_id: uuid.UUID) -> subprocess.Popen:
    """Spawn one worker subprocess. Inherits parent env (DB_URL, REDIS_URL, ...)."""
    return subprocess.Popen(
        [sys.executable, "-m", "quant.queue.worker", str(queue_id)],
    )


class WorkerLoop:
    """Wakeup-driven loop that claims QUEUED jobs and spawns worker subprocs."""

    BLPOP_TIMEOUT_S = 30
    DRAIN_TIMEOUT_S = 30
    DEFAULT_JOB_TIMEOUT_S = 6000  # 100 min hard cap per backtest job — presented as FAILED.

    def __init__(
        self,
        db_url: str,
        redis_url: str,
        *,
        max_concurrent: int = 1,
        job_timeout_s: int = DEFAULT_JOB_TIMEOUT_S,
        spawn_fn: SpawnFn | None = None,
        repo: WorkerLoopRepo | None = None,
        refdata: RedisRefData | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._db_url = db_url
        self._redis_url = redis_url
        self.max_concurrent = max_concurrent
        self.JOB_TIMEOUT_S = job_timeout_s
        self._spawn = spawn_fn or default_spawn
        self._repo = repo or WorkerLoopRepo(db_url)
        self._refdata = refdata or RedisRefData(redis_url)
        self._redis = redis_client or redis.Redis.from_url(redis_url)
        # Tracks (Popen, start_monotonic, job_row) per claimed queue_id so we
        # can kill + mark FAILED after JOB_TIMEOUT_S.
        self._active: dict[uuid.UUID, tuple[subprocess.Popen, float, dict]] = {}
        self._running = False

    # ── boot recovery ────────────────────────────────────────────────────

    def recover_stale(self) -> int:
        """Mark every currently-RUNNING row as FAILED on boot.

        Rationale: this loop just started and owns no children, so by
        definition any RUNNING row in ``BT.QUEUE`` belongs to a worker
        whose parent loop has died. Single-replica assumption: in a
        multi-host deployment this would steal another loop's jobs;
        multi-replica needs a per-loop ownership column (out of scope
        for Phase A).

        Returns the number of recovered rows.
        """
        running_id = self._refdata.resolve_queue_status_id("RUNNING")
        failed_id = self._refdata.resolve_queue_status_id("FAILED")
        rows = self._repo.list_by_status(running_id)
        for row in rows:
            self._repo.mark_failed(
                row["queue_id"],
                row["strategy_id"],
                row["strategy_vid"],
                row["priority"],
                row["user_id"],
                failed_id,
                "worker_loop restarted while job was running",
            )
            logger.warning("recovered orphan RUNNING job %s -> FAILED", row["queue_id"])
        return len(rows)

    # ── per-tick steps ───────────────────────────────────────────────────

    def _reap_children(self) -> None:
        finished = [
            qid for qid, (proc, _start, _row) in self._active.items()
            if proc.poll() is not None
        ]
        for qid in finished:
            proc, _start, _row = self._active.pop(qid)
            logger.info("worker %s exited with code %s", qid, proc.returncode)

    def _enforce_timeouts(self) -> None:
        """Kill workers exceeding JOB_TIMEOUT_S; flip their row to FAILED.

        Mirrors the orphan-recovery path: we own the FAILED transition
        here because the worker subprocess is being killed mid-flight and
        cannot write its own terminal row.
        """
        now = time.monotonic()
        failed_id: int | None = None
        for qid in list(self._active.keys()):
            proc, start, row = self._active[qid]
            if proc.poll() is not None:
                continue  # _reap_children will pick it up next tick
            if now - start < self.JOB_TIMEOUT_S:
                continue
            logger.warning(
                "worker %s exceeded JOB_TIMEOUT_S=%ds \u2014 killing",
                qid, self.JOB_TIMEOUT_S,
            )
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error("worker %s did not exit after SIGKILL", qid)
            if failed_id is None:
                failed_id = self._refdata.resolve_queue_status_id("FAILED")
            self._repo.mark_failed(
                row["queue_id"],
                row["strategy_id"],
                row["strategy_vid"],
                row["priority"],
                row["user_id"],
                failed_id,
                f"job exceeded {self.JOB_TIMEOUT_S}s timeout",
            )
            self._active.pop(qid, None)

    def _try_claim_and_spawn(self) -> bool:
        """Claim one job and spawn its worker. Returns True iff a job was spawned."""
        queued_id = self._refdata.resolve_queue_status_id("QUEUED")
        running_id = self._refdata.resolve_queue_status_id("RUNNING")
        job = self._repo.claim_next(queued_id, running_id)
        if job is None:
            return False
        qid = uuid.UUID(str(job["queue_id"]))
        proc = self._spawn(qid)
        self._active[qid] = (proc, time.monotonic(), job)
        logger.info("spawned worker for %s (pid=%s)", qid, getattr(proc, "pid", "?"))
        return True

    def tick(self) -> None:
        """One iteration: reap finished children, enforce timeouts, fill capacity."""
        self._reap_children()
        self._enforce_timeouts()
        while self._running and len(self._active) < self.max_concurrent:
            if not self._try_claim_and_spawn():
                break

    # ── lifecycle ────────────────────────────────────────────────────────

    def run(self) -> None:
        """Main loop. Blocks until SIGTERM/SIGINT or ``stop()``."""
        self._running = True
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        n = self.recover_stale()
        if n:
            logger.warning("recovered %d orphan RUNNING job(s) on boot", n)

        logger.info("worker_loop started — max_concurrent=%d", self.max_concurrent)
        while self._running:
            self.tick()
            if not self._running:
                break
            wait_for_wake(self._redis, timeout=self.BLPOP_TIMEOUT_S)

        self._drain()
        logger.info("worker_loop stopped")

    def _drain(self) -> None:
        """Wait for active children to exit on shutdown; kill survivors."""
        for qid, (proc, _start, _row) in list(self._active.items()):
            logger.info("waiting for worker %s to exit before shutdown", qid)
            try:
                proc.wait(timeout=self.DRAIN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                logger.warning("worker %s did not exit in %ds — killing", qid, self.DRAIN_TIMEOUT_S)
                proc.kill()

    def stop(self) -> None:
        if self._running:
            logger.info("worker_loop stop requested")
            self._running = False


def main() -> int:
    db_url = load_config()
    max_concurrent = int(os.getenv("MAX_CONCURRENT_WORKERS", "1"))
    job_timeout_s = int(os.getenv("JOB_TIMEOUT_S", str(WorkerLoop.DEFAULT_JOB_TIMEOUT_S)))
    loop = WorkerLoop(
        db_url,
        get_redis_url(),
        max_concurrent=max_concurrent,
        job_timeout_s=job_timeout_s,
    )
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
