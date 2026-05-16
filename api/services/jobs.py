"""Service + repo for ``/api/v1/jobs/*`` — Phase B v6.

Replaces ``coordinator/src/services/jobs.ts`` and ``coordinator/src/queue/repo.ts``.

Writes go through ``BT.SP_INS_QUEUE`` (per AGENTS.md). Reads use direct
``SELECT`` on ``BT.QUEUE`` (allowed for reads) for simplicity — the same
joins the coordinator's TS code performed.
"""

import logging
import uuid
from typing import Any

import redis

from api.schemas.jobs import (
    MAX_QUEUED_PER_USER,
    PRIORITY_MAP,
    EnqueueRequest,
    EnqueueResponse,
)
from quant.queue.wake import publish_wake
from quant.refdata.reader import RedisRefData
from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)

ACTIVE_TS = "9999-12-31 00:00:00+00"


class RateLimitError(Exception):
    """Per-user QUEUED rate limit exceeded — router maps to HTTP 429."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"rate_limited: at most {limit} QUEUED jobs per user")
        self.limit = limit


class JobNotFound(Exception):
    """Router maps to HTTP 404."""


class CancelNotAllowed(Exception):
    """Job is already in a terminal state — router maps to HTTP 409."""


class JobsRepo(DbGateway):
    """Reads + writes for BT.QUEUE / BT.RESULT used by the jobs router."""

    # ── reads (direct SELECT, allowed by AGENTS.md) ─────────────────────

    def count_queued_for_user(self, user_id: str, queued_status_id: int) -> int:
        rows = self._query(
            "SELECT COUNT(*)::INTEGER AS n FROM BT.QUEUE"
            " WHERE TRANSACT_TO_TS = %s::timestamptz"
            "   AND QUEUE_STATUS_ID = %s"
            "   AND USER_ID = %s",
            (ACTIVE_TS, int(queued_status_id), user_id),
        )
        return int(rows[0]["n"]) if rows else 0

    def list_for_user(self, user_id: str, limit: int = 50) -> list[dict]:
        return self._query(
            "SELECT q.QUEUE_ID, q.QUEUE_VID, q.STRATEGY_ID, q.STRATEGY_VID,"
            "       s.STRATEGY_NM,"
            "       q.QUEUE_STATUS_ID,"
            "       (SELECT NAME FROM REFDATA.QUEUE_STATUS"
            "         WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,"
            "       q.PRIORITY, q.USER_ID, q.TRANSACT_FROM_TS, q.ERROR_TEXT"
            "  FROM BT.QUEUE q"
            "  LEFT JOIN BT.STRATEGY s ON s.STRATEGY_ID = q.STRATEGY_ID"
            "                         AND s.STRATEGY_VID = q.STRATEGY_VID"
            " WHERE q.TRANSACT_TO_TS = %s::timestamptz"
            "   AND q.USER_ID = %s"
            " ORDER BY q.PRIORITY ASC, q.TRANSACT_FROM_TS ASC"
            " LIMIT %s",
            (ACTIVE_TS, user_id, int(limit)),
        )

    def queued_position(self, queue_id: uuid.UUID, queued_status_id: int) -> int:
        """1-indexed position in the QUEUED ranking (0 if not found)."""
        rows = self._query(
            "WITH ranked AS ("
            "  SELECT QUEUE_ID, ROW_NUMBER() OVER ("
            "    ORDER BY PRIORITY ASC, TRANSACT_FROM_TS ASC) AS pos"
            "    FROM BT.QUEUE"
            "   WHERE TRANSACT_TO_TS = %s::timestamptz"
            "     AND QUEUE_STATUS_ID = %s"
            ") SELECT pos FROM ranked WHERE QUEUE_ID = %s::uuid",
            (ACTIVE_TS, int(queued_status_id), str(queue_id)),
        )
        return int(rows[0]["pos"]) if rows else 0

    def get_active(self, queue_id: uuid.UUID, user_id: str | None = None) -> dict | None:
        """Active QUEUE row with status/strategy joins. Returns None if not found.

        If ``user_id`` is supplied the lookup is scoped — used by the router
        to enforce ownership without leaking 404 vs 403.
        """
        sql = (
            "SELECT q.QUEUE_ID, q.QUEUE_VID, q.STRATEGY_ID, q.STRATEGY_VID,"
            "       s.STRATEGY_NM, s.CONFIG_JSON,"
            "       q.QUEUE_STATUS_ID,"
            "       (SELECT NAME FROM REFDATA.QUEUE_STATUS"
            "         WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,"
            "       q.PRIORITY, q.USER_ID, q.TRANSACT_FROM_TS, q.ERROR_TEXT"
            "  FROM BT.QUEUE q"
            "  LEFT JOIN BT.STRATEGY s ON s.STRATEGY_ID = q.STRATEGY_ID"
            "                         AND s.STRATEGY_VID = q.STRATEGY_VID"
            " WHERE q.QUEUE_ID = %s::uuid"
            "   AND q.TRANSACT_TO_TS = %s::timestamptz"
        )
        params: tuple = (str(queue_id), ACTIVE_TS)
        if user_id is not None:
            sql += " AND q.USER_ID = %s"
            params = params + (user_id,)
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def get_result(self, queue_id: uuid.UUID) -> dict | None:
        rows = self._query(
            "SELECT RESULT_ID, RESULT_PAYLOAD"
            "  FROM BT.RESULT"
            " WHERE QUEUE_ID = %s::uuid"
            " ORDER BY CREATED_AT DESC"
            " LIMIT 1",
            (str(queue_id),),
        )
        return rows[0] if rows else None

    # ── writes (always via SP_INS_QUEUE) ────────────────────────────────

    def ins_queue(
        self,
        queue_id: uuid.UUID,
        strategy_id: uuid.UUID | str,
        strategy_vid: int,
        status_id: int,
        priority: int,
        user_id: str,
        error_text: str | None = None,
    ) -> None:
        self._call_write(
            "CALL bt.sp_ins_queue("
            "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(queue_id),
                str(strategy_id),
                int(strategy_vid),
                int(status_id),
                int(priority),
                error_text,
                user_id,
            ),
        )


class JobsService:
    """Business logic for /jobs — HTTP-agnostic."""

    def __init__(
        self,
        repo: JobsRepo,
        refdata: RedisRefData,
        redis_client: redis.Redis,
    ) -> None:
        self._repo = repo
        self._refdata = refdata
        self._redis = redis_client

    # ── helpers ─────────────────────────────────────────────────────────

    def _status(self, name: str) -> int:
        return self._refdata.resolve_queue_status_id(name)

    # ── enqueue ─────────────────────────────────────────────────────────

    def enqueue(self, user_id: str, req: EnqueueRequest) -> EnqueueResponse:
        queued_id = self._status("QUEUED")

        if self._repo.count_queued_for_user(user_id, queued_id) >= MAX_QUEUED_PER_USER:
            raise RateLimitError(MAX_QUEUED_PER_USER)

        queue_id = uuid.uuid4()
        self._repo.ins_queue(
            queue_id=queue_id,
            strategy_id=req.strategy_id,
            strategy_vid=req.strategy_vid,
            status_id=queued_id,
            priority=PRIORITY_MAP[req.priority],
            user_id=user_id,
        )
        publish_wake(self._redis)

        pos = self._repo.queued_position(queue_id, queued_id)
        return EnqueueResponse(queue_id=queue_id, queue_pos=pos)

    # ── list ────────────────────────────────────────────────────────────

    def list_for_user(self, user_id: str, limit: int = 50) -> list[dict]:
        return self._repo.list_for_user(user_id, limit=limit)

    # ── get one ─────────────────────────────────────────────────────────

    def get(self, user_id: str, queue_id: uuid.UUID) -> dict:
        row = self._repo.get_active(queue_id, user_id=user_id)
        if row is None:
            raise JobNotFound(str(queue_id))
        result = self._repo.get_result(queue_id)
        if result is not None:
            row["result"] = result.get("result_payload")
        return row

    # ── cancel ──────────────────────────────────────────────────────────

    def cancel(self, user_id: str, queue_id: uuid.UUID) -> dict:
        row = self._repo.get_active(queue_id, user_id=user_id)
        if row is None:
            raise JobNotFound(str(queue_id))

        status = row["queue_status"]
        if status == "QUEUED":
            target = self._status("CANCELLED")
        elif status == "RUNNING":
            target = self._status("CANCEL_REQUESTED")
        else:
            raise CancelNotAllowed(
                f"job {queue_id} is in terminal state {status!r}"
            )

        self._repo.ins_queue(
            queue_id=queue_id,
            strategy_id=row["strategy_id"],
            strategy_vid=row["strategy_vid"],
            status_id=target,
            priority=row["priority"],
            user_id=user_id,
            error_text=None,
        )
        # Wake the loop so it notices QUEUED→CANCELLED disappearance and
        # re-tests the queue head.
        publish_wake(self._redis)

        return self._repo.get_active(queue_id, user_id=user_id) or row

    # ── SSE polling ─────────────────────────────────────────────────────

    def snapshot_status(self, user_id: str, queue_id: uuid.UUID) -> dict | None:
        """One status sample for SSE — None if the job isn't visible to the user."""
        row = self._repo.get_active(queue_id, user_id=user_id)
        if row is None:
            return None
        return {
            "queue_id": str(row["queue_id"]),
            "queue_vid": int(row["queue_vid"]),
            "queue_status": row["queue_status"],
            "queue_status_id": int(row["queue_status_id"]),
            "error_text": row.get("error_text"),
        }


def _to_payload(row: Any) -> Any:
    return row
