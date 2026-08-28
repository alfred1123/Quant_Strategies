"""HTTP boundary for trade deployments — Phase 1.2.

Routes under ``/api/v1/trade/deployments/*``. All routes behind
``require_user`` (registered in ``quant.api.main``).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.credentials.repo import ApiCredentialRepo
from quant.queue.repo import BtQueueRepo
from quant.schemas.account import AccountSnapshot
from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import (
    CreateDeploymentRequest,
    DeploymentRow,
    UpdateDeploymentRequest,
)
from quant.schemas.dry_run import DryRunReport, DryRunRequest
from quant.trade.db_repo import TradeRepo
from quant.trade.service import TradeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trade", tags=["trade"])


def build_trade_service(state) -> TradeService:
    """A fresh ``TradeService`` over the singletons on app state.

    Takes the state rather than the request because the scheduler tick builds
    one per apply too, and it has no request to build it from.
    """
    conninfo = state.db_conninfo
    bt = BtQueueRepo(conninfo, user_id="system")
    repo = TradeRepo(conninfo, bt=bt, user_id="system")
    return TradeService(
        repo=repo,
        bt=bt,
        credential_service=state.credential_service,
        credential_repo=ApiCredentialRepo(conninfo, user_id="system"),
        adapter_registry=state.adapter_registry,
        data_caches=state.data_caches,
        price_bars=state.price_bars,
    )


def get_trade_service(request: Request) -> TradeService:
    """Build a per-request ``TradeService`` with all deps from app state."""
    return build_trade_service(request.app.state)


@router.post("/deployments/dry-run", response_model=DryRunReport)
def dry_run_deployment(
    req: DryRunRequest,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> DryRunReport:
    return svc.dry_run(user.app_user_id, req)


@router.get(
    "/accounts/{api_credential_id}/snapshot",
    response_model=AccountSnapshot,
)
def account_snapshot(
    api_credential_id: int,
    paper: bool = True,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> AccountSnapshot:
    """Live balances and open positions for one broker account.

    Read-only — reaches the exchange but places nothing. ``paper`` defaults to
    the safe environment: a caller that omits it gets the demo account, never a
    real one. Not cached server-side; every call is a rate-limited exchange
    round-trip, so the client decides how often to ask.
    """
    return svc.account_snapshot(user.app_user_id, api_credential_id, paper=paper)


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
    return svc.get_deployment(user.app_user_id, deployment_id)


@router.patch("/deployments/{deployment_id}", response_model=DeploymentRow)
def update_deployment(
    deployment_id: UUID,
    req: UpdateDeploymentRequest,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> DeploymentRow:
    return svc.update_deployment(user.app_user_id, deployment_id, req)


@router.post(
    "/deployments/{deployment_id}/stop",
    response_model=DeploymentRow,
)
def stop_deployment(
    deployment_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> DeploymentRow:
    return svc.stop_deployment(user.app_user_id, deployment_id)


@router.post(
    "/deployments/{deployment_id}/apply",
    response_model=ApplyReport,
)
def apply_deployment(
    deployment_id: UUID,
    user: CurrentUser = Depends(require_user),
    svc: TradeService = Depends(get_trade_service),
) -> ApplyReport:
    return svc.apply_deployment(user.app_user_id, deployment_id)
