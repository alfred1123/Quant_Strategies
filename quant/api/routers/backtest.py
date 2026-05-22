"""Backtest router — POST endpoints for data, optimize, performance, walk-forward."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from quant.api.deps import get_data_caches
from quant.api.schemas.backtest import (
    OptimizeRequest, OptimizeResponse,
    PerformanceRequest, PerformanceResponse,
    WalkForwardRequest, WalkForwardResponse,
)
from quant.api.services import backtest as svc
from quant.refdata.bundle import DataCaches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

@router.post("/optimize", response_model=OptimizeResponse)
def optimize(
    req: OptimizeRequest,
    caches: DataCaches = Depends(get_data_caches),
):
    try:
        return svc.run_optimize(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
        )
    except Exception as exc:
        logger.exception("Optimization failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/optimize/stream")
async def optimize_stream(
    req: OptimizeRequest,
    caches: DataCaches = Depends(get_data_caches),
):
    """SSE endpoint streaming per-trial progress during optimization."""
    return StreamingResponse(
        svc.stream_optimize(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/performance", response_model=PerformanceResponse)
def performance(
    req: PerformanceRequest,
    caches: DataCaches = Depends(get_data_caches),
):
    try:
        return svc.run_performance(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
        )
    except Exception as exc:
        logger.exception("Performance calculation failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/walk-forward", response_model=WalkForwardResponse)
def walk_forward(
    req: WalkForwardRequest,
    caches: DataCaches = Depends(get_data_caches),
):
    try:
        return svc.run_walk_forward(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
        )
    except Exception as exc:
        logger.exception("Walk-forward test failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
