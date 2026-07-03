"""Live strategy evaluation — latest position for dry-run and executor.

Unlike :mod:`quant.strategy.backtest_service`, this module derives a rolling
lookback window and fetches fresh bars. Indicator math is
:class:`quant.strategy.performance.Performance` ``._compute_latest_position()``.
"""

from __future__ import annotations

import json
import logging

import pandas as pd

from quant.data.backtest_cache import BacktestCache
from quant.refdata.bundle import DataCaches
from quant.schemas.backtest import OptimizeRequest
from quant.strategy.backtest_service import BacktestError, _build_config, _fetch_df
from quant.strategy.optimizer import extract_best_params
from quant.strategy.performance import Performance, _live_date_range
from quant.strategy.signals import StrategyConfig, config_from_json, params_from_strategy_json

logger = logging.getLogger(__name__)


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
        config = _build_config(req, refdata_cache)
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


def build_data_dict_for_signal(
    config: StrategyConfig,
    optimize_req: OptimizeRequest | None,
    *,
    start: str,
    end: str,
    cache: dict,
    inst_cache=None,
    bt_cache=None,
) -> dict[str, pd.DataFrame]:
    """Fetch product + factor bars for live position evaluation."""
    symbol = config.internal_cusip
    default_ds = (
        optimize_req.data_source
        if optimize_req is not None
        else _default_data_source(symbol)
    )
    if optimize_req is not None:
        pairs: list[tuple[str, str | None]] = [(symbol, optimize_req.data_source)]
        for factor in optimize_req.factors:
            cusip = factor.symbol or symbol
            if cusip not in {p[0] for p in pairs}:
                pairs.append((cusip, factor.data_source))
    else:
        pairs = [(symbol, _default_data_source(symbol))]
        for sub in config.get_substrategies():
            if sub.internal_cusip and sub.internal_cusip not in {p[0] for p in pairs}:
                pairs.append((sub.internal_cusip, _default_data_source(sub.internal_cusip)))

    data_dict: dict[str, pd.DataFrame] = {}
    for cusip, ds_override in pairs:
        if cusip in data_dict:
            continue
        try:
            data_dict[cusip] = _fetch_df(
                cusip, start, end, ds_override or default_ds,
                cache, inst_cache, bt_cache,
            )
        except BacktestError as exc:
            raise LiveEvaluationError(exc.detail) from exc
        except BacktestCache.CacheMissError as exc:
            raise LiveEvaluationError(str(exc)) from exc

    for sym, df in data_dict.items():
        if df.empty:
            raise LiveEvaluationError(f"No data returned for {sym!r}")
    return data_dict


def compute_latest_position(
    config_json: dict | str,
    *,
    result_payload: dict | None,
    caches: DataCaches,
) -> tuple[float, str]:
    """Return ``(latest_position, data_as_of)`` for the frozen strategy config."""
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
    start, end = _live_date_range(window, config.trading_period)
    data_dict = build_data_dict_for_signal(
        config,
        optimize_req,
        start=start,
        end=end,
        cache=cache,
        inst_cache=caches.instrument_cache,
        bt_cache=caches.backtest_cache,
    )
    try:
        position, as_of = Performance(
            data_dict, config, window, signal,
        )._compute_latest_position()
    except ValueError as exc:
        raise LiveEvaluationError(str(exc)) from exc

    logger.info(
        "Computed live position=%s as_of=%s for %s (lookback %s → %s)",
        position,
        as_of,
        config.internal_cusip,
        start,
        end,
    )
    return position, as_of
