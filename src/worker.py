"""Backtest worker — Slice C minimum (no progress, no cancel, no timeout).

Invocation:
    python -m src.worker <queue_id>

See docs/design/backtest-queue.md §10 for the full contract. This Slice C
implementation covers steps 1-4 + 7 + 9 + 11-12 only:

    1. Parse queue_id from argv.
    2. Connect to DB via DB_URL env var.
    3. Read CONFIG_JSON for the strategy version snapshot in BT.QUEUE.
    4. Reconstruct OptimizeRequest, run optimization to completion.
    7. Emit `started` JSON on stdout.
    9. INSERT BT.RESULT, then SP_INS_QUEUE → COMPLETED.
   11. On any uncaught error → SP_INS_QUEUE → FAILED with traceback.
   12. Emit `terminal` JSON, exit 0.

Slice D adds: per-trial progress, signal-based cancel, deadline.

Exit codes (per §10.1):
    0 — terminal state written to DB (COMPLETED, FAILED, or CANCELLED).
    1 — uncaught crash before the FAILED row could be written.
    2 — config error (bad argv, missing env, queue row not found, bad JSON).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone

import psycopg

# Imports below are relative to src/ — keep module runnable as `python -m src.worker`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import BacktestCache, InstrumentCache, RefDataCache  # noqa: E402

# api/services/backtest.py owns the optimize-from-request glue (data fetch,
# config build, parameter ranges). Reusing it keeps the worker behaviour
# in lockstep with the synchronous /optimize endpoint.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from api.schemas.backtest import OptimizeRequest  # noqa: E402
from api.services.backtest import run_optimize  # noqa: E402

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event: dict) -> None:
    """Write one newline-delimited JSON event to stdout (§10.3)."""
    print(json.dumps(event), flush=True)


def _fetch_job(conn: psycopg.Connection, queue_id: uuid.UUID) -> dict:
    """Read the active QUEUE row + its frozen STRATEGY snapshot.

    Joins on (strategy_id, strategy_vid) so the worker sees the exact
    config that was submitted, even if the strategy has since been
    edited (design §6).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT q.strategy_id, q.strategy_vid, q.priority, q.user_id,
                   s.config_json
              FROM bt.queue q
              JOIN bt.strategy s
                ON s.strategy_id  = q.strategy_id
               AND s.strategy_vid = q.strategy_vid
             WHERE q.queue_id       = %s::uuid
               AND q.transact_to_ts = TIMESTAMPTZ '9999-12-31'
             LIMIT 1
            """,
            (str(queue_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"no active BT.QUEUE row for queue_id={queue_id}")
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def _resolve_status_id(refdata: RefDataCache, name: str) -> int:
    for r in refdata.get("queue_status"):
        if r["name"] == name:
            return int(r["queue_status_id"])
    raise RuntimeError(f"REFDATA.QUEUE_STATUS missing NAME={name!r}")


def _call_proc_write(conn: psycopg.Connection, sql: str, params: tuple) -> tuple:
    """Run a CALL ... ; raise on non-00000 SQLSTATE; commit on success.

    Returns the OUT-row tuple so callers needing extra OUT params
    (e.g. OUT_RESULT_ID from SP_INS_RESULT) can extract them.
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        out = cur.fetchone()
        sqlstate = out[-3]  # OUT_SQLSTATE is third-from-last across our procs
        if sqlstate != "00000":
            sqlerrmc = out[-1]
            raise RuntimeError(f"proc failed (SQLSTATE {sqlstate}): {sqlerrmc}")
    conn.commit()
    return out


def _ins_queue(
    conn: psycopg.Connection,
    queue_id: uuid.UUID,
    job: dict,
    status_id: int,
    error_text: str | None,
) -> None:
    _call_proc_write(
        conn,
        "CALL bt.sp_ins_queue("
        "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer, %s::text, %s::text,"
        " NULL::text, NULL::text, NULL::text)",
        (
            str(queue_id),
            str(job["strategy_id"]),
            int(job["strategy_vid"]),
            status_id,
            int(job["priority"]),
            error_text,
            job["user_id"],
        ),
    )


def _ins_result(
    conn: psycopg.Connection,
    queue_id: uuid.UUID,
    payload: dict,
    user_id: str,
) -> int:
    out = _call_proc_write(
        conn,
        "CALL bt.sp_ins_result("
        "%s::uuid, %s::jsonb, %s::text, NULL::integer, NULL::text, NULL::text, NULL::text)",
        (str(queue_id), json.dumps(payload, default=str), user_id),
    )
    # SP_INS_RESULT OUT order: OUT_RESULT_ID, OUT_SQLSTATE, OUT_SQLMSG, OUT_SQLERRMC
    return int(out[0])


def _run(queue_id: uuid.UUID, db_url: str) -> int:
    """Main worker flow. Returns the process exit code."""
    refdata = RefDataCache(db_url)
    refdata.load_all()
    inst = InstrumentCache(db_url)
    try:
        inst.load_all()
    except Exception:
        logger.warning("InstrumentCache load failed — proceeding without it", exc_info=True)
    bt_cache = BacktestCache(db_url, refdata=refdata)

    completed_id = _resolve_status_id(refdata, "COMPLETED")
    failed_id    = _resolve_status_id(refdata, "FAILED")

    # Single connection for queue/result writes — DB_URL is the conninfo.
    conn = psycopg.connect(db_url)
    try:
        job = _fetch_job(conn, queue_id)

        _emit({"type": "started", "queue_id": str(queue_id), "ts": _iso_now()})

        try:
            req = OptimizeRequest.model_validate(job["config_json"])
        except Exception as exc:  # bad CONFIG_JSON shape — config error
            raise ValueError(f"CONFIG_JSON failed OptimizeRequest validation: {exc}") from exc

        try:
            response = run_optimize(req, refdata, inst_cache=inst, bt_cache=bt_cache)
        except Exception:
            err = traceback.format_exc()
            logger.error("optimize failed for queue_id=%s\n%s", queue_id, err)
            _ins_queue(conn, queue_id, job, failed_id, err)
            _emit({
                "type": "terminal", "queue_id": str(queue_id),
                "status": "FAILED", "ts": _iso_now(),
            })
            return 0  # FAILED row written → clean exit per §10.1.

        result_id = _ins_result(conn, queue_id, response.model_dump(), job["user_id"])
        _ins_queue(conn, queue_id, job, completed_id, None)
        _emit({
            "type": "terminal", "queue_id": str(queue_id),
            "status": "COMPLETED", "result_id": result_id, "ts": _iso_now(),
        })
        return 0
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )

    if len(argv) != 2:
        print("usage: python -m src.worker <queue_id>", file=sys.stderr)
        return 2
    try:
        queue_id = uuid.UUID(argv[1])
    except ValueError:
        print(f"invalid queue_id (not a UUID): {argv[1]!r}", file=sys.stderr)
        return 2

    db_url = os.environ.get("DB_URL")
    if not db_url:
        print("DB_URL env var is required", file=sys.stderr)
        return 2

    try:
        return _run(queue_id, db_url)
    except LookupError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except Exception:
        # Last-resort: we couldn't even write FAILED. Exit 1 so the
        # coordinator's reaper writes FAILED on our behalf (Slice D).
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
