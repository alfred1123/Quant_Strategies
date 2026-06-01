"""HTTP boundary for the promotion decision log — ``/api/v1/backtest/promotions``.

Read-only. All routes behind ``require_user`` (registered in
``quant.api.main``). Promotion records are a shared pool — not user-scoped.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.schemas.promotion import PromotionRow
from quant.api.services.promotion import PromotionService
from quant.promotion.repo import PromotionRepo
from quant.queue.repo import BtQueueRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/promotions", tags=["promotions"])


def get_promotion_service(request: Request) -> PromotionService:
    """Build a per-request ``PromotionService`` against app-wide DB conninfo."""
    conninfo = request.app.state.db_conninfo
    bt = BtQueueRepo(conninfo, user_id="system")
    return PromotionService(repo=PromotionRepo(conninfo, bt=bt))


@router.get("", response_model=list[PromotionRow])
def list_promotions(
    strategy_id: UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: CurrentUser = Depends(require_user),
    svc: PromotionService = Depends(get_promotion_service),
) -> list[PromotionRow]:
    return [
        PromotionRow(**r)
        for r in svc.list_promotions(strategy_id, limit=limit)
    ]
