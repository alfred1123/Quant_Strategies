"""Service layer that bridges FastAPI requests to src/ backtest modules.

All heavy lifting is delegated to the existing pipeline modules.
This layer handles DataFrame ↔ dict conversion and config construction.
"""

import logging

import numpy as np
import pandas as pd

import src.data as _data_module
from src.strat import SignalDirection, StrategyConfig, SubStrategy
from src.perf import Performance
from src.param_opt import ParametersOptimization
from src.walk_forward import WalkForward

from api.schemas.backtest import (
    OptimizeRequest, PerformanceRequest, WalkForwardRequest,
    OptimizeResponse, PerformanceResponse, WalkForwardResponse,
    EquityPoint,
)

logger = logging.getLogger(__name__)

# ── Data fetching ────────────────────────────────────────────────────────────

def _fetch_df(symbol: str, start: str, end: str, data_source: str, cache) -> pd.DataFrame:
    """Fetch prices using the data source class registered in REFDATA.APP."""
    app_rows = {row["name"]: row for row in cache.get("app")}
    app = app_rows.get(data_source)
    if app is None:
        raise ValueError(f"Unknown data source: {data_source!r}. Check REFDATA.APP.")
    cls = getattr(_data_module, app["class_name"])
    src = cls()
    price = src.get_historical_price(symbol, start, end)
    if hasattr(src.get_historical_price, "cache_clear"):
        src.get_historical_price.cache_clear()
    return pd.DataFrame({
        "datetime": price["t"],
        "price": price["v"],
        "factor": price["v"],
    })


# ── Config builders ──────────────────────────────────────────────────────────
#
# Strategy/indicator names come from REFDATA-driven UI dropdowns, so they are
# already constrained to valid values. getattr raises AttributeError if
# an unknown name is sent directly to the API — no extra validation needed.

def _build_config(req) -> StrategyConfig:
    if req.mode == "single":
        return StrategyConfig(
            ticker=req.symbol,
            indicator_name=req.indicator,
            signal_func=getattr(SignalDirection, req.strategy),
            trading_period=req.trading_period,
        )
    substrategies = [
        SubStrategy(
            indicator_name=f.indicator,
            signal_func_name=f.strategy,
            window=0,
            signal=0.0,
            data_column=f.data_column,
        )
        for f in req.factors
    ]
    return StrategyConfig(
        ticker=req.symbol,
        indicator_name=req.factors[0].indicator,
        signal_func=getattr(SignalDirection, req.factors[0].strategy),
        trading_period=req.trading_period,
        conjunction=req.conjunction or "AND",
        substrategies=tuple(substrategies),
    )


def _build_param_ranges(req):
    """Return (window_list, signal_list) shaped for ParametersOptimization.run() / WalkForward.run().

    Single mode: flat tuples.
    Multi mode: lists of tuples, one per factor.
    """
    if req.mode == "single":
        return (
            req.window_range.to_values(as_int=True),
            req.signal_range.to_values(),
        )
    return (
        [f.window_range.to_values(as_int=True) for f in req.factors],
        [f.signal_range.to_values() for f in req.factors],
    )


# ── Optimize ─────────────────────────────────────────────────────────────────

def run_optimize(req: OptimizeRequest, cache, callback=None) -> OptimizeResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
    callbacks = [callback] if callback else []
    config = _build_config(req)
    window_list, signal_list = _build_param_ranges(req)
    opt = ParametersOptimization(df.copy(), config, fee_bps=req.fee_bps)
    result = opt.run(window_list, signal_list, callbacks=callbacks)

    return OptimizeResponse(
        total_trials=len(result.grid_df),
        valid=result.n_valid,
        best=result.best,
        top10=result.top10,
        grid=result.grid,
        optuna_plots=result.extract_plots(),
    )


# ── Performance ───────────────────────────────────────────────────────────────

def run_performance(req: PerformanceRequest, cache) -> PerformanceResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
    config = _build_config(req)
    window = req.window if req.mode == "single" else tuple(req.windows)
    signal = req.signal if req.mode == "single" else tuple(req.signals)

    perf = Performance(df.copy(), config, window, signal, fee_bps=req.fee_bps)
    perf.enrich_performance()

    strat_metrics = perf.get_strategy_performance().replace({np.nan: None}).to_dict()
    bh_metrics = perf.get_buy_hold_performance().replace({np.nan: None}).to_dict()

    chart_df = perf.data.dropna(subset=["cumu"])
    equity_curve = [
        EquityPoint(
            datetime=str(row["datetime"]),
            cumu=float(row["cumu"]),
            buy_hold_cumu=float(row["buy_hold_cumu"]),
            dd=float(row["dd"]),
            buy_hold_dd=float(row["buy_hold_dd"]),
        )
        for _, row in chart_df.iterrows()
    ]

    return PerformanceResponse(
        strategy_metrics=strat_metrics,
        buy_hold_metrics=bh_metrics,
        equity_curve=equity_curve,
    )


# ── Walk-Forward ──────────────────────────────────────────────────────────────

def run_walk_forward(req: WalkForwardRequest, cache) -> WalkForwardResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
    config = _build_config(req)
    window_list, signal_list = _build_param_ranges(req)

    wf = WalkForward(df.copy(), req.split_ratio, config, fee_bps=req.fee_bps)
    result = wf.run(window_list, signal_list)

    # Build equity curve from the full-period data stored in WalkForwardResult
    best_w = result.best_window
    best_s = result.best_signal
    chart_df = result.full_equity_df.dropna(subset=["cumu"]) if result.full_equity_df is not None else pd.DataFrame()

    split_date = str(chart_df["datetime"].iloc[wf.split_idx]) if wf.split_idx < len(chart_df) else ""

    equity_curve = [
        EquityPoint(
            datetime=str(row["datetime"]),
            cumu=float(row["cumu"]),
            buy_hold_cumu=float(row["buy_hold_cumu"]),
            dd=float(row["dd"]),
            buy_hold_dd=float(row["buy_hold_dd"]),
        )
        for _, row in chart_df.iterrows()
    ]

    is_metrics = result.is_metrics.replace({np.nan: None}).to_dict()
    oos_metrics = result.oos_metrics.replace({np.nan: None}).to_dict()
    ov = result.overfitting_ratio
    ov_out = None if (ov is None or (isinstance(ov, float) and np.isnan(ov))) else float(ov)

    # Pydantic expects list[int]/list[float] for multi-factor, not tuple
    best_w_out = list(best_w) if isinstance(best_w, tuple) else best_w
    best_s_out = list(best_s) if isinstance(best_s, tuple) else best_s

    return WalkForwardResponse(
        best_window=best_w_out,
        best_signal=best_s_out,
        is_metrics=is_metrics,
        oos_metrics=oos_metrics,
        overfitting_ratio=ov_out,
        equity_curve=equity_curve,
        split_date=split_date,
    )
