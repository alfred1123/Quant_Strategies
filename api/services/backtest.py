"""Service layer that bridges FastAPI requests to src/ backtest modules.

All heavy lifting is delegated to the existing pipeline modules.
This layer handles DataFrame ↔ dict conversion and config construction.
"""

import asyncio
import json
import logging
import math
import queue
import threading

import numpy as np
import pandas as pd

import src.data as _data_module
from src.strat import SignalDirection, StrategyConfig, SubStrategy, resolve_signal_func
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
        **{col: price[col] for col in ("Open", "High", "Low", "Close", "Volume")
           if col in price.columns},
    })


# ── Config builders ──────────────────────────────────────────────────────────
#
# Strategy/indicator names come from REFDATA-driven UI dropdowns, so they are
# already constrained to valid values. getattr raises AttributeError if
# an unknown name is sent directly to the API — no extra validation needed.

def _build_config(req, cache) -> StrategyConfig:
    indicator_rows = cache.get("indicator")
    signal_type_rows = cache.get("signal_type")

    if req.mode == "single":
        func = resolve_signal_func(
            req.strategy, req.indicator, indicator_rows, signal_type_rows,
        )
        return StrategyConfig(
            ticker=req.symbol,
            indicator_name=req.indicator,
            signal_func=func,
            trading_period=req.trading_period,
        )
    substrategies = [
        SubStrategy(
            indicator_name=f.indicator,
            signal_func_name=resolve_signal_func(
                f.strategy, f.indicator, indicator_rows, signal_type_rows,
            ).__name__,
            window=0,
            signal=0.0,
            data_column=f.data_column,
        )
        for f in req.factors
    ]
    first_func = resolve_signal_func(
        req.factors[0].strategy, req.factors[0].indicator,
        indicator_rows, signal_type_rows,
    )
    return StrategyConfig(
        ticker=req.symbol,
        indicator_name=req.factors[0].indicator,
        signal_func=first_func,
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
    config = _build_config(req, cache)
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


def _compute_total_trials(req: OptimizeRequest) -> int:
    """Pre-compute the number of trials that optuna will run."""
    from src.param_opt import OPTUNA_MAX_TRIALS
    if req.mode == "single":
        w = req.window_range.to_values(as_int=True)
        s = req.signal_range.to_values()
        total = len(w) * len(s)
    else:
        total = math.prod(
            len(f.window_range.to_values(as_int=True)) * len(f.signal_range.to_values())
            for f in req.factors
        )
    return min(total, OPTUNA_MAX_TRIALS)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_optimize(req: OptimizeRequest, cache):
    """Async generator yielding SSE events for optimization progress.

    Events:
        init     — {total: int}                           (before first trial)
        progress — {trial, total, best_sharpe}             (after each trial)
        result   — full OptimizeResponse dict               (on completion)
        error    — {detail: str}                            (on failure)
    """
    progress_q: queue.Queue = queue.Queue()
    total = _compute_total_trials(req)

    def _run():
        try:
            df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
            config = _build_config(req, cache)
            window_list, signal_list = _build_param_ranges(req)

            def on_trial(study, trial):
                best = study.best_value if study.best_value > float("-inf") else None
                progress_q.put(("progress", {
                    "trial": trial.number + 1,
                    "total": total,
                    "best_sharpe": round(best, 4) if best is not None else None,
                }))

            opt = ParametersOptimization(df.copy(), config, fee_bps=req.fee_bps)
            result = opt.run(window_list, signal_list, callbacks=[on_trial])

            resp = OptimizeResponse(
                total_trials=len(result.grid_df),
                valid=result.n_valid,
                best=result.best,
                top10=result.top10,
                grid=result.grid,
                optuna_plots=result.extract_plots(),
            )
            progress_q.put(("result", resp.model_dump()))
        except Exception as exc:
            logger.exception("Streaming optimization failed")
            progress_q.put(("error", {"detail": str(exc)}))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    yield _sse_event("init", {"total": total})

    while True:
        try:
            event_type, data = await asyncio.to_thread(progress_q.get, timeout=600)
        except Exception:
            yield _sse_event("error", {"detail": "Optimization timed out"})
            return

        yield _sse_event(event_type, data)

        if event_type in ("result", "error"):
            return


# ── Performance ───────────────────────────────────────────────────────────────

def run_performance(req: PerformanceRequest, cache) -> PerformanceResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
    config = _build_config(req, cache)
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

    perf_csv = perf.data.to_csv(index=False)

    return PerformanceResponse(
        strategy_metrics=strat_metrics,
        buy_hold_metrics=bh_metrics,
        equity_curve=equity_curve,
        perf_csv=perf_csv,
    )


# ── Walk-Forward ──────────────────────────────────────────────────────────────

def run_walk_forward(req: WalkForwardRequest, cache) -> WalkForwardResponse:
    df = _fetch_df(req.symbol, req.start, req.end, req.data_source, cache)
    config = _build_config(req, cache)
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
