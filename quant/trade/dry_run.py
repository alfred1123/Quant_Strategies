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
from quant.trade.bar_source import PriceBarServiceFactory, resolve_signal_source
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
    price_bars: PriceBarServiceFactory | None = None,
) -> DryRunReport:
    """Validate broker + mapping and return intended action without placing orders.

    Prices off the same series the live apply will use. It did not always: the
    dry run took the provider path unconditionally, so a preview could report
    HOLD off one venue's bars while the apply that followed placed a BUY off
    another's. A dry run whose numbers do not match the thing it previews is
    worse than none, because it is trusted.

    There is no schedule yet at dry-run time, so ``resolve_signal_source``
    falls through to daily — the cadence a deployment is allowed to run on.
    """
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
    bar_loader, bar_source = resolve_signal_source(
        app_id=req.app_id,
        schedule_tm_interval_id=None,
        data_caches=data_caches,
        price_bars=price_bars,
        what=f"dry run of strategy {req.strategy_id}",
    )
    try:
        position, data_as_of = compute_latest_position(
            strategy_row["config_json"],
            result_payload=result_payload,
            caches=data_caches,
            bar_loader=bar_loader,
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
            bar_source=bar_source,
        )


def _broker_report(
    *,
    adapter: TradeAdapter,
    req: DryRunRequest,
    strategy_row: dict,
    signal: float,
    data_as_of: str,
    bar_source: str,
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
        bar_source=bar_source,
    )
