"""Admin router — /api/v1/admin.

System-level endpoints for scheduled maintenance tasks.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from quant.api.admin.repo import LogProcRepo
from quant.api.auth.dependencies import require_user_or_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_log_proc_repo(request: Request) -> LogProcRepo:
    return LogProcRepo(request.app.state.db_conninfo, user_id="system")


@router.post("/log-proc-summary/summarize")
def summarize_log_proc(
    caller: str = Depends(require_user_or_service),
    repo: LogProcRepo = Depends(_get_log_proc_repo),
) -> dict:
    """Aggregate LOG_PROC_DETAIL into daily per-proc summaries."""
    rows_affected = repo.summarize()
    logger.info("log-proc-summary: %d rows upserted by caller=%s", rows_affected, caller)
    return {"rows_affected": rows_affected}
