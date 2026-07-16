"""Live apply orchestration — signal → order → audit.

Phase 1.7: single-attempt execution. Retry/cancel policy (bounded backoff,
cancel-before-retry, Notifier alerts) will be layered in Phase 2.
"""

from __future__ import annotations

import logging
import uuid
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches
from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import DeploymentRow
from quant.strategy.live_service import LiveEvaluationError, compute_latest_position
from quant.trade.brokers.ccxt.confirm import buy_sell_cd_for_action
from quant.trade.errors import AdapterNotFoundError, TradeValidationError
from quant.trade.models.order import IntendedAction
from quant.trade.db_repo import TradeRepo
from quant.trade.registry import AdapterRegistry

logger = logging.getLogger(__name__)


def run_live_apply(
    *,
    app_user_id: UUID,
    deployment: DeploymentRow,
    repo: TradeRepo,
    bt: BtQueueRepo,
    credential_service: CredentialService,
    credential_repo: ApiCredentialRepo,
    adapter_registry: AdapterRegistry,
    data_caches: DataCaches,
    user_id: str,
) -> ApplyReport:
    """Execute one apply cycle: signal evaluation → order → audit write."""

    # ── adapter ──────────────────────────────────────────────────
    if not adapter_registry.has_adapter(deployment.app_id):
        raise AdapterNotFoundError(
            f"no broker adapter registered for app_id={deployment.app_id}"
        )
    keys = credential_service.decrypt_credential(
        credential_repo, app_user_id, deployment.api_credential_id
    )
    if keys is None:
        raise TradeValidationError(
            "API credential not found or cannot decrypt", status_code=404
        )

    # ── signal ───────────────────────────────────────────────────
    strategy_rows = bt.sp_get_strategy(
        deployment.strategy_id, strategy_vid=deployment.strategy_vid
    )
    if not strategy_rows:
        raise TradeValidationError(
            f"strategy {deployment.strategy_id} v{deployment.strategy_vid} not found",
            status_code=404,
        )
    strategy_row = strategy_rows[0]

    result_payload = bt.fetch_result_payload(
        deployment.strategy_id, deployment.strategy_vid
    )
    try:
        signal, _data_as_of = compute_latest_position(
            strategy_row["config_json"],
            result_payload=result_payload,
            caches=data_caches,
        )
    except LiveEvaluationError as exc:
        raise TradeValidationError(str(exc)) from exc

    # ── execute ──────────────────────────────────────────────────
    adapter = adapter_registry.create(
        deployment.app_id,
        api_key=keys[0],
        api_secret=keys[1],
        paper=deployment.is_paper_ind == "Y",
        inst_cache=data_caches.instrument_cache,
    )
    with adapter:
        vendor_symbol = adapter.validate_for_dry_run(
            deployment.internal_cusip, deployment.app_id
        )
        position_qty = adapter.get_position_qty(vendor_symbol)
        action = adapter.intended_side(signal, position_qty)

        if action is IntendedAction.HOLD:
            return ApplyReport(
                deployment_id=deployment.deployment_id,
                deployment_vid=deployment.deployment_vid,
                action=action,
                vendor_symbol=vendor_symbol,
                signal=signal,
                position_qty=position_qty,
                message="no order needed (HOLD)",
            )

        result = adapter.apply_signal(
            vendor_symbol, signal, float(deployment.qty)
        )
        if result is None:
            return ApplyReport(
                deployment_id=deployment.deployment_id,
                deployment_vid=deployment.deployment_vid,
                action=action,
                vendor_symbol=vendor_symbol,
                signal=signal,
                position_qty=position_qty,
                message="no order needed (qty resolved to 0)",
            )

        # ── audit ────────────────────────────────────────────────
        buy_sell = buy_sell_cd_for_action(action)
        if buy_sell is not None:
            try:
                repo.sp_ins_execution_event(
                    execution_event_id=uuid.uuid4(),
                    app_user_id=app_user_id,
                    deployment_id=deployment.deployment_id,
                    deployment_vid=deployment.deployment_vid,
                    buy_sell_cd=buy_sell,
                    is_success_ind="Y" if result.success else "N",
                    user_id=user_id,
                    signal_value=signal,
                    quantity=result.filled_qty or float(deployment.qty),
                    vendor_order_id=result.vendor_order_id,
                )
            except Exception:
                logger.exception("audit write failed — order was already placed")

        return ApplyReport(
            deployment_id=deployment.deployment_id,
            deployment_vid=deployment.deployment_vid,
            action=action,
            vendor_symbol=vendor_symbol,
            signal=signal,
            position_qty=position_qty,
            order_success=result.success,
            vendor_order_id=result.vendor_order_id,
            filled_qty=result.filled_qty,
            avg_price=result.avg_price,
            fee=result.fee,
            message=result.message,
        )
