"""HTTP boundary for the backtest job queue — Phase B v6.

Replaces the TS coordinator's ``/api/v1/jobs/*`` endpoints. All routes
behind ``require_user`` (registered in ``quant.api.main``).
"""

import asyncio
import json
import logging
from uuid import UUID

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.shared.config import get_redis_url
from quant.api.deps import get_data_caches
from quant.api.schemas.jobs import EnqueueRequest, EnqueueResponse, JobDetail, JobRow
from quant.api.services.jobs import (
    CancelNotAllowed,
    JobNotFound,
    JobsService,
    RateLimitError,
    ReenqueueNotAllowed,
)
from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

# SSE polling cadence — see docs/design/backtest-queue.md §0 Phase B.
SSE_POLL_INTERVAL_S = 1.0


def get_jobs_service(
    request: Request,
    caches: DataCaches = Depends(get_data_caches),
) -> JobsService:
    """Build a per-request ``JobsService`` against app-wide DB + Redis."""
    repo = BtQueueRepo(request.app.state.db_conninfo, user_id="system")
    return JobsService(repo=repo, refdata=caches.refdata, redis_client=_get_redis(request))


def _get_redis(request: Request) -> redis_lib.Redis:
    """Reuse the app-wide Redis client from ``app.state`` if present, else build one."""
    client = getattr(request.app.state, "redis_client", None)
    if client is None:
        client = redis_lib.Redis.from_url(get_redis_url())
        request.app.state.redis_client = client
    return client


# ── POST /jobs ──────────────────────────────────────────────────────────


@router.post("", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue(
    req: EnqueueRequest,
    user: CurrentUser = Depends(require_user),
    svc: JobsService = Depends(get_jobs_service),
) -> EnqueueResponse:
    try:
        return svc.enqueue(str(user.app_user_id), req)
    except RateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


# ── GET /jobs ───────────────────────────────────────────────────────────


@router.get("", response_model=list[JobRow])
def list_jobs(
    user: CurrentUser = Depends(require_user),
    svc: JobsService = Depends(get_jobs_service),
) -> list[JobRow]:
    return [JobRow(**r) for r in svc.list_for_user(str(user.app_user_id))]


# ── GET /jobs/{id} ──────────────────────────────────────────────────────


@router.get("/{queue_id}", response_model=JobDetail)
def get_job(
    queue_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: JobsService = Depends(get_jobs_service),
) -> JobDetail:
    try:
        return JobDetail(**svc.get(str(user.app_user_id), queue_id))
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /jobs/{id}/cancel ──────────────────────────────────────────────


@router.post("/{queue_id}/cancel", response_model=JobRow)
def cancel_job(
    queue_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: JobsService = Depends(get_jobs_service),
) -> JobRow:
    try:
        row = svc.cancel(str(user.app_user_id), queue_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CancelNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JobRow(**row)


# ── POST /jobs/{id}/reenqueue ───────────────────────────────────────────


@router.post(
    "/{queue_id}/reenqueue",
    response_model=EnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reenqueue_job(
    queue_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: JobsService = Depends(get_jobs_service),
) -> EnqueueResponse:
    """Submit a new QUEUE row reusing the original strategy + priority.

    Allowed only when the source job is FAILED or CANCELLED. Per-user
    QUEUED cap still applies — returns 429 when exceeded.
    """
    try:
        return svc.reenqueue(str(user.app_user_id), queue_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ReenqueueNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


# ── GET /jobs/{id}/events (SSE) ─────────────────────────────────────────


@router.get("/{queue_id}/events")
async def stream_events(
    queue_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: JobsService = Depends(get_jobs_service),
) -> StreamingResponse:
    """SSE — emits a status event whenever ``QUEUE_STATUS`` changes.

    Polls ``BT.QUEUE`` every ``SSE_POLL_INTERVAL_S`` seconds. Closes when
    the row reaches a terminal state (COMPLETED / FAILED / CANCELLED).
    """
    user_id = str(user.app_user_id)
    terminal = {"COMPLETED", "FAILED", "CANCELLED"}

    async def gen():
        last_vid = -1
        while True:
            snap = svc.snapshot_status(user_id, queue_id)
            if snap is None:
                # Job vanished or unauthorized — emit close marker and stop.
                yield "event: error\ndata: " + json.dumps({"detail": "not_found"}) + "\n\n"
                return
            if snap["queue_vid"] != last_vid:
                last_vid = snap["queue_vid"]
                yield "event: status\ndata: " + json.dumps(snap) + "\n\n"
            if snap["queue_status"] in terminal:
                return
            await asyncio.sleep(SSE_POLL_INTERVAL_S)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
