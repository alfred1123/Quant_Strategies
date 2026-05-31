"""Pydantic schemas for ``/api/v1/backtest/jobs/*`` — Phase B v6.

Mirrors ``coordinator/src/types/queue.ts`` so the frontend contract is
preserved when the coordinator is deleted in Phase D.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Frontend label → DB priority integer (lower = runs first).
PRIORITY_MAP: dict[str, int] = {"normal": 100, "high": 0}

# Max active QUEUED jobs per user before POST returns 429.
MAX_QUEUED_PER_USER = 30

PriorityLabel = Literal["normal", "high"]


class EnqueueRequest(BaseModel):
    """Inline-strategy enqueue: server creates BT.STRATEGY then enqueues."""

    strategy_nm: str = Field(..., min_length=1, max_length=200)
    config_json: dict[str, Any]
    priority: PriorityLabel = "normal"


class EnqueueResponse(BaseModel):
    queue_id: UUID
    queue_pos: int


class PromoteRequest(BaseModel):
    """Promote a specific VID to IS_BEST_IND = 'Y'."""

    strategy_vid: int


class JobRow(BaseModel):
    """One active or terminal BT.QUEUE row, joined to status name + strategy name."""

    queue_id: UUID
    queue_vid: int
    strategy_id: UUID
    strategy_vid: int
    strategy_nm: str | None = None
    is_best_ind: str | None = None
    queue_status_id: int
    queue_status: str
    priority: int
    user_id: str
    transact_from_ts: datetime
    error_text: str | None = None


class JobDetail(JobRow):
    """Single-job lookup — adds optional linked BT.RESULT payload."""

    config_json: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
