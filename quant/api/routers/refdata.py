"""REFDATA router — serves cached reference data for UI dropdowns.

FastAPI both publishes (lifespan + ``POST /refresh``) and reads REFDATA
from Redis. Workers pick up changes on their next ``get()`` via the
``refdata:version`` check in ``RedisRefData``. Routes use ``DataCaches``
from ``api.deps.get_data_caches``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from quant.shared.config import get_redis_url
from quant.api.deps import get_data_caches
from quant.refdata.bundle import DataCaches
from quant.refdata.publisher import RefDataPublisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/refdata", tags=["refdata"])


@router.get("/{table_name}")
def get_refdata(table_name: str, caches: DataCaches = Depends(get_data_caches)):
    try:
        return caches.refdata.get(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/refresh")
def refresh_refdata(request: Request):
    """Re-publish every REFDATA table from Postgres into Redis.

    Any authenticated user may trigger a refresh today — there is no
    admin role yet. Returns the number of tables published.
    """
    conninfo = request.app.state.db_conninfo
    try:
        n = RefDataPublisher(conninfo, get_redis_url()).publish_all()
    except Exception as exc:
        logger.exception("REFDATA refresh failed")
        raise HTTPException(status_code=503, detail=f"refresh failed: {exc}") from exc
    return {"tables": n}
