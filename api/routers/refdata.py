"""REFDATA router — serves cached reference data for UI dropdowns.

Read-only. Refreshing REFDATA from Postgres is the **coordinator's**
responsibility (it owns the Redis snapshot and version stamp). FastAPI
workers pick up new data automatically on the next ``get()`` via the
``refdata:version`` check in ``RedisRefData``. Routes use ``DataCaches``
from ``api.deps.get_data_caches``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_data_caches
from src.cache import DataCaches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/refdata", tags=["refdata"])


@router.get("/{table_name}")
def get_refdata(table_name: str, caches: DataCaches = Depends(get_data_caches)):
    try:
        return caches.refdata.get(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
