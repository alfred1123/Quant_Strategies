"""Trade deployment business logic — shared by API and workers."""

import logging
import uuid
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches
from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import (
    CreateDeploymentRequest,
    DeploymentRow,
    DeploymentStatus,
    UpdateDeploymentRequest,
)
from quant.schemas.dry_run import DryRunReport, DryRunRequest
from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.db_repo import TradeRepo
from quant.trade.dry_run import run_dry_run
from quant.trade.errors import DeploymentNotFound, TradeValidationError
from quant.trade.live_apply import LiveApplyOrchestrator
from quant.trade.registry import AdapterRegistry

logger = logging.getLogger(__name__)


class TradeService:
    """Deployment apply/status — HTTP-agnostic."""

    def __init__(
        self,
        repo: TradeRepo,
        bt: BtQueueRepo,
        credential_service: CredentialService,
        credential_repo: ApiCredentialRepo,
        adapter_registry: AdapterRegistry,
        data_caches: DataCaches,
        price_bars: PriceBarServiceFactory | None = None,
    ) -> None:
        self._repo = repo
        self._bt = bt
        self._credential_service = credential_service
        self._credential_repo = credential_repo
        self._adapter_registry = adapter_registry
        self._data_caches = data_caches
        self._live_apply = LiveApplyOrchestrator(
            repo,
            bt,
            credential_service,
            credential_repo,
            adapter_registry,
            data_caches,
            price_bars=price_bars,
        )

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
            confirm_live=req.confirm_live,
            schedule_tm_interval_id=req.schedule_tm_interval_id,
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

    def update_deployment(
        self,
        app_user_id: UUID,
        deployment_id: UUID,
        req: UpdateDeploymentRequest,
    ) -> DeploymentRow:
        current = self.get_deployment(app_user_id, deployment_id)
        row = self._repo.write_deployment(
            deployment_id=deployment_id,
            app_user_id=app_user_id,
            strategy_id=current.strategy_id,
            strategy_vid=current.strategy_vid,
            api_credential_id=current.api_credential_id,
            app_id=current.app_id,
            internal_cusip=current.internal_cusip,
            qty=current.qty,
            is_paper_ind=current.is_paper_ind,
            is_enabled_ind=(
                ("Y" if req.enabled else "N")
                if req.enabled is not None
                else current.is_enabled_ind
            ),
            deployment_status=req.deployment_status or current.deployment_status,
            user_id=str(app_user_id),
            schedule_tm_interval_id=(
                req.schedule_tm_interval_id
                if "schedule_tm_interval_id" in req.model_fields_set
                else current.schedule_tm_interval_id
            ),
        )
        return DeploymentRow.model_validate(row)

    def stop_deployment(
        self, app_user_id: UUID, deployment_id: UUID
    ) -> DeploymentRow:
        """Stop a deployment — disables it and sets status to STOPPED.

        Idempotent: stopping an already-stopped deployment is a no-op.
        """
        current = self.get_deployment(app_user_id, deployment_id)
        if current.deployment_status == DeploymentStatus.STOPPED:
            return current
        row = self._repo.write_deployment(
            deployment_id=deployment_id,
            app_user_id=app_user_id,
            strategy_id=current.strategy_id,
            strategy_vid=current.strategy_vid,
            api_credential_id=current.api_credential_id,
            app_id=current.app_id,
            internal_cusip=current.internal_cusip,
            qty=current.qty,
            is_paper_ind=current.is_paper_ind,
            is_enabled_ind="N",
            deployment_status=DeploymentStatus.STOPPED,
            user_id=str(app_user_id),
            schedule_tm_interval_id=current.schedule_tm_interval_id,
        )
        logger.info("Deployment %s stopped by user %s", deployment_id, app_user_id)
        return DeploymentRow.model_validate(row)

    def apply_deployment(
        self, app_user_id: UUID, deployment_id: UUID
    ) -> ApplyReport:
        dep = self.get_deployment(app_user_id, deployment_id)
        if dep.is_enabled_ind != "Y":
            raise TradeValidationError(
                "deployment is disabled (kill switch)", status_code=400
            )
        return self._live_apply.run(
            app_user_id,
            dep,
            str(app_user_id),
        )

    def dry_run(
        self,
        app_user_id: UUID,
        req: DryRunRequest,
    ) -> DryRunReport:
        return run_dry_run(
            app_user_id=app_user_id,
            req=req,
            repo=self._repo,
            bt=self._bt,
            credential_service=self._credential_service,
            credential_repo=self._credential_repo,
            adapter_registry=self._adapter_registry,
            data_caches=self._data_caches,
        )
