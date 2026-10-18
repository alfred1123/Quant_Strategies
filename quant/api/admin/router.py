"""Admin router — /api/v1/admin.

System-level endpoints for scheduled maintenance tasks.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from quant.api.admin.connection_maintenance import ConnectionMaintenanceService
from quant.api.admin.repo import ApiRequestPayloadRepo, ConnectionMaintenanceRepo, LogProcRepo
from quant.api.admin.schemas import (
    DetachApiRequestPayloadRequest,
    FillScheduledProvidersRequest,
    TerminateStaleConnectionsRequest,
)
from quant.api.auth.dependencies import require_user_or_service
from quant.api.deps import get_data_caches
from quant.data.provider_fill import fill_scheduled_providers
from quant.refdata.bundle import DataCaches
from quant.trade.registry import ccxt_apps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_log_proc_repo(request: Request) -> LogProcRepo:
    return LogProcRepo(request.app.state.db_conninfo, user_id="system")


def _get_api_request_payload_repo(request: Request) -> ApiRequestPayloadRepo:
    return ApiRequestPayloadRepo(request.app.state.db_conninfo, user_id="system")


def _get_connection_maintenance_service(request: Request) -> ConnectionMaintenanceService:
    return ConnectionMaintenanceService(
        ConnectionMaintenanceRepo(request.app.state.db_conninfo, user_id="system"),
    )


@router.post("/db/terminate-stale-connections")
def terminate_stale_connections(
    body: TerminateStaleConnectionsRequest = TerminateStaleConnectionsRequest(),
    caller: str = Depends(require_user_or_service),
    service: ConnectionMaintenanceService = Depends(_get_connection_maintenance_service),
) -> dict:
    """Terminate idle ``quant_app`` sessions older than *idle_seconds*."""
    sweep = service.sweep_stale_connections(idle_seconds=body.idle_seconds)
    logger.info(
        "db/terminate-stale-connections: stale=%d terminated=%d idle_seconds=%d caller=%s",
        sweep.stale,
        sweep.terminated,
        body.idle_seconds,
        caller,
    )
    return {
        "stale": sweep.stale,
        "terminated": sweep.terminated,
        "idle_seconds": body.idle_seconds,
    }


@router.post("/db/detach-api-request-payload")
def detach_api_request_payload(
    body: DetachApiRequestPayloadRequest = DetachApiRequestPayloadRequest(),
    caller: str = Depends(require_user_or_service),
    repo: ApiRequestPayloadRepo = Depends(_get_api_request_payload_repo),
) -> dict:
    """Detach payload partitions whose range ended before *retention_days*."""
    dropped = repo.detach(retention_days=body.retention_days)
    logger.info(
        "db/detach-api-request-payload: dropped=%d retention_days=%d caller=%s",
        dropped,
        body.retention_days,
        caller,
    )
    return {"dropped": dropped, "retention_days": body.retention_days}


def _venue_markets(request: Request, app_id: int) -> list[tuple[str, str | None]] | None:
    """``(vendor_symbol, base)`` for one ccxt app, or None when the table is unread."""
    try:
        markets = request.app.state.price_bars.for_app(app_id).venue_symbols()
    except Exception:
        logger.exception("venue markets unavailable for app_id=%s", app_id)
        return None
    return [(market.vendor_symbol, market.base) for market in markets]


@router.post("/providers/fill")
def fill_providers(
    request: Request,
    body: FillScheduledProvidersRequest,
    caller: str = Depends(require_user_or_service),
    caches: DataCaches = Depends(get_data_caches),
) -> dict:
    """Insert a fresh window for every provider the checkbox does not call.

    A missing provider xref is written first when the exchange base is on
    that provider's asset list. The fetch then reads the xref.
    """
    exchange_app_ids = [app_id for app_id, _preset in ccxt_apps(caches.refdata)]
    report = fill_scheduled_providers(
        caches.refdata,
        caches.instrument_cache,
        caches.backtest_cache,
        since=body.since,
        exchange_app_ids=exchange_app_ids,
        markets_for_app=lambda app_id: _venue_markets(request, app_id),
    )
    logger.info(
        "providers/fill: filled=%d failed=%d since=%s caller=%s",
        report.filled,
        report.failed,
        body.since.isoformat(),
        caller,
    )
    return {
        "filled": report.filled,
        "failed": report.failed,
        "since": body.since.isoformat(),
        "errors": report.errors,
    }


@router.post("/log-proc-summary/summarize")
def summarize_log_proc(
    caller: str = Depends(require_user_or_service),
    repo: LogProcRepo = Depends(_get_log_proc_repo),
) -> dict:
    """Aggregate LOG_PROC_DETAIL into daily per-proc summaries."""
    rows_affected = repo.summarize()
    logger.info("log-proc-summary: %d rows upserted by caller=%s", rows_affected, caller)
    return {"rows_affected": rows_affected}
