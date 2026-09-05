"""INST router — the instrument master: the lists UI dropdowns read, and the
one write that adds to them.

Instruments are **not scoped to the caller**. A product is a shared platform
fact in the same way a bar subscription is: everybody sees the same list, and
the row an instrument creates is the row everybody then trades against. Being
signed in is what the write route checks; ownership is not a thing an
instrument has, and ``USER_ID`` on the row is audit only.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.deps import get_data_caches
from quant.refdata.bundle import DataCaches
from quant.schemas.inst import CreatedInstrument, CreateInstrumentRequest, VenueSymbol
from quant.trade.registry import exchange_id_for_app

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


@router.get("/apps/{app_id}/venue-symbols", response_model=list[VenueSymbol])
def get_venue_symbols(
    app_id: int,
    request: Request,
    caches: DataCaches = Depends(get_data_caches),
) -> list[VenueSymbol]:
    """What this venue *could* list, as opposed to what the platform has mapped.

    The only route in this router that leaves the process. Every other read
    here is the instrument cache answering what we already hold, and that is
    exactly why this one cannot be: creating an instrument means naming a
    ticker the platform has never stored, so the set to choose from can only
    come from the exchange.

    Empty rather than 404 for a venue with no market list, matching
    ``/apps/{app_id}/products`` — a broker the platform reaches some other way
    is a real venue that simply cannot answer this, and the form stays usable
    as free text either way.
    """
    if exchange_id_for_app(app_id, refdata=caches.refdata) is None:
        return []
    # Through the price bar factory for its cached client: ccxt holds the
    # symbol table on the exchange instance, so a per-request fetcher would
    # re-download several thousand markets on every keystroke-triggered mount.
    markets = request.app.state.price_bars.for_app(app_id).venue_symbols()
    return [
        VenueSymbol(
            vendor_symbol=m.vendor_symbol,
            base=m.base,
            quote=m.quote,
            market_types=list(m.market_types),
        )
        for m in markets
    ]


@router.post(
    "/products",
    response_model=CreatedInstrument,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    req: CreateInstrumentRequest,
    user: CurrentUser = Depends(require_user),
    caches: DataCaches = Depends(get_data_caches),
) -> CreatedInstrument:
    """Create a product and the first venue symbol for it, in one submit.

    201 because this genuinely creates — unlike ``/market-data/subscriptions``,
    where the same route also enables and retargets. Sending it twice for the
    same cusip is a 409, not a second instrument: the cusip *is* the identity.

    ``require_user`` is restated even though the whole router is mounted behind
    it, for the reason the market-data router gives: the router gate is a floor
    and not a ceiling, so a write must not depend on how it happens to be
    mounted today. It checks that somebody is signed in and nothing more —
    there is no owner to compare against.
    """
    created = caches.instrument_cache.create_instrument(
        internal_cusip=req.internal_cusip,
        display_nm=req.display_nm,
        asset_type_id=req.asset_type_id,
        exchange=req.exchange,
        ccy=req.ccy,
        description=req.description,
        app_id=req.app_id,
        vendor_symbol=req.vendor_symbol,
    )
    logger.info(
        "instrument %s created by %s, listed on app %d as %s",
        req.internal_cusip, user.username, req.app_id, req.vendor_symbol,
    )
    return CreatedInstrument(**created)


@router.post("/refresh", status_code=204)
def refresh_inst(caches: DataCaches = Depends(get_data_caches)):
    try:
        caches.instrument_cache.refresh()
    except Exception as exc:
        logger.exception("INST refresh failed")
        raise HTTPException(status_code=503, detail="Failed to refresh INST cache") from exc
