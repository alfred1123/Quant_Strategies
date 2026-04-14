"""Backtest router — POST endpoints for data, optimize, performance, walk-forward."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.schemas.backtest import (
    DataRequest, DataResponse,
    OptimizeRequest, OptimizeResponse,
    PerformanceRequest, PerformanceResponse,
    WalkForwardRequest, WalkForwardResponse,
)
from api.services import backtest as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

@router.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest, request: Request):
    try:
        return svc.run_optimize(req, request.app.state.refdata_cache)
    except Exception as exc:
        logger.exception("Optimization failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/optimize/stream")
async def optimize_stream(req: OptimizeRequest, request: Request):
    """SSE endpoint streaming per-trial progress during optimization."""
    cache = request.app.state.refdata_cache
    return StreamingResponse(
        svc.stream_optimize(req, cache),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/performance", response_model=PerformanceResponse)
def performance(req: PerformanceRequest, request: Request):
    try:
        return svc.run_performance(req, request.app.state.refdata_cache)
    except Exception as exc:
        logger.exception("Performance calculation failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/walk-forward", response_model=WalkForwardResponse)
def walk_forward(req: WalkForwardRequest, request: Request):
    try:
        return svc.run_walk_forward(req, request.app.state.refdata_cache)
    except Exception as exc:
        logger.exception("Walk-forward test failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
