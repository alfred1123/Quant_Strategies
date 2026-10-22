"""Replace the stored series for providers the checkbox does not call.

``REFDATA.APP.REFRESH_DATASET_IND = N`` on a non-exchange app means the
drawer must not hit that vendor. This pass does, once a day, through the
same ``fetch_df`` insert a refresh uses. An exchange is skipped: its bars
already live in ``MARKET_DATA.PRICE_BAR``.

Each call is one catalog metric for one product that has a vendor symbol
for that app. The window is ``since`` through today, and the insert
replaces that whole window. Before that read, a product whose exchange
listings agree on one base is given a provider xref when the provider's
asset list contains that base. The fetch then uses
``InstrumentCache.resolve_internal_cusip``, the same read as every other app.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from quant.shared.db import ProcedureError

logger = logging.getLogger(__name__)


@dataclass
class FillReport:
    """How many series were stored, and which ones failed."""

    filled: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


NOT_A_LISTED_ASSET = "not a listed asset"
NO_VENUE_BASE = "no venue market base"
BASES_DISAGREE = "venue market bases disagree"
MARKETS_UNAVAILABLE = "venue markets unavailable"
ASSET_LIST_UNAVAILABLE = "provider asset list unavailable"


@dataclass(frozen=True)
class ExchangeListing:
    """One ccxt xref, after that venue's market table has been asked.

    ``markets_unavailable`` means the table could not be read. ``base`` is
    then absent. The vendor symbol is not parsed into a base, and the
    internal CUSIP is not an input.
    """

    vendor_symbol: str | None
    base: str | None
    markets_unavailable: bool = False


@dataclass(frozen=True)
class ProviderSymbolDecision:
    """Whether the fill should insert a provider xref for one product.

    ``write`` is true only when ``vendor_symbol`` should be inserted. An
    existing row has ``write`` false, the stored symbol, and no skip reason.
    The fetch reads that row through ``InstrumentCache.resolve_internal_cusip``.
    """

    vendor_symbol: str | None
    write: bool
    skip_reason: str | None


def resolve_provider_symbol(
    listings: Sequence[ExchangeListing],
    *,
    listed_symbols: Collection[str] | None,
    existing_symbol: str | None,
) -> ProviderSymbolDecision:
    """Decide the provider vendor symbol from the exchange listings.

    The symbol is the venue market base (``BTCUSDT`` → ``BTC``), kept only
    when ``listed_symbols`` contains it. The stored spelling is the list's.
    ``listed_symbols`` None means the catalog could not be read, and nothing
    is proposed. An empty collection means the provider lists nothing. An
    existing symbol is left as-is, including one this rule would not choose.
    """
    if existing_symbol:
        return ProviderSymbolDecision(existing_symbol, write=False, skip_reason=None)
    if not listings:
        return _skip(NO_VENUE_BASE)

    bases: list[str] = []
    market_failed = False
    for listing in listings:
        if listing.markets_unavailable:
            market_failed = True
            continue
        base = (listing.base or "").strip()
        if base:
            bases.append(base)

    distinct = _distinct_bases(bases)
    if len(distinct) > 1:
        return _skip(BASES_DISAGREE)
    if len(distinct) == 0:
        return _skip(MARKETS_UNAVAILABLE if market_failed else NO_VENUE_BASE)
    if listed_symbols is None:
        return _skip(ASSET_LIST_UNAVAILABLE)

    catalog = _asset_catalog(listed_symbols)
    symbol = catalog.get(distinct[0].casefold())
    if symbol is None:
        return _skip(f"{distinct[0]} is {NOT_A_LISTED_ASSET}")
    return ProviderSymbolDecision(symbol, write=True, skip_reason=None)


def _distinct_bases(bases: Sequence[str]) -> list[str]:
    distinct: dict[str, str] = {}
    for base in bases:
        distinct.setdefault(base.casefold(), base)
    return list(distinct.values())


def _asset_catalog(listed_symbols: Collection[str]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for symbol in listed_symbols:
        if not isinstance(symbol, str):
            continue
        cleaned = symbol.strip()
        if cleaned:
            catalog.setdefault(cleaned.casefold(), cleaned)
    return catalog


def _skip(reason: str) -> ProviderSymbolDecision:
    return ProviderSymbolDecision(None, write=False, skip_reason=reason)


def scheduled_provider_apps(apps: list[dict]) -> list[dict]:
    """Non-exchange apps whose Refresh dataset checkbox is off."""
    return [
        app for app in apps
        if app.get("is_exchange_ind") != "Y" and app.get("refresh_dataset_ind") == "N"
    ]


_CURRENT_XREF_SQLSTATE = "23505"


def listed_asset_symbols(app: dict) -> Collection[str] | None:
    """Assets the provider class lists, or None when that read cannot be used.

    None is not an empty catalog. Only :class:`quant.data.sources.Glassnode`
    lists assets. Any other source class has no catalog, so no xref is
    proposed. A failed read is the same outcome. The traceback is logged.
    """
    class_name = app.get("class_name")
    if not class_name:
        return None
    import quant.data.sources as sources

    if getattr(sources, class_name, None) is not sources.Glassnode:
        return None
    try:
        return sources.Glassnode().list_asset_symbols()
    except Exception:
        logger.exception("provider asset list unavailable for %s", app.get("name"))
        return None


def _load_markets(
    exchange_app_ids: Collection[int],
    markets_for_app: Callable[[int], Sequence[tuple[str, str | None]] | None],
) -> tuple[dict[int, list[tuple[str, str | None]]], set[int]]:
    loaded: dict[int, list[tuple[str, str | None]]] = {}
    failed: set[int] = set()
    for app_id in exchange_app_ids:
        app_key = int(app_id)
        try:
            markets = markets_for_app(app_key)
        except Exception:
            logger.exception("venue markets unavailable for app_id=%s", app_key)
            failed.add(app_key)
            continue
        if markets is None:
            failed.add(app_key)
            continue
        loaded[app_key] = list(markets)
    return loaded, failed


def _listing_for(
    vendor_symbol: str | None,
    markets: Sequence[tuple[str, str | None]],
    *,
    unavailable: bool,
) -> ExchangeListing:
    if unavailable:
        return ExchangeListing(vendor_symbol, None, True)
    for symbol, base in markets:
        if symbol != vendor_symbol:
            continue
        cleaned = (base or "").strip()
        return ExchangeListing(vendor_symbol, cleaned or None, False)
    return ExchangeListing(vendor_symbol, None, False)


def _write_missing_symbols(
    inst_cache,
    app: dict,
    *,
    exchange_ids: set[int],
    markets_by_app: dict[int, list[tuple[str, str | None]]],
    failed_app_ids: set[int],
    listed_symbols: Collection[str] | None,
) -> None:
    """Insert a provider xref where the exchange base is on the asset list.

    An existing row is left alone. One refresh follows the writes so the
    fetch below sees them through the same cache read as a row that was
    already there. A unique violation means another writer won; the refresh
    picks up that row.
    """
    app_id = int(app["app_id"])
    wrote = False
    for product in inst_cache.get_products():
        product_id = int(product["product_id"])
        exchange_xrefs = [
            xref for xref in inst_cache.get_xrefs(product_id=product_id)
            if xref.get("app_id") is not None and int(xref["app_id"]) in exchange_ids
        ]
        if not exchange_xrefs:
            continue
        listings = [
            _listing_for(
                xref.get("vendor_symbol"),
                markets_by_app.get(int(xref["app_id"]), ()),
                unavailable=int(xref["app_id"]) in failed_app_ids,
            )
            for xref in exchange_xrefs
        ]
        decision = resolve_provider_symbol(
            listings,
            listed_symbols=listed_symbols,
            existing_symbol=inst_cache.resolve_vendor_symbol(product_id, app_id),
        )
        if not decision.write or not decision.vendor_symbol:
            if decision.skip_reason:
                logger.info(
                    "provider symbol skipped %s %s: %s",
                    app.get("name"), product.get("internal_cusip"), decision.skip_reason,
                )
            continue
        try:
            inst_cache.sp_ins_product_xref(
                product_id=product_id,
                app_id=app_id,
                vendor_symbol=decision.vendor_symbol,
            )
        except ProcedureError as exc:
            if exc.sqlstate != _CURRENT_XREF_SQLSTATE:
                logger.warning(
                    "provider symbol was not written %s %s: %s",
                    app.get("name"), product.get("internal_cusip"), exc.message,
                )
                continue
            logger.info(
                "provider symbol already present %s %s",
                app.get("name"), product.get("internal_cusip"),
            )
        else:
            logger.info(
                "provider symbol wrote %s %s %s",
                app.get("name"), product.get("internal_cusip"), decision.vendor_symbol,
            )
        wrote = True
    if wrote:
        inst_cache.refresh()


def fill_scheduled_providers(
    refdata,
    inst_cache,
    bt_cache,
    *,
    since: date,
    exchange_app_ids: Collection[int],
    markets_for_app: Callable[[int], Sequence[tuple[str, str | None]] | None],
    today: date | None = None,
) -> FillReport:
    """Fetch and insert every scheduled provider series from *since* through *today*.

    ``exchange_app_ids`` are the ccxt venues whose market base can become a
    provider symbol. ``markets_for_app`` returns ``(vendor_symbol, base)``
    pairs, or None when that venue's table could not be read.
    """
    end = today if today is not None else datetime.now(UTC).date()
    start_s = since.isoformat()
    end_s = end.isoformat()
    report = FillReport()
    metrics = refdata.get("app_metric")
    markets_by_app, failed_app_ids = _load_markets(exchange_app_ids, markets_for_app)
    exchange_ids = {int(app_id) for app_id in exchange_app_ids}

    for app in scheduled_provider_apps(refdata.get("app")):
        _write_missing_symbols(
            inst_cache,
            app,
            exchange_ids=exchange_ids,
            markets_by_app=markets_by_app,
            failed_app_ids=failed_app_ids,
            listed_symbols=listed_asset_symbols(app),
        )
        app_id = int(app["app_id"])
        app_metrics = [
            row for row in metrics
            if int(row["app_id"]) == app_id and row.get("metric_path")
        ]
        for xref in inst_cache.get_xrefs(app_id=app_id):
            product = inst_cache.get_product_by_id(xref["product_id"])
            if product is None:
                continue
            cusip = product["internal_cusip"]
            for metric in app_metrics:
                metric_nm = metric["metric_nm"]
                try:
                    from quant.strategy.backtest_service import fetch_df

                    fetch_df(
                        cusip, start_s, end_s, app["name"], refdata, inst_cache, bt_cache,
                        refresh=True,
                        tm_interval_id=bt_cache.default_tm_interval_id(),
                        metric_nm=metric_nm,
                    )
                except Exception as exc:
                    report.failed += 1
                    message = f"{app['name']} {metric_nm} {cusip}: {exc}"
                    report.errors.append(message)
                    logger.warning("scheduled provider fill failed: %s", message)
                    continue
                report.filled += 1
                logger.info(
                    "scheduled provider fill stored %s %s %s [%s, %s]",
                    app["name"], metric_nm, cusip, start_s, end_s,
                )
    return report
