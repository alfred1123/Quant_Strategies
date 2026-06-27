"""HTTP boundary for trade deployments — Phase 1.2.

Routes under ``/api/v1/trade/deployments/*``. All routes behind
``require_user`` (registered in ``quant.api.main``).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.queue.repo import BtQueueRepo
from quant.schemas.deployments import CreateDeploymentRequest, DeploymentRow
from quant.trade.db_repo import TradeRepo
from quant.trade.service import DeploymentNotFound, TradeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trade", tags=["trade"])


def get_trade_service(request: Request) -> TradeService:
    """Build a per-request ``TradeService`` against app-wide DB conninfo."""
    conninfo = request.app.state.db_conninfo
    bt = BtQueueRepo(conninfo, user_id="system")
    repo = TradeRepo(conninfo, bt=bt, user_id="system")
    return TradeService(repo=repo)


@router.post(
    "/deployments",
    response_model=DeploymentRow,
    status_code=status.HTTP_201_CREATED,
)
def create_deployment(
    req: CreateDeploymentRequest,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> DeploymentRow:
    return svc.create_deployment(user.app_user_id, str(user.app_user_id), req)


@router.get("/deployments", response_model=list[DeploymentRow])
def list_deployments(
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> list[DeploymentRow]:
    return svc.list_deployments(user.app_user_id)


@router.get("/deployments/{deployment_id}", response_model=DeploymentRow)
def get_deployment(
    deployment_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> DeploymentRow:
    try:
        return svc.get_deployment(user.app_user_id, deployment_id)
    except DeploymentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
