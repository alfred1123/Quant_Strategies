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
import uuid
from typing import Callable

import redis

from api.config import get_redis_url, load_config
from quant.queue.wake import wait_for_wake
from quant.refdata.reader import RedisRefData
from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class WorkerLoopRepo(DbGateway):
    """DB calls used by the loop: claim head, list-by-status, mark FAILED."""

    def list_by_status(self, queue_status_id: int) -> list[dict]:
        """Active QUEUE rows with the given status, priority/time-ordered."""
        return self._query(
            "SELECT * FROM bt.fn_get_queue_for_terminal(NULL, %s)",
            (int(queue_status_id),),
        )

    def claim_next(self, queued_status_id: int, running_status_id: int) -> dict | None:
        """Pop the head of the QUEUED ranking → transition RUNNING.

        Phase A pattern (per ``docs/design/backtest-queue.md`` §9.4): read
        head + write RUNNING in two statements. NOT atomic across multiple
        loops — single-replica only. Multi-replica deployments need a
        future ``BT.SP_CLAIM_NEXT`` that does both inside one SP.

        Returns the claimed job row (dict) or ``None`` when the queue is
        empty.
        """
        rows = self._query(
            "SELECT * FROM bt.fn_get_queue_for_terminal(NULL, %s) LIMIT 1",
            (int(queued_status_id),),
        )
        if not rows:
            return None
        row = rows[0]
        self._call_write(
            "CALL bt.sp_ins_queue("
            "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(row["queue_id"]),
                str(row["strategy_id"]),
                int(row["strategy_vid"]),
                int(running_status_id),
                int(row["priority"]),
                None,
                row["user_id"],
            ),
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
        self._call_write(
            "CALL bt.sp_ins_queue("
            "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(queue_id),
                str(strategy_id),
                int(strategy_vid),
                int(failed_status_id),
                int(priority),
                error_text,
                user_id,
            ),
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

    def __init__(
        self,
        db_url: str,
        redis_url: str,
        *,
        max_concurrent: int = 1,
        spawn_fn: SpawnFn | None = None,
        repo: WorkerLoopRepo | None = None,
        refdata: RedisRefData | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._db_url = db_url
        self._redis_url = redis_url
        self.max_concurrent = max_concurrent
        self._spawn = spawn_fn or default_spawn
        self._repo = repo or WorkerLoopRepo(db_url)
        self._refdata = refdata or RedisRefData(redis_url)
        self._redis = redis_client or redis.Redis.from_url(redis_url)
        self._active: dict[uuid.UUID, subprocess.Popen] = {}
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
        finished = [qid for qid, proc in self._active.items() if proc.poll() is not None]
        for qid in finished:
            proc = self._active.pop(qid)
            logger.info("worker %s exited with code %s", qid, proc.returncode)

    def _try_claim_and_spawn(self) -> bool:
        """Claim one job and spawn its worker. Returns True iff a job was spawned."""
        queued_id = self._refdata.resolve_queue_status_id("QUEUED")
        running_id = self._refdata.resolve_queue_status_id("RUNNING")
        job = self._repo.claim_next(queued_id, running_id)
        if job is None:
            return False
        qid = uuid.UUID(str(job["queue_id"]))
        proc = self._spawn(qid)
        self._active[qid] = proc
        logger.info("spawned worker for %s (pid=%s)", qid, getattr(proc, "pid", "?"))
        return True

    def tick(self) -> None:
        """One iteration: reap finished children, fill capacity. Non-blocking."""
        self._reap_children()
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
        for qid, proc in list(self._active.items()):
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
    loop = WorkerLoop(db_url, get_redis_url(), max_concurrent=max_concurrent)
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
