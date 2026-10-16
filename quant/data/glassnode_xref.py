"""Map an exchange listing to a Glassnode ``INST.PRODUCT_XREF``.

Decision #21: the Glassnode symbol is the asset, not the pair. The asset is
the **venue market base** (``BTCUSDT`` → ``BTC``). It is not produced by
stripping a quote currency off ``INTERNAL_CUSIP`` — that breaks ``BTCUSDC``,
``1000PEPEUSDT``, and any pair that is not quoted in USDT.

A base is written only after Glassnode's asset list confirms it. A current
row for that product and app is left alone. A base the list does not contain
stays unmapped. Being listed is not a promise that every metric accepts the
asset; a metric that rejects it still fails at fetch time.

The write is ``InstrumentCache.sp_ins_product_xref`` (``INST.SP_INS_PRODUCT_XREF``).

This module does not construct a Glassnode client and does not call a venue.
The caller passes the asset catalog and the markets it already holds.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from quant.data.instruments import InstrumentCache
from quant.market_data.fetcher import VenueMarket
from quant.refdata.reader import RedisRefData
from quant.shared.db import ProcedureError

logger = logging.getLogger(__name__)

#: ``REFDATA.APP.NAME``. The id is resolved from the catalog at call time.
GLASSNODE_APP_NAME = "glassnode"

#: Phrase the create dialog shows when the asset list does not contain the base.
NOT_ON_GLASSNODE = "not on Glassnode"

NO_VENUE_BASE = "no venue market base"
BASES_DISAGREE = "venue market bases disagree"
MARKETS_UNAVAILABLE = "venue markets unavailable"
ASSET_LIST_UNAVAILABLE = "Glassnode asset list unavailable"
GLASSNODE_APP_MISSING = "REFDATA.APP has no glassnode row"
XREF_NOT_WRITTEN = "Glassnode xref was not written"

#: ``UQ_PRODUCT_XREF_CURRENT`` — one open row per ``(PRODUCT_ID, APP_ID)``.
_CURRENT_XREF_SQLSTATE = "23505"


@dataclass(frozen=True)
class GlassnodeXrefOutcome:
    """What the pass did for one exchange-listed product.

    ``wrote`` is true only when this pass inserted a row. ``skip_reason`` is
    set when no row was written and none was already there. An existing row
    has a ``vendor_symbol``, ``wrote`` false, and no skip reason.
    """

    product_id: int
    internal_cusip: str
    vendor_symbol: str | None
    skip_reason: str | None
    wrote: bool


def glassnode_app_id(refdata: RedisRefData) -> int | None:
    """``REFDATA.APP`` id for Glassnode, or None when that row is absent."""
    resolved = refdata.resolve_app_id(GLASSNODE_APP_NAME)
    if resolved is None:
        return None
    return int(resolved)


def venue_market_base(
    vendor_symbol: str | None,
    markets: Sequence[VenueMarket],
) -> str | None:
    """Base asset the venue prints for this ticker, or None when it prints none.

    Matched on the raw vendor symbol the xref stores. A ticker the venue does
    not list has no base — the cusip is not a substitute.
    """
    if not vendor_symbol or not markets:
        return None
    for market in markets:
        if market.vendor_symbol != vendor_symbol:
            continue
        base = (market.base or "").strip()
        return base or None
    return None


def read_glassnode_asset_symbols(
    listed_symbols: Collection[object] | None = None,
    *,
    reader: Callable[[], Collection[object] | None] | None = None,
) -> list[str] | None:
    """The asset catalog, or None when it could not be read.

    ``listed_symbols`` is a catalog the caller already holds, including an
    empty one. Nothing is fetched, and ``reader`` is not called. When only
    ``reader`` is set, that callable is what reaches the network — this
    function does not construct a client. None is not an empty catalog. An
    empty catalog means nothing is listed, so a base is not on Glassnode. An
    unread catalog must not be treated as that, and nothing is written until
    the list has been read. The exchange listing that triggered this pass is
    already stored; a failed read must not fail that request. The traceback
    is logged.
    """
    if listed_symbols is not None:
        return _symbol_list(listed_symbols)
    if reader is None:
        return None
    try:
        loaded = reader()
    except Exception:
        logger.exception("Glassnode asset list could not be read")
        return None
    if loaded is None:
        return None
    return _symbol_list(loaded)


def _symbol_list(symbols: Collection[object]) -> list[str]:
    cleaned: list[str] = []
    for symbol in symbols:
        if not isinstance(symbol, str):
            continue
        text = symbol.strip()
        if text:
            cleaned.append(text)
    return cleaned


def load_venue_markets(
    exchange_app_ids: Collection[int],
    markets_for_app: Callable[[int], Sequence[VenueMarket]],
) -> tuple[dict[int, list[VenueMarket]], set[int]]:
    """Markets per exchange app, and the apps whose list could not be read.

    A venue that cannot be listed does not abort the pass. The Glassnode
    symbol is the venue base, so a venue with no market table contributes no
    base, and the cusip is not consulted in its place. Other venues in the
    same pass still map. The traceback is logged.
    """
    loaded: dict[int, list[VenueMarket]] = {}
    failed: set[int] = set()
    for app_id in exchange_app_ids:
        app_key = int(app_id)
        try:
            loaded[app_key] = list(markets_for_app(app_key))
        except Exception:
            logger.exception("venue markets unavailable for app_id=%s", app_key)
            failed.add(app_key)
    return loaded, failed


def map_glassnode_xrefs(
    cache: InstrumentCache,
    *,
    glassnode_app_id: int | None,
    exchange_app_ids: Collection[int],
    markets_by_app: Mapping[int, Sequence[VenueMarket]],
    failed_app_ids: Collection[int] = (),
    listed_symbols: Collection[str] | None,
    product_id: int | None = None,
) -> list[GlassnodeXrefOutcome]:
    """Write a Glassnode xref for each exchange-listed product that qualifies.

    ``product_id`` limits the pass to one product (the listing just created).
    None walks every product the cache holds. Products with no ccxt exchange
    listing are omitted — they are not "not on Glassnode".

    ``listed_symbols`` None means the catalog could not be read. No xref is
    written in that case. An empty collection means Glassnode lists nothing.

    The instrument cache is reloaded once, after every write in the pass. A
    reload that fails is logged. The outcomes still return, because the rows
    are already committed.
    """
    exchange_ids = {int(app_id) for app_id in exchange_app_ids}
    failed = {int(app_id) for app_id in failed_app_ids}
    catalog = None if listed_symbols is None else _catalog(listed_symbols)
    products = cache.get_products()
    if product_id is not None:
        products = [row for row in products if int(row["product_id"]) == int(product_id)]

    outcomes: list[GlassnodeXrefOutcome] = []
    wrote_any = False
    try:
        for product in products:
            outcome, wrote = _outcome_for_product(
                cache,
                product,
                glassnode_app_id=glassnode_app_id,
                exchange_ids=exchange_ids,
                markets_by_app=markets_by_app,
                failed=failed,
                catalog=catalog,
            )
            if outcome is None:
                continue
            if wrote:
                wrote_any = True
            outcomes.append(outcome)
            logger.info(
                "glassnode xref product_id=%s cusip=%s wrote=%s symbol=%s reason=%s",
                outcome.product_id,
                outcome.internal_cusip,
                outcome.wrote,
                outcome.vendor_symbol,
                outcome.skip_reason,
            )
        return outcomes
    finally:
        # One reload for the whole pass. Refreshing after every insert reloads
        # every product and xref, and a failed reload aborted the products
        # still waiting. The rows are already committed; this publish is so
        # the process serves them. A failed reload is logged and the outcomes
        # still return — the same window as a failed ``POST /api/v1/inst/refresh``.
        # The unique-violation path refreshes on its own, because that read
        # has to see the row that won the race.
        if wrote_any:
            try:
                cache.refresh()
            except Exception:
                logger.exception(
                    "instrument cache refresh after glassnode xref writes failed"
                )


def glassnode_xref_report(
    outcomes: Sequence[GlassnodeXrefOutcome],
) -> dict[str, list[dict[str, object]]]:
    """Split a pass into mapped, already mapped, and skipped products."""
    mapped: list[dict] = []
    already_mapped: list[dict] = []
    skipped: list[dict] = []
    for outcome in outcomes:
        row = {
            "product_id": outcome.product_id,
            "internal_cusip": outcome.internal_cusip,
            "vendor_symbol": outcome.vendor_symbol,
        }
        if outcome.wrote:
            mapped.append(row)
        elif outcome.skip_reason:
            skipped.append({**row, "reason": outcome.skip_reason})
        else:
            already_mapped.append(row)
    return {
        "mapped": mapped,
        "already_mapped": already_mapped,
        "skipped": skipped,
    }


def _outcome_for_product(
    cache: InstrumentCache,
    product: dict,
    *,
    glassnode_app_id: int | None,
    exchange_ids: set[int],
    markets_by_app: Mapping[int, Sequence[VenueMarket]],
    failed: set[int],
    catalog: dict[str, str] | None,
) -> tuple[GlassnodeXrefOutcome | None, bool]:
    product_key = int(product["product_id"])
    cusip = str(product.get("internal_cusip") or "")
    exchange_xrefs = _exchange_xrefs(cache.get_xrefs(product_id=product_key), exchange_ids)
    if not exchange_xrefs:
        return None, False
    if glassnode_app_id is None:
        return _skipped(product_key, cusip, GLASSNODE_APP_MISSING), False

    existing = cache.resolve_vendor_symbol(product_key, glassnode_app_id)
    if existing:
        return _kept(product_key, cusip, existing), False

    bases, market_failed = _bases(exchange_xrefs, markets_by_app, failed)
    distinct = _distinct_bases(bases)
    if len(distinct) > 1:
        return _skipped(product_key, cusip, BASES_DISAGREE), False
    if len(distinct) == 0:
        reason = MARKETS_UNAVAILABLE if market_failed else NO_VENUE_BASE
        return _skipped(product_key, cusip, reason), False
    if catalog is None:
        return _skipped(product_key, cusip, ASSET_LIST_UNAVAILABLE), False

    symbol = catalog.get(distinct[0].casefold())
    if symbol is None:
        return _skipped(product_key, cusip, f"{distinct[0]} is {NOT_ON_GLASSNODE}"), False
    return _insert(cache, product_key, cusip, glassnode_app_id, symbol)


def _exchange_xrefs(xrefs: Sequence[dict], exchange_ids: set[int]) -> list[dict]:
    rows: list[dict] = []
    for xref in xrefs:
        app_id = xref.get("app_id")
        if app_id is not None and int(app_id) in exchange_ids:
            rows.append(xref)
    return rows


def _bases(
    exchange_xrefs: Sequence[dict],
    markets_by_app: Mapping[int, Sequence[VenueMarket]],
    failed: set[int],
) -> tuple[list[str], bool]:
    bases: list[str] = []
    market_failed = False
    for xref in exchange_xrefs:
        app_id = int(xref["app_id"])
        if app_id in failed:
            market_failed = True
            continue
        base = venue_market_base(xref.get("vendor_symbol"), markets_by_app.get(app_id, ()))
        if base:
            bases.append(base)
    return bases, market_failed


def _distinct_bases(bases: Sequence[str]) -> list[str]:
    distinct: dict[str, str] = {}
    for base in bases:
        distinct.setdefault(base.casefold(), base)
    return list(distinct.values())


def _catalog(listed_symbols: Collection[object]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for symbol in _symbol_list(listed_symbols):
        catalog.setdefault(symbol.casefold(), symbol)
    return catalog


def _kept(product_id: int, cusip: str, vendor_symbol: str) -> GlassnodeXrefOutcome:
    return GlassnodeXrefOutcome(
        product_id=product_id,
        internal_cusip=cusip,
        vendor_symbol=vendor_symbol,
        skip_reason=None,
        wrote=False,
    )


def _skipped(product_id: int, cusip: str, reason: str) -> GlassnodeXrefOutcome:
    return GlassnodeXrefOutcome(
        product_id=product_id,
        internal_cusip=cusip,
        vendor_symbol=None,
        skip_reason=reason,
        wrote=False,
    )


def _insert(
    cache: InstrumentCache,
    product_id: int,
    cusip: str,
    glassnode_app_id: int,
    symbol: str,
) -> tuple[GlassnodeXrefOutcome, bool]:
    try:
        cache.sp_ins_product_xref(
            product_id=product_id,
            app_id=glassnode_app_id,
            vendor_symbol=symbol,
        )
    except ProcedureError as exc:
        if exc.sqlstate != _CURRENT_XREF_SQLSTATE:
            raise
        # The pass publishes its own writes once, at the end. This reload is
        # only so the outcome can name the row that won the race.
        cache.refresh()
        existing = cache.resolve_vendor_symbol(product_id, glassnode_app_id)
        if existing:
            return _kept(product_id, cusip, existing), False
        return _skipped(product_id, cusip, exc.message), False
    return (
        GlassnodeXrefOutcome(
            product_id=product_id,
            internal_cusip=cusip,
            vendor_symbol=symbol,
            skip_reason=None,
            wrote=True,
        ),
        True,
    )
