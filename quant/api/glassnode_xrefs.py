"""Wire an exchange listing to a Glassnode product xref.

``quant.data.glassnode_xref`` owns the decision and does not open a
connection. This module is the one that can see REFDATA, the ccxt app
list, the price-bar factory, and the Glassnode client together. The live
client is constructed here, and only here.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections.abc import Callable, Collection, Sequence

from quant.data.glassnode_xref import (
    ASSET_LIST_UNAVAILABLE,
    MARKETS_UNAVAILABLE,
    XREF_NOT_WRITTEN,
    GlassnodeXrefOutcome,
    glassnode_app_id,
    load_venue_markets,
    map_glassnode_xrefs,
    read_glassnode_asset_symbols,
)
from quant.data.instruments import InstrumentCache
from quant.data.sources import Glassnode
from quant.market_data.fetcher import VenueMarket
from quant.refdata.bundle import DataCaches
from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.registry import ccxt_apps

logger = logging.getLogger(__name__)

#: Process tuning. A catalog GET that sits for the historical-price timeout
#: (30s) is long enough to stall a create worker. Override with
#: ``GLASSNODE_ASSET_LIST_TIMEOUT_S``. Not a business limit: the asset list
#: is not a user-facing quota.
_DEFAULT_ASSET_LIST_TIMEOUT_S = 2.0

_cache_lock = threading.Lock()
_cached_symbols: list[str] | None = None
_fetch_lock = threading.Lock()
_workers_lock = threading.Lock()
_workers: set[threading.Thread] = set()


def asset_list_timeout_s() -> float:
    """Seconds a Glassnode asset-catalog GET may take.

    Unset uses the process default. A blank value is unset. Anything that
    is not a positive finite number raises — a bad deploy setting must not
    be read as the default.
    """
    raw = os.getenv("GLASSNODE_ASSET_LIST_TIMEOUT_S")
    if raw is None or raw.strip() == "":
        return _DEFAULT_ASSET_LIST_TIMEOUT_S
    timeout = float(raw)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(
            f"GLASSNODE_ASSET_LIST_TIMEOUT_S must be a positive number, got {raw!r}"
        )
    return timeout


def live_glassnode_asset_reader() -> list[str]:
    """Open the Glassnode client and read the asset catalog.

    This is the only call site that constructs ``Glassnode``. Callers that
    already hold the catalog, and tests, pass the symbols in and never
    reach this function.
    """
    return Glassnode().list_asset_symbols(timeout_s=asset_list_timeout_s())


def store_glassnode_asset_symbols(symbols: Collection[str]) -> None:
    """Remember a catalog that has already been read."""
    global _cached_symbols
    with _cache_lock:
        _cached_symbols = list(symbols)


def clear_glassnode_asset_cache() -> None:
    """Drop the process catalog. The next pass that needs it reads again."""
    global _cached_symbols
    with _cache_lock:
        _cached_symbols = None


def wait_for_glassnode_xref_workers(timeout_s: float = 2.0) -> None:
    """Join background xref passes started by this process.

    Tests call this so a worker cannot outlive the test that started it.
    A timed-out create does not: the worker is a daemon and keeps the write
    going after the response has been sent.
    """
    with _workers_lock:
        threads = list(_workers)
    for thread in threads:
        thread.join(timeout_s)
    with _workers_lock:
        _workers.difference_update(thread for thread in threads if not thread.is_alive())


def warm_glassnode_asset_cache() -> None:
    """Fetch the asset catalog on a daemon thread.

    Startup calls this so a later create usually finds the list already
    cached. The thread is not joined. A missing key does not start a fetch:
    there is nothing the client can read. A timeout or an unreachable
    Glassnode leaves the cache empty; create then does not wait on it past
    the asset-list timeout.
    """
    if not (os.getenv("GLASSNODE_API_KEY") or "").strip():
        return
    if _cached_asset_symbols() is not None:
        return
    _start_daemon(_warm_asset_cache)


def apply_listing_glassnode_xrefs(
    caches: DataCaches,
    price_bars: PriceBarServiceFactory,
    *,
    product_id: int | None = None,
    listed_symbols: Collection[object] | None = None,
    asset_reader: Callable[[], Collection[object] | None] | None = None,
) -> list[GlassnodeXrefOutcome]:
    """Confirm the venue base against Glassnode and write the xref it allows.

    ``product_id`` is the listing just created. None walks every product that
    already has a ccxt exchange listing — the one backfill, not a schedule.

    A product that is not listed on a ccxt venue is skipped before the asset
    list is read. Adding an equity must not depend on ``GLASSNODE_API_KEY``.

    The create pass does not call Glassnode or the venue on this thread when
    the asset catalog and the venue's market table are already in the
    process. When either is missing, the read runs on a daemon thread and
    this call waits at most :func:`asset_list_timeout_s`. The thread keeps
    going after that, and still writes the xref if the base is listed. The
    returned skip reason is what this call knew before it stopped waiting.
    """
    cache = caches.instrument_cache
    exchange_app_ids = [app_id for app_id, _preset in ccxt_apps(caches.refdata)]
    if product_id is not None:
        exchange_app_ids = _exchange_ids_on_product(cache, product_id, exchange_app_ids)
        if not exchange_app_ids:
            return []
        return _apply_for_create(
            caches,
            price_bars,
            product_id=product_id,
            exchange_app_ids=exchange_app_ids,
            listed_symbols=listed_symbols,
            asset_reader=asset_reader,
        )
    return _apply_for_backfill(
        caches,
        price_bars,
        exchange_app_ids=exchange_app_ids,
        listed_symbols=listed_symbols,
        asset_reader=asset_reader,
    )


def _apply_for_create(
    caches: DataCaches,
    price_bars: PriceBarServiceFactory,
    *,
    product_id: int,
    exchange_app_ids: Sequence[int],
    listed_symbols: Collection[object] | None,
    asset_reader: Callable[[], Collection[object] | None] | None,
) -> list[GlassnodeXrefOutcome]:
    symbols = (
        read_glassnode_asset_symbols(listed_symbols)
        if listed_symbols is not None
        else _cached_asset_symbols()
    )
    markets, missing = _cached_venue_markets(price_bars, exchange_app_ids)
    if symbols is not None and not missing:
        return _map(
            caches,
            exchange_app_ids,
            markets,
            (),
            symbols,
            product_id,
        )

    timeout_s = asset_list_timeout_s()
    done = threading.Event()
    outcomes: list[GlassnodeXrefOutcome] | None = None
    failed = False

    def work() -> None:
        nonlocal outcomes, failed
        try:
            outcomes = _map_with_network(
                caches,
                price_bars,
                product_id=product_id,
                exchange_app_ids=exchange_app_ids,
                listed_symbols=listed_symbols,
                asset_reader=asset_reader,
                refresh_catalog=False,
            )
        except Exception:
            logger.exception(
                "Glassnode xref was not written for product_id=%s",
                product_id,
            )
            failed = True
        finally:
            done.set()

    _start_daemon(work)
    if not done.wait(timeout_s):
        reason = ASSET_LIST_UNAVAILABLE if symbols is None else MARKETS_UNAVAILABLE
        return [_not_written(caches.instrument_cache, product_id, reason)]
    if failed or outcomes is None:
        return [_not_written(caches.instrument_cache, product_id, XREF_NOT_WRITTEN)]
    return outcomes


def _apply_for_backfill(
    caches: DataCaches,
    price_bars: PriceBarServiceFactory,
    *,
    exchange_app_ids: Sequence[int],
    listed_symbols: Collection[object] | None,
    asset_reader: Callable[[], Collection[object] | None] | None,
) -> list[GlassnodeXrefOutcome]:
    """The admin pass. It may call the network. The route turns a leak into a 200."""
    return _map_with_network(
        caches,
        price_bars,
        product_id=None,
        exchange_app_ids=exchange_app_ids,
        listed_symbols=listed_symbols,
        asset_reader=asset_reader,
        refresh_catalog=True,
    )


def _map_with_network(
    caches: DataCaches,
    price_bars: PriceBarServiceFactory,
    *,
    product_id: int | None,
    exchange_app_ids: Sequence[int],
    listed_symbols: Collection[object] | None,
    asset_reader: Callable[[], Collection[object] | None] | None,
    refresh_catalog: bool,
) -> list[GlassnodeXrefOutcome]:
    if listed_symbols is not None:
        symbols: list[str] | None = read_glassnode_asset_symbols(listed_symbols)
    else:
        reader = asset_reader if asset_reader is not None else live_glassnode_asset_reader
        symbols = _fetch_and_cache(reader, refresh=refresh_catalog)
    markets_by_app, failed_app_ids = load_venue_markets(
        exchange_app_ids,
        lambda app_id: price_bars.for_app(app_id).venue_symbols(),
    )
    return _map(
        caches,
        exchange_app_ids,
        markets_by_app,
        failed_app_ids,
        symbols,
        product_id,
    )


def _map(
    caches: DataCaches,
    exchange_app_ids: Sequence[int],
    markets_by_app: dict[int, list[VenueMarket]],
    failed_app_ids: Collection[int],
    listed_symbols: Collection[str] | None,
    product_id: int | None,
) -> list[GlassnodeXrefOutcome]:
    return map_glassnode_xrefs(
        caches.instrument_cache,
        glassnode_app_id=glassnode_app_id(caches.refdata),
        exchange_app_ids=exchange_app_ids,
        markets_by_app=markets_by_app,
        failed_app_ids=failed_app_ids,
        listed_symbols=listed_symbols,
        product_id=product_id,
    )


def _cached_venue_markets(
    price_bars: PriceBarServiceFactory,
    exchange_app_ids: Sequence[int],
) -> tuple[dict[int, list[VenueMarket]], list[int]]:
    loaded: dict[int, list[VenueMarket]] = {}
    missing: list[int] = []
    for app_id in exchange_app_ids:
        markets = price_bars.for_app(app_id).cached_venue_symbols()
        if markets is None:
            missing.append(int(app_id))
            continue
        loaded[int(app_id)] = list(markets)
    return loaded, missing


def _not_written(
    cache: InstrumentCache,
    product_id: int,
    reason: str,
) -> GlassnodeXrefOutcome:
    product = cache.get_product_by_id(product_id)
    cusip = ""
    if isinstance(product, dict):
        cusip = str(product.get("internal_cusip") or "")
    return GlassnodeXrefOutcome(
        product_id=product_id,
        internal_cusip=cusip,
        vendor_symbol=None,
        skip_reason=reason,
        wrote=False,
    )


def _cached_asset_symbols() -> list[str] | None:
    with _cache_lock:
        if _cached_symbols is None:
            return None
        return list(_cached_symbols)


def _fetch_and_cache(
    reader: Callable[[], Collection[object] | None],
    *,
    refresh: bool,
) -> list[str] | None:
    """Read the catalog once, even when several passes ask together.

    A failed read does not clear a catalog already stored. Unread is not
    empty, and a blip must not make the next create treat every base as
    unlisted. ``refresh`` is the admin pass: it reads again even when a
    catalog is already cached, and a failure returns None for that pass
    without replacing the stored list.
    """
    if not refresh:
        cached = _cached_asset_symbols()
        if cached is not None:
            return cached
    with _fetch_lock:
        if not refresh:
            cached = _cached_asset_symbols()
            if cached is not None:
                return cached
        symbols = read_glassnode_asset_symbols(reader=reader)
        if symbols is not None:
            store_glassnode_asset_symbols(symbols)
        return symbols


def _warm_asset_cache() -> None:
    try:
        _fetch_and_cache(live_glassnode_asset_reader, refresh=False)
    except Exception:
        logger.exception("Glassnode asset catalog could not be cached")


def _start_daemon(target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target, name="glassnode-xref", daemon=True)
    thread.start()
    with _workers_lock:
        _workers.add(thread)
        finished = {worker for worker in _workers if not worker.is_alive()}
        _workers.difference_update(finished)


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
