"""Wire an exchange listing to a Glassnode product xref.

``quant.data.glassnode_xref`` owns the decision. This module is the one
that can see REFDATA, the ccxt app list, and the price-bar factory together.
"""

from __future__ import annotations

from quant.data.glassnode_xref import (
    GlassnodeXrefOutcome,
    glassnode_app_id,
    load_venue_markets,
    map_glassnode_xrefs,
    read_glassnode_asset_symbols,
)
from quant.data.instruments import InstrumentCache
from quant.refdata.bundle import DataCaches
from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.registry import ccxt_apps


def apply_listing_glassnode_xrefs(
    caches: DataCaches,
    price_bars: PriceBarServiceFactory,
    *,
    product_id: int | None = None,
) -> list[GlassnodeXrefOutcome]:
    """Confirm the venue base against Glassnode and write the xref it allows.

    ``product_id`` is the listing just created. None walks every product that
    already has a ccxt exchange listing — the one backfill, not a schedule.

    A product that is not listed on a ccxt venue is skipped before the asset
    list is read. Adding an equity must not depend on ``GLASSNODE_API_KEY``.
    """
    cache = caches.instrument_cache
    exchange_app_ids = [app_id for app_id, _preset in ccxt_apps(caches.refdata)]
    if product_id is not None:
        exchange_app_ids = _exchange_ids_on_product(cache, product_id, exchange_app_ids)
        if not exchange_app_ids:
            return []

    markets_by_app, failed_app_ids = load_venue_markets(
        exchange_app_ids,
        lambda app_id: price_bars.for_app(app_id).venue_symbols(),
    )
    return map_glassnode_xrefs(
        cache,
        glassnode_app_id=glassnode_app_id(caches.refdata),
        exchange_app_ids=exchange_app_ids,
        markets_by_app=markets_by_app,
        failed_app_ids=failed_app_ids,
        listed_symbols=read_glassnode_asset_symbols(),
        product_id=product_id,
    )


def _exchange_ids_on_product(
    cache: InstrumentCache,
    product_id: int,
    exchange_app_ids: list[int],
) -> list[int]:
    """Ccxt apps this product already lists, in the order the catalog named them."""
    exchange_ids = {int(app_id) for app_id in exchange_app_ids}
    found: list[int] = []
    for xref in cache.get_xrefs(product_id=product_id):
        app_id = xref.get("app_id")
        if app_id is None:
            continue
        app_key = int(app_id)
        if app_key in exchange_ids and app_key not in found:
            found.append(app_key)
    return found
