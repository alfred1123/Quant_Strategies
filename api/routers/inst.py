"""INST router — serves cached instrument/product data for UI dropdowns."""

import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inst", tags=["inst"])


@router.get("/products")
def get_products(request: Request):
    cache = request.app.state.instrument_cache
    return cache.get_products()


@router.get("/products/{product_id}/xrefs")
def get_product_xrefs(product_id: int, request: Request):
    cache = request.app.state.instrument_cache
    xrefs = cache.get_xrefs(product_id=product_id)
    if not xrefs:
        raise HTTPException(status_code=404, detail=f"No xrefs for product_id={product_id}")
    return xrefs


@router.post("/refresh", status_code=204)
def refresh_inst(request: Request):
    cache = request.app.state.instrument_cache
    try:
        cache.refresh()
    except Exception as exc:
        logger.exception("INST refresh failed")
        raise HTTPException(status_code=503, detail="Failed to refresh INST cache") from exc
