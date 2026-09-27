"""HTTP boundary for the strategy catalog — ``/api/v1/strategies``.

Read-only. Returns **caller-owned** strategies only (Trade deploy path).
All routes behind ``require_user`` (registered in ``quant.api.main``).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.schemas.strategies import StrategyListRow, StrategyResult
from quant.api.services.strategies import (
    StrategiesService,
    StrategyListVersions,
    StrategyNotFound,
)
from quant.queue.repo import BtQueueRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def get_strategies_service(request: Request) -> StrategiesService:
    conninfo = request.app.state.db_conninfo
    return StrategiesService(repo=BtQueueRepo(conninfo, user_id="system"))


@router.get("", response_model=list[StrategyListRow])
def list_strategies(
    limit: int = Query(default=200, ge=1, le=1000),
    versions: StrategyListVersions = Query(
        default="best",
        description="best = IS_BEST_IND rows only; all = every VID owned by caller",
    ),
    user: CurrentUser = Depends(require_user),
    svc: StrategiesService = Depends(get_strategies_service),
) -> list[StrategyListRow]:
    rows = svc.list_strategies(
        user_id=str(user.app_user_id),
        limit=limit,
        versions=versions,
    )
    return [StrategyListRow(**r) for r in rows]


@router.get("/{strategy_id}/result", response_model=StrategyResult)
def get_strategy_result(
    strategy_id: UUID,
    strategy_vid: int = Query(..., ge=1),
    _user: CurrentUser = Depends(require_user),
    svc: StrategiesService = Depends(get_strategies_service),
) -> StrategyResult:
    """Stored backtest for one strategy version (``SP_GET_RESULT``)."""
    try:
        return StrategyResult(**svc.get_result(strategy_id, strategy_vid))
    except StrategyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
