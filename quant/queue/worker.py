"""Backtest worker — Slice C minimum (no progress, no cancel, no timeout).

Invocation:
    python -m quant.queue.worker <queue_id>

See docs/design/backtest-queue.md §10 for the full contract. This Slice C
implementation covers steps 1-4 + 7 + 9 + 11-12 only:

    1. Parse queue_id from argv.
    2. Connect to DB via DB_URL env var.
    3. Read CONFIG_JSON for the strategy version snapshot in BT.QUEUE.
    4. Reconstruct OptimizeRequest, run optimization to completion.
    7. Emit `started` JSON on stdout.
    9. CALL BT.SP_INS_RESULT (client UUID RESULT_ID), then SP_INS_QUEUE → COMPLETED.
   11. On any uncaught error → SP_INS_QUEUE → FAILED with traceback.
   12. Emit `terminal` JSON, exit 0.

Slice D adds: per-trial progress, signal-based cancel, deadline.

Exit codes (per §10.1):
    0 — terminal state written to DB (COMPLETED, FAILED, or CANCELLED).
    1 — uncaught crash before the FAILED row could be written.
    2 — config error (bad argv, missing env, queue row not found, bad JSON).
"""

import json
import logging
import sys
import traceback
import uuid

from quant.shared.config import load_config, get_redis_url
from quant.schemas.backtest import OptimizeRequest
from quant.strategy.backtest_service import run_optimize

from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches
from quant.shared.util import utc_now_iso

logger = logging.getLogger(__name__)


class WorkerRepo(BtQueueRepo):
    """All BT.* DB access for the worker — REFCURSOR drain + SP write."""

    # ── reads ───────────────────────────────────────────────────────────

    def fetch_job(self, queue_id: uuid.UUID) -> dict:
        """Active QUEUE row + frozen ``CONFIG_JSON`` via ``BT.SP_GET_QUEUE_LATEST`` (one ``_call_get``)."""
        row = self.sp_get_queue_latest(queue_id)
        if row is None:
            raise LookupError(
                f"no active BT.QUEUE row (or missing frozen STRATEGY) for queue_id={queue_id}"
            )
        return row

    # ── writes ──────────────────────────────────────────────────────────

    def ins_result(
        self, result_id: uuid.UUID, queue_id: uuid.UUID, payload: dict, user_id: str
    ) -> None:
        """SP_INS_RESULT — OUT row ``(SQLSTATE, SQLMSG, SQLERRMC)`` only (same as SP_INS_QUEUE)."""
        self._call_write(
            "CALL bt.sp_ins_result("
            "%s::uuid, %s::uuid, %s::jsonb, %s::text, NULL::text, NULL::text, NULL::text)",
            (str(result_id), str(queue_id), json.dumps(payload, default=str), user_id),
        )


class BacktestWorker:
    """Runs one queued optimization job: REFDATA, caches, DB repo, stdout events."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    def _emit(self, event: dict) -> None:
        """Write one newline-delimited JSON event to stdout (§10.3)."""
        print(json.dumps(event), flush=True)

    def run(self, queue_id: uuid.UUID) -> int:
        """Main worker flow. Returns the process exit code."""
        caches = DataCaches(self._db_url, get_redis_url())
        caches.require_redis()
        caches.load_instruments(soft_fail=True)
        refdata = caches.refdata

        completed_id = refdata.resolve_queue_status_id("COMPLETED")
        failed_id = refdata.resolve_queue_status_id("FAILED")

        repo = WorkerRepo(self._db_url)
        job = repo.fetch_job(queue_id)

        self._emit({"type": "started", "queue_id": str(queue_id), "ts": utc_now_iso()})

        try:
            req = OptimizeRequest.model_validate(job["config_json"])
        except Exception as exc:  # bad CONFIG_JSON shape — config error
            raise ValueError(f"CONFIG_JSON failed OptimizeRequest validation: {exc}") from exc

        try:
            response = run_optimize(
                req,
                refdata,
                inst_cache=caches.instrument_cache,
                bt_cache=caches.backtest_cache,
            )
        except Exception:
            err = traceback.format_exc()
            logger.error("optimize failed for queue_id=%s\n%s", queue_id, err)
            repo.sp_ins_queue(
                queue_id=queue_id,
                strategy_id=job["strategy_id"],
                strategy_vid=job["strategy_vid"],
                status_id=failed_id,
                priority=job["priority"],
                user_id=job["user_id"],
                error_text=err,
            )
            self._emit({
                "type": "terminal", "queue_id": str(queue_id),
                "status": "FAILED", "ts": utc_now_iso(),
            })
            return 0  # FAILED row written → clean exit per §10.1.

        result_id = uuid.uuid4()
        repo.ins_result(result_id, queue_id, response.model_dump(), job["user_id"])
        repo.sp_ins_queue(
            queue_id=queue_id,
            strategy_id=job["strategy_id"],
            strategy_vid=job["strategy_vid"],
            status_id=completed_id,
            priority=job["priority"],
            user_id=job["user_id"],
        )
        self._emit({
            "type": "terminal", "queue_id": str(queue_id),
            "status": "COMPLETED", "result_id": str(result_id), "ts": utc_now_iso(),
        })
        return 0


def main(argv: list[str]) -> int:
    # Initialise logging + load .env/SSM + DB conninfo via quant.shared.config.load_config().
    db_url = load_config()

    if len(argv) != 2:
        logger.error("usage: python -m src.worker <queue_id>")
        return 2
    try:
        queue_id = uuid.UUID(argv[1])
    except ValueError:
        logger.error("invalid queue_id (not a UUID): %r", argv[1])
        return 2

    try:
        return BacktestWorker(db_url).run(queue_id)
    except LookupError as exc:
        logger.error("config error: %s", exc)
        return 2
    except Exception:
        logger.exception(
            "uncaught error before FAILED could be written "
            "(coordinator reaper should mark FAILED)"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
