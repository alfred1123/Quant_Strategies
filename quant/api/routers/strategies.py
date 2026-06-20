"""HTTP boundary for the strategy catalog — ``/api/v1/strategies``.

Read-only. Returns **caller-owned** strategies only (Trade deploy path).
All routes behind ``require_user`` (registered in ``quant.api.main``).
"""

import logging

from fastapi import APIRouter, Depends, Query, Request

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.schemas.strategies import StrategyListRow
from quant.api.services.strategies import StrategiesService, StrategyListVersions
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
