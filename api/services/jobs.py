"""Service for ``/api/v1/jobs/*`` — Phase B v6.

Replaces ``coordinator/src/services/jobs.ts``. All DB access is delegated
to :class:`quant.queue.repo.BtQueueRepo`; this module is HTTP-agnostic
business logic only.
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
from quant.queue.repo import BtQueueRepo
from quant.queue.wake import publish_wake
from quant.refdata.reader import RedisRefData

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Per-user QUEUED rate limit exceeded — router maps to HTTP 429."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"rate_limited: at most {limit} QUEUED jobs per user")
        self.limit = limit


class JobNotFound(Exception):
    """Router maps to HTTP 404."""


class CancelNotAllowed(Exception):
    """Job is already in a terminal state — router maps to HTTP 409."""


class ReenqueueNotAllowed(Exception):
    """Only FAILED / CANCELLED jobs may be re-enqueued — router maps to HTTP 409."""


class JobsService:
    """Business logic for /jobs — HTTP-agnostic."""

    def __init__(
        self,
        repo: BtQueueRepo,
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

        # Persist a frozen BT.STRATEGY snapshot first — SP_INS_QUEUE refs
        # the exact (strategy_id, strategy_vid) so worker payloads can't
        # be mutated mid-flight.
        strategy_id = uuid.uuid4()
        strategy_vid = self._repo.sp_ins_strategy(
            strategy_id=strategy_id,
            strategy_nm=req.strategy_nm,
            config_json=req.config_json,
            user_id=user_id,
        )

        queue_id = uuid.uuid4()
        self._repo.sp_ins_queue(
            queue_id=queue_id,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
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
            row["result"] = result.get("payload_json")
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

        self._repo.sp_ins_queue(
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

    # ── reenqueue ───────────────────────────────────────────────────────

    def reenqueue(self, user_id: str, queue_id: uuid.UUID) -> EnqueueResponse:
        """Submit a fresh QUEUE row for a FAILED / CANCELLED job.

        Same ``(STRATEGY_ID, STRATEGY_VID, PRIORITY)`` as the source row;
        new ``QUEUE_ID`` with ``QUEUE_VID=1``. Per-user QUEUED cap still
        applies — RateLimitError → 429.
        """
        row = self._repo.get_active(queue_id, user_id=user_id)
        if row is None:
            raise JobNotFound(str(queue_id))

        status = row["queue_status"]
        if status not in {"FAILED", "CANCELLED"}:
            raise ReenqueueNotAllowed(
                f"job {queue_id} cannot be re-enqueued from state {status!r}"
            )

        queued_id = self._status("QUEUED")
        if self._repo.count_queued_for_user(user_id, queued_id) >= MAX_QUEUED_PER_USER:
            raise RateLimitError(MAX_QUEUED_PER_USER)

        new_queue_id = uuid.uuid4()
        self._repo.sp_ins_queue(
            queue_id=new_queue_id,
            strategy_id=row["strategy_id"],
            strategy_vid=int(row["strategy_vid"]),
            status_id=queued_id,
            priority=int(row["priority"]),
            user_id=user_id,
        )
        publish_wake(self._redis)

        pos = self._repo.queued_position(new_queue_id, queued_id)
        return EnqueueResponse(queue_id=new_queue_id, queue_pos=pos)

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
