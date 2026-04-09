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

def _build_single_config(req) -> StrategyConfig:
    return StrategyConfig(
        ticker=req.symbol,
        indicator_name=req.indicator,
        signal_func=getattr(SignalDirection, req.strategy),
        trading_period=req.trading_period,
    )


def _build_multi_config(req) -> StrategyConfig:
    substrategies = []
    for f in req.factors:
        substrategies.append(SubStrategy(
            indicator_name=f.indicator,
            signal_func_name=f.strategy,
            window=0,
            signal=0.0,
            data_column=f.data_column,
        ))
    return StrategyConfig(
        ticker=req.symbol,
        indicator_name=req.factors[0].indicator,
        signal_func=getattr(SignalDirection, req.factors[0].strategy),
        trading_period=req.trading_period,
        conjunction=req.conjunction or "AND",
        substrategies=tuple(substrategies),
    )


def _resize_param_range(r, as_int=False):
    """Expand a RangeParam into a concrete value sequence for the optimizer."""
    if as_int:
        return tuple(range(int(r.min), int(r.max) + 1, int(r.step)))
    return tuple(np.arange(r.min, r.max + r.step / 2, r.step))


# ── Optimize ─────────────────────────────────────────────────────────────────

def run_optimize(req: OptimizeRequest, cache, callback=None) -> OptimizeResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
    callbacks = [callback] if callback else []

    if req.mode == "single":
        config = _build_single_config(req)
        window_list = _resize_param_range(req.window_range, as_int=True)
        signal_list = _resize_param_range(req.signal_range)
        opt = ParametersOptimization(df.copy(), config, fee_bps=req.fee_bps)
        result = opt.optimize(window_list, signal_list, callbacks=callbacks)
    else:
        config = _build_multi_config(req)
        window_ranges = [_resize_param_range(f.window_range, as_int=True) for f in req.factors]
        signal_ranges = [_resize_param_range(f.signal_range) for f in req.factors]
        opt = ParametersOptimization(df.copy(), config, fee_bps=req.fee_bps)
        result = opt.optimize_multi(window_ranges, signal_ranges, callbacks=callbacks)

    return OptimizeResponse(
        total_trials=len(result.grid_df),
        valid=result.n_valid,
        best=result.best,
        top10=result.top10,
        grid=result.grid,
        optuna_plots=_extract_optuna_plots(result.study, req),
    )


def _extract_optuna_plots(study, req: OptimizeRequest) -> dict | None:
    """Serialize optuna visualizations as Plotly JSON for the frontend."""
    if study is None:
        return None
    import optuna.visualization as optuna_vis
    import json

    plots = {}
    try:
        fig = optuna_vis.plot_optimization_history(study)
        plots["optimization_history"] = json.loads(fig.to_json())
    except Exception:
        pass
    try:
        fig = optuna_vis.plot_param_importances(study)
        plots["param_importances"] = json.loads(fig.to_json())
    except Exception:
        pass

    if req.mode == "single":
        try:
            fig = optuna_vis.plot_contour(study)
            plots["contour"] = json.loads(fig.to_json())
        except Exception:
            pass
    else:
        try:
            fig = optuna_vis.plot_parallel_coordinate(study)
            plots["parallel_coordinate"] = json.loads(fig.to_json())
        except Exception:
            pass
        for i in range(len(req.factors)):
            try:
                fig = optuna_vis.plot_contour(
                    study, params=[f"window_{i}", f"signal_{i}"])
                plots[f"contour_factor_{i}"] = json.loads(fig.to_json())
            except Exception:
                pass
    return plots or None


# ── Performance ───────────────────────────────────────────────────────────────

def run_performance(req: PerformanceRequest, cache) -> PerformanceResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)

    if req.mode == "single":
        config = _build_single_config(req)
        window = req.window
        signal = req.signal
    else:
        config = _build_multi_config(req)
        window = tuple(req.windows)
        signal = tuple(req.signals)

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

    if req.mode == "single":
        config = _build_single_config(req)
        window_list = _resize_param_range(req.window_range, as_int=True)
        signal_list = _resize_param_range(req.signal_range)
    else:
        config = _build_multi_config(req)
        window_list = [_resize_param_range(f.window_range, as_int=True) for f in req.factors]
        signal_list = [_resize_param_range(f.signal_range) for f in req.factors]

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

    # Normalize best_window/best_signal for JSON
    if isinstance(best_w, tuple):
        best_w_out = list(best_w)
        best_s_out = [float(s) for s in best_s]
    else:
        best_w_out = int(best_w)
        best_s_out = float(best_s)

    return WalkForwardResponse(
        best_window=best_w_out,
        best_signal=best_s_out,
        is_metrics=is_metrics,
        oos_metrics=oos_metrics,
        overfitting_ratio=ov_out,
        equity_curve=equity_curve,
        split_date=split_date,
    )
