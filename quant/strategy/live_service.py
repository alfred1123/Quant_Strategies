"""Live strategy evaluation — latest position for dry-run and executor.

Unlike :mod:`quant.strategy.backtest_service`, this module derives a rolling
lookback window and fetches fresh bars. Indicator math is
:class:`quant.strategy.performance.Performance` ``.compute_latest_position()``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import pandas as pd

from quant.data.backtest_cache import BacktestCache
from quant.refdata.bundle import DataCaches
from quant.schemas.backtest import OptimizeRequest
from quant.strategy.backtest_service import BacktestError, build_config, fetch_df
from quant.strategy.optimizer import extract_best_params
from quant.strategy.performance import (
    Performance,
    live_date_range,
    live_lookback_bars,
)
from quant.strategy.signals import StrategyConfig, config_from_json, params_from_strategy_json

logger = logging.getLogger(__name__)

#: ``(internal_cusip, lookback_bars) -> DataFrame`` — the interval and broker are
#: already bound by the caller, so this stays a two-argument call per symbol.
BarLoader = Callable[[str, int], pd.DataFrame]

#: ``internal_cusip -> DataFrame``. What `build_data_dict_for_signal` is given
#: once the window (dates or bar count) has been bound.
SymbolLoader = Callable[[str], pd.DataFrame]


class LiveEvaluationError(ValueError):
    """Live strategy evaluation failed (maps to HTTP 400 in dry-run)."""


def _default_data_source(internal_cusip: str) -> str:
    return "glassnode" if internal_cusip.endswith(".crypto") else "yahoo"


def _resolve_config_and_params(
    config_json: dict,
    result_payload: dict | None,
    refdata_cache: dict,
) -> tuple[StrategyConfig, object, object, OptimizeRequest | None]:
    if "factors" in config_json:
        req = OptimizeRequest.model_validate(config_json)
        config = build_config(req, refdata_cache)
        if result_payload is None or not result_payload.get("best"):
            raise LiveEvaluationError(
                "no optimization result found for strategy — run backtest first"
            )
        try:
            window, signal = extract_best_params(result_payload["best"])
        except ValueError as exc:
            raise LiveEvaluationError(
                f"result payload missing best params: {exc}"
            ) from exc
        return config, window, signal, req

    config = config_from_json(config_json)
    window, signal = params_from_strategy_json(config_json)
    return config, window, signal, None


def _data_sources(
    config: StrategyConfig,
    optimize_req: OptimizeRequest | None,
) -> dict[str, str]:
    """Provider to read each symbol from, keyed the way the config keys them.

    Only the provider path needs this — bars all come from one venue. Factors
    may override the request-level source, and the key must be
    ``vendor_symbol or symbol`` because that is what ``build_config`` writes
    onto the substrategy and therefore what ``Performance`` looks up.
    """
    if optimize_req is None:
        return {c: _default_data_source(c) for c in config.get_internal_cusips()}

    default = optimize_req.data_source
    sources = {config.internal_cusip: default}
    for factor in optimize_req.factors:
        cusip = factor.vendor_symbol or factor.symbol or config.internal_cusip
        sources.setdefault(cusip, factor.data_source or default)
    return sources


def build_data_dict_for_signal(
    config: StrategyConfig,
    load: SymbolLoader,
) -> dict[str, pd.DataFrame]:
    """One frame per symbol the strategy reads, keyed as ``Performance`` expects.

    The symbol set is ``StrategyConfig.get_internal_cusips()`` — the same
    accessor the backtest path resolves through — so live evaluation cannot
    disagree with the config about which series a strategy needs. Where those
    frames come from is entirely ``load``'s business, which is what lets the
    provider and price-bar paths share this function instead of drifting apart.

    The trade asset is loaded first so an unavailable primary fails before any
    factor work; the rest are sorted to keep the order deterministic.
    """
    primary = config.internal_cusip
    symbols = [primary] + sorted(config.get_internal_cusips() - {primary})

    data_dict = {cusip: load(cusip) for cusip in symbols}
    for cusip, df in data_dict.items():
        if df.empty:
            raise LiveEvaluationError(f"No data returned for {cusip!r}")
    return data_dict


def provider_loader(
    config: StrategyConfig,
    optimize_req: OptimizeRequest | None,
    *,
    start: str,
    end: str,
    cache: dict,
    inst_cache=None,
    bt_cache=None,
) -> SymbolLoader:
    """Load symbols from the strategy's configured data provider, by date."""
    sources = _data_sources(config, optimize_req)

    def load(cusip: str) -> pd.DataFrame:
        data_source = sources.get(cusip) or _default_data_source(cusip)
        try:
            return fetch_df(cusip, start, end, data_source, cache, inst_cache, bt_cache)
        except BacktestCache.CacheMissError:
            # Trade/dry-run must reach today's bar — refresh from the strategy's
            # configured data provider when the BT cache is stale or short.
            logger.info(
                "Cache miss for %s [%s, %s] — refreshing from provider for live eval",
                cusip, start, end,
            )
            return fetch_df(
                cusip, start, end, data_source,
                cache, inst_cache, bt_cache, refresh=True,
            )
        except BacktestError as exc:
            raise LiveEvaluationError(exc.detail) from exc

    return load


def bars_loader(bar_loader: BarLoader, lookback: int) -> SymbolLoader:
    """Load symbols from ``MARKET_DATA.PRICE_BAR``, by bar count.

    Every series comes from the exchange the deployment trades on, including
    factors: mixing an exchange series with a provider series would align bars
    that were never observed on the same clock. A symbol the exchange cannot
    supply raises out of ``bar_loader`` rather than falling back, because a
    silent fallback is exactly the mismatch this is avoiding.
    """
    return lambda cusip: bar_loader(cusip, lookback)


def compute_latest_position(
    config_json: dict | str,
    *,
    result_payload: dict | None,
    caches: DataCaches,
    bar_loader: BarLoader | None = None,
) -> tuple[float, str]:
    """Return ``(latest_position, data_as_of)`` for the frozen strategy config.

    ``bar_loader`` switches the series source to ``MARKET_DATA.PRICE_BAR``,
    which is what a scheduled deployment uses: its interval may be finer than a
    day, and the provider path can only address history by date.
    """
    if isinstance(config_json, str):
        doc = json.loads(config_json)
    elif isinstance(config_json, dict):
        doc = config_json
    else:
        raise LiveEvaluationError("strategy CONFIG_JSON must be a JSON object")

    cache = {
        "app": caches.refdata.get("app"),
        "indicator": caches.refdata.get("indicator"),
        "signal_type": caches.refdata.get("signal_type"),
    }
    config, window, signal, optimize_req = _resolve_config_and_params(
        doc, result_payload, cache,
    )
    if bar_loader is not None:
        lookback = live_lookback_bars(window)
        load = bars_loader(bar_loader, lookback)
        window_desc = f"{lookback} bars"
    else:
        start, end = live_date_range(window, config.trading_period)
        load = provider_loader(
            config,
            optimize_req,
            start=start,
            end=end,
            cache=cache,
            inst_cache=caches.instrument_cache,
            bt_cache=caches.backtest_cache,
        )
        window_desc = f"{start} → {end}"
    data_dict = build_data_dict_for_signal(config, load)
    try:
        position, as_of = Performance(
            data_dict, config, window, signal,
        ).compute_latest_position()
    except ValueError as exc:
        raise LiveEvaluationError(str(exc)) from exc

    logger.info(
        "Computed live position=%s as_of=%s for %s (lookback %s)",
        position,
        as_of,
        config.internal_cusip,
        window_desc,
    )
    return position, as_of
