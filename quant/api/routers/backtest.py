"""Backtest router — POST endpoints for data, optimize, performance, walk-forward."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from quant.api.deps import get_data_caches
from quant.refdata.bundle import DataCaches
from quant.schemas.backtest import (
    OptimizeRequest,
    OptimizeResponse,
    PerformanceRequest,
    PerformanceResponse,
    WalkForwardRequest,
    WalkForwardResponse,
)
from quant.strategy.backtest_service import (
    BacktestError,
    run_optimize,
    run_performance,
    run_walk_forward,
    stream_optimize,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BacktestError):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/optimize", response_model=OptimizeResponse)
def optimize(
    req: OptimizeRequest,
    request: Request,
    caches: DataCaches = Depends(get_data_caches),
):
    try:
        return run_optimize(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
            bar_services=request.app.state.price_bars,
        )
    except Exception as exc:
        logger.exception("Optimization failed")
        raise _http_error(exc) from exc


@router.post("/optimize/stream")
async def optimize_stream(
    req: OptimizeRequest,
    request: Request,
    caches: DataCaches = Depends(get_data_caches),
):
    """SSE endpoint streaming per-trial progress during optimization."""
    return StreamingResponse(
        stream_optimize(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
            bar_services=request.app.state.price_bars,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/performance", response_model=PerformanceResponse)
def performance(
    req: PerformanceRequest,
    request: Request,
    caches: DataCaches = Depends(get_data_caches),
):
    try:
        return run_performance(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
            bar_services=request.app.state.price_bars,
        )
    except Exception as exc:
        logger.exception("Performance calculation failed")
        raise _http_error(exc) from exc


@router.post("/walk-forward", response_model=WalkForwardResponse)
def walk_forward(
    req: WalkForwardRequest,
    request: Request,
    caches: DataCaches = Depends(get_data_caches),
):
    try:
        return run_walk_forward(
            req,
            caches.refdata,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
            bar_services=request.app.state.price_bars,
        )
    except Exception as exc:
        logger.exception("Walk-forward test failed")
        raise _http_error(exc) from exc
