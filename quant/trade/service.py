"""Trade deployment business logic — shared by API and workers."""

import logging
import uuid
from decimal import Decimal
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches
from quant.schemas.account import AccountSnapshot
from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import (
    CreateDeploymentRequest,
    DeploymentRow,
    DeploymentStatus,
    ScheduleOptions,
    UpdateDeploymentRequest,
)
from quant.schemas.dry_run import DryRunReport, DryRunRequest
from quant.schemas.execution import ExecutionEventRow, TransactionRow
from quant.trade.account import fetch_account_snapshot
from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.db_repo import TradeRepo
from quant.trade.dry_run import run_dry_run
from quant.trade.errors import DeploymentNotFound, TradeValidationError
from quant.trade.live_apply import LiveApplyOrchestrator
from quant.trade.models.market import MarketLimits
from quant.trade.registry import AdapterRegistry
from quant.trade.schedule_align import compute_initial_scheduled_ts, should_realign_schedule
from quant.trade.schedule_policy import require_fitted_interval, schedulable_interval_ids

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
        self._price_bars = price_bars
        self._live_apply = LiveApplyOrchestrator(
            repo,
            bt,
            credential_service,
            credential_repo,
            adapter_registry,
            data_caches,
            price_bars=price_bars,
        )

    def _venue_limits(self, app_id: int, internal_cusip: str) -> MarketLimits:
        """What the venue will accept for this instrument, as last cached.

        Empty limits when the symbol has no xref or nothing is cached, so an
        instrument the venue does not list is refused by the dry run (which asks
        the broker directly) rather than here.
        """
        vendor_symbol = self._data_caches.instrument_cache.resolve_internal_cusip(
            internal_cusip, app_id
        )
        if vendor_symbol is None:
            return MarketLimits(symbol=internal_cusip)
        return self._data_caches.venue_limits.get(app_id, vendor_symbol)

    def _require_tradable_qty(
        self, *, app_id: int, internal_cusip: str, qty: Decimal
    ) -> None:
        """Refuse a quantity the venue would never fill.

        Enforced here as well as before submitting because this is the moment a
        person can still fix it; at order time the only remaining move is to
        pause the deployment. The notional rule needs a live price, so it stays
        an order-time check — this is the lot size.
        """
        undersized = self._venue_limits(app_id, internal_cusip).undersized(float(qty))
        if undersized is not None:
            raise TradeValidationError(undersized)

    def _row(self, raw: dict) -> DeploymentRow:
        """A DEPLOYMENT row plus the venue's lot size for its instrument.

        ``min_qty`` is not stored — it is the exchange's rule, carried on the row
        so the qty editor can refuse a value the API would refuse anyway instead
        of discovering it on the next tick.
        """
        row = DeploymentRow.model_validate(raw)
        limits = self._venue_limits(row.app_id, row.internal_cusip)
        return row.model_copy(update={"min_qty": limits.min_qty})

    def create_deployment(
        self,
        app_user_id: UUID,
        user_id: str,
        req: CreateDeploymentRequest,
    ) -> DeploymentRow:
        require_fitted_interval(
            req.schedule_tm_interval_id, refdata=self._data_caches.refdata
        )
        self._require_tradable_qty(
            app_id=req.app_id, internal_cusip=req.internal_cusip, qty=req.qty
        )
        deployment_id = req.deployment_id or uuid.uuid4()
        initial_ts = None
        if req.schedule_tm_interval_id is not None:
            initial_ts = compute_initial_scheduled_ts(
                refdata=self._data_caches.refdata,
                app_id=req.app_id,
                schedule_tm_interval_id=req.schedule_tm_interval_id,
            )
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
            initial_scheduled_ts=initial_ts,
        )
        return self._row(row)

    def schedule_options(self) -> ScheduleOptions:
        """Cadences the schedule control may offer."""
        return ScheduleOptions(
            tm_interval_ids=schedulable_interval_ids(self._data_caches.refdata)
        )

    def get_deployment(
        self, app_user_id: UUID, deployment_id: UUID
    ) -> DeploymentRow:
        rows = self._repo.sp_get_deployment(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
        )
        if not rows:
            raise DeploymentNotFound(str(deployment_id))
        return self._row(rows[0])

    def list_deployments(self, app_user_id: UUID) -> list[DeploymentRow]:
        rows = self._repo.sp_get_deployment(app_user_id=app_user_id)
        return [self._row(r) for r in rows]

    def update_deployment(
        self,
        app_user_id: UUID,
        deployment_id: UUID,
        req: UpdateDeploymentRequest,
    ) -> DeploymentRow:
        current = self.get_deployment(app_user_id, deployment_id)
        # Only what the caller is setting, never the value already stored: a
        # row whose cadence predates this rule must still be reachable by the
        # kill switch, and refusing the PATCH would be refusing to disable it.
        if "schedule_tm_interval_id" in req.model_fields_set:
            require_fitted_interval(
                req.schedule_tm_interval_id, refdata=self._data_caches.refdata
            )
        schedule_tm_interval_id = (
            req.schedule_tm_interval_id
            if "schedule_tm_interval_id" in req.model_fields_set
            else current.schedule_tm_interval_id
        )
        if "qty" in req.model_fields_set:
            if req.qty is None:
                raise TradeValidationError("qty must be greater than 0")
            self._require_tradable_qty(
                app_id=current.app_id,
                internal_cusip=current.internal_cusip,
                qty=req.qty,
            )
            qty = req.qty
        else:
            qty = current.qty
        initial_ts = None
        if should_realign_schedule(current, req) and schedule_tm_interval_id is not None:
            initial_ts = compute_initial_scheduled_ts(
                refdata=self._data_caches.refdata,
                app_id=current.app_id,
                schedule_tm_interval_id=schedule_tm_interval_id,
            )
        row = self._repo.write_deployment(
            deployment_id=deployment_id,
            app_user_id=app_user_id,
            strategy_id=current.strategy_id,
            strategy_vid=current.strategy_vid,
            api_credential_id=current.api_credential_id,
            app_id=current.app_id,
            internal_cusip=current.internal_cusip,
            qty=qty,
            is_paper_ind=current.is_paper_ind,
            is_enabled_ind=(
                ("Y" if req.enabled else "N")
                if req.enabled is not None
                else current.is_enabled_ind
            ),
            deployment_status=req.deployment_status or current.deployment_status,
            user_id=str(app_user_id),
            schedule_tm_interval_id=schedule_tm_interval_id,
            initial_scheduled_ts=initial_ts,
        )
        return self._row(row)

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
        return self._row(row)

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
            price_bars=self._price_bars,
        )

    def account_snapshot(
        self,
        app_user_id: UUID,
        api_credential_id: int,
        *,
        paper: bool,
    ) -> AccountSnapshot:
        """Balances and open positions as the broker reports them right now."""
        return fetch_account_snapshot(
            app_user_id=app_user_id,
            api_credential_id=api_credential_id,
            paper=paper,
            credential_service=self._credential_service,
            credential_repo=self._credential_repo,
            adapter_registry=self._adapter_registry,
            data_caches=self._data_caches,
        )

    def list_execution_events(
        self,
        app_user_id: UUID,
        *,
        deployment_id: UUID | None = None,
        limit: int = 50,
    ) -> list[ExecutionEventRow]:
        if deployment_id is not None:
            self.get_deployment(app_user_id, deployment_id)
        rows = self._repo.sp_get_execution_event(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
            limit=limit,
        )
        return [ExecutionEventRow.model_validate(r) for r in rows]

    def list_transactions(
        self,
        app_user_id: UUID,
        *,
        deployment_id: UUID | None = None,
        limit: int = 50,
    ) -> list[TransactionRow]:
        if deployment_id is not None:
            self.get_deployment(app_user_id, deployment_id)
        rows = self._repo.sp_get_transaction(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
            limit=limit,
        )
        return [TransactionRow.model_validate(r) for r in rows]
