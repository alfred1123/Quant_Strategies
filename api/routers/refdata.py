"""REFDATA router — serves cached reference data for UI dropdowns."""

import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/refdata", tags=["refdata"])


@router.get("/{table_name}")
def get_refdata(table_name: str, request: Request):
    cache = request.app.state.refdata_cache
    try:
        return cache.get(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/refresh", status_code=204)
def refresh_refdata(request: Request):
    cache = request.app.state.refdata_cache
    try:
        cache.refresh()
    except Exception as exc:
        logger.exception("REFDATA refresh failed")
        raise HTTPException(status_code=503, detail="Failed to refresh REFDATA") from exc
