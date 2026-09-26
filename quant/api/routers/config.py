"""CONFIG policy snapshot.

``GET /config/{table}`` reads ``config:<table>``.
``POST /config/refresh`` rewrites that snapshot only.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from quant.shared.config import get_redis_url
from quant.api.deps import get_data_caches
from quant.refdata.bundle import DataCaches
from quant.refdata.publisher import RefDataPublisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/{table_name}")
def get_config(table_name: str, caches: DataCaches = Depends(get_data_caches)):
    try:
        return caches.refdata.get_config(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/refresh")
def refresh_config(request: Request):
    """Re-publish CONFIG policy rows from Postgres into Redis.

    Any authenticated user may trigger a refresh today — there is no
    admin role yet. Returns the number of tables published.
    """
    conninfo = request.app.state.db_conninfo
    try:
        n = RefDataPublisher(conninfo, get_redis_url()).publish("config")
    except Exception as exc:
        logger.exception("CONFIG refresh failed")
        raise HTTPException(status_code=503, detail=f"refresh failed: {exc}") from exc
    return {"tables": n}
