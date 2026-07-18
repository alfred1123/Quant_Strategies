"""Deployment dry-run orchestration — credentials, broker, signal, no orders."""

from __future__ import annotations

import logging
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches
from quant.schemas.dry_run import DryRunReport, DryRunRequest
from quant.strategy.live_service import LiveEvaluationError, compute_latest_position
from quant.trade.adapters.base import TradeAdapter
from quant.trade.db_repo import TradeRepo
from quant.trade.errors import AdapterNotFoundError, TradeValidationError
from quant.trade.registry import AdapterRegistry

logger = logging.getLogger(__name__)


def run_dry_run(
    *,
    app_user_id: UUID,
    req: DryRunRequest,
    repo: TradeRepo,
    bt: BtQueueRepo,
    credential_service: CredentialService,
    credential_repo: ApiCredentialRepo,
    adapter_registry: AdapterRegistry,
    data_caches: DataCaches,
) -> DryRunReport:
    """Validate broker + mapping and return intended action without placing orders."""
    strategy_row = repo.validate_dry_run(
        app_user_id=app_user_id,
        strategy_id=req.strategy_id,
        strategy_vid=req.strategy_vid,
        api_credential_id=req.api_credential_id,
        app_id=req.app_id,
        internal_cusip=req.internal_cusip,
        qty=req.qty,
    )

    if not adapter_registry.has_adapter(req.app_id):
        raise AdapterNotFoundError(
            f"no broker adapter registered for app_id={req.app_id}"
        )

    keys = credential_service.decrypt_credential(
        credential_repo, app_user_id, req.api_credential_id
    )
    if keys is None:
        raise TradeValidationError(
            "API credential not found or not owned", status_code=404
        )

    result_payload = bt.fetch_result_payload(req.strategy_id, req.strategy_vid)
    try:
        position, data_as_of = compute_latest_position(
            strategy_row["config_json"],
            result_payload=result_payload,
            caches=data_caches,
        )
    except LiveEvaluationError as exc:
        raise TradeValidationError(str(exc)) from exc

    adapter = adapter_registry.create(
        req.app_id,
        api_key=keys[0],
        api_secret=keys[1],
        paper=req.paper,
        inst_cache=data_caches.instrument_cache,
    )
    with adapter:
        return _broker_report(
            adapter=adapter,
            req=req,
            strategy_row=strategy_row,
            signal=position,
            data_as_of=data_as_of,
        )


def _broker_report(
    *,
    adapter: TradeAdapter,
    req: DryRunRequest,
    strategy_row: dict,
    signal: float,
    data_as_of: str,
) -> DryRunReport:
    """Build dry-run report; caller must manage adapter lifecycle via context manager."""
    vendor_symbol = adapter.validate_for_dry_run(req.internal_cusip, req.app_id)
    position_qty = adapter.get_position_qty(vendor_symbol)
    intended = adapter.intended_side(signal, position_qty)

    price = adapter.get_last_price(vendor_symbol)
    notional = float(req.qty) * price if price is not None else None

    return DryRunReport(
        strategy_id=req.strategy_id,
        strategy_vid=req.strategy_vid,
        strategy_nm=strategy_row.get("strategy_nm") or "",
        internal_cusip=req.internal_cusip,
        vendor_symbol=vendor_symbol,
        app_id=req.app_id,
        paper=req.paper,
        qty=req.qty,
        signal=signal,
        intended_side=intended,
        position_qty=position_qty,
        data_as_of=data_as_of,
        notional=notional,
    )
