"""Trade deployment business logic — shared by API and workers."""

import logging
import uuid
from uuid import UUID

from quant.schemas.deployments import CreateDeploymentRequest, DeploymentRow
from quant.trade.db_repo import TradeRepo

logger = logging.getLogger(__name__)


class DeploymentNotFound(Exception):
    """HTTP layer maps to 404."""


class TradeService:
    """Deployment apply/status — HTTP-agnostic."""

    def __init__(self, repo: TradeRepo) -> None:
        self._repo = repo

    def create_deployment(
        self,
        app_user_id: UUID,
        user_id: str,
        req: CreateDeploymentRequest,
    ) -> DeploymentRow:
        deployment_id = req.deployment_id or uuid.uuid4()
        row = self._repo.sp_ins_deployment(
            deployment_id=deployment_id,
            app_user_id=app_user_id,
            strategy_id=req.strategy_id,
            strategy_vid=req.strategy_vid,
            api_credential_id=req.api_credential_id,
            app_id=req.app_id,
            internal_cusip=req.internal_cusip,
            qty=req.qty,
            is_paper_ind="Y" if req.paper else "N",
            is_enabled_ind="Y" if req.enabled else "N",
            deployment_status=req.deployment_status,
            user_id=user_id,
        )
        return DeploymentRow.model_validate(row)

    def get_deployment(
        self, app_user_id: UUID, deployment_id: UUID
    ) -> DeploymentRow:
        rows = self._repo.sp_get_deployment(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
        )
        if not rows:
            raise DeploymentNotFound(str(deployment_id))
        return DeploymentRow.model_validate(rows[0])

    def list_deployments(self, app_user_id: UUID) -> list[DeploymentRow]:
        rows = self._repo.sp_get_deployment(app_user_id=app_user_id)
        return [DeploymentRow.model_validate(r) for r in rows]
