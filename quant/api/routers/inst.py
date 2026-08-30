"""INST router — serves cached instrument/product data for UI dropdowns."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from quant.api.deps import get_data_caches
from quant.refdata.bundle import DataCaches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inst", tags=["inst"])


@router.get("/products")
def get_products(caches: DataCaches = Depends(get_data_caches)):
    return caches.instrument_cache.get_products()


@router.get("/products/{product_id}/xrefs")
def get_product_xrefs(product_id: int, caches: DataCaches = Depends(get_data_caches)):
    xrefs = caches.instrument_cache.get_xrefs(product_id=product_id)
    if not xrefs:
        raise HTTPException(status_code=404, detail=f"No xrefs for product_id={product_id}")
    return xrefs


@router.get("/apps/{app_id}/products")
def get_app_products(app_id: int, caches: DataCaches = Depends(get_data_caches)):
    """Products this app actually lists, with the symbol it prints for each.

    `/products` is every instrument the platform knows, which is the wrong list
    to offer once a venue is chosen: a Nasdaq ETF has no Bybit xref, so picking
    it could only produce a subscription that never captures a bar. Listing is
    exactly what `INST.PRODUCT_XREF` records, so the xrefs for one app *are*
    the answer.

    Empty is a real answer — an exchange with no xrefs lists nothing — so this
    returns `[]` rather than 404, unlike the per-product lookup above where a
    missing product is a bad request.
    """
    cache = caches.instrument_cache
    products = []
    for xref in cache.get_xrefs(app_id=app_id):
        product = cache.get_product_by_id(xref["product_id"])
        if product is not None:
            products.append(product | {"vendor_symbol": xref["vendor_symbol"]})
    return products


@router.post("/refresh", status_code=204)
def refresh_inst(caches: DataCaches = Depends(get_data_caches)):
    try:
        caches.instrument_cache.refresh()
    except Exception as exc:
        logger.exception("INST refresh failed")
        raise HTTPException(status_code=503, detail="Failed to refresh INST cache") from exc
