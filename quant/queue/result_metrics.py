"""Map backtest performance dicts to BT.RESULT shredded columns."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Keys on performance.strategy_metrics / performance.buy_hold_metrics
_TOTAL_RETURN = "Total Return"
_ANNUALIZED_RETURN = "Annualized Return"
_SHARPE_RATIO = "Sharpe Ratio"
_MAX_DRAWDOWN = "Max Drawdown"
_CALMAR_RATIO = "Calmar Ratio"


def _metric_value(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        val = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return val


def _read_metrics(metrics: dict | None) -> tuple[float | None, ...]:
    src = metrics or {}
    return (
        _metric_value(src.get(_TOTAL_RETURN)),
        _metric_value(src.get(_ANNUALIZED_RETURN)),
        _metric_value(src.get(_SHARPE_RATIO)),
        _metric_value(src.get(_MAX_DRAWDOWN)),
        _metric_value(src.get(_CALMAR_RATIO)),
    )


@dataclass(frozen=True)
class ShreddedResultMetrics:
    """Strategy + buy-and-hold metrics passed to BT.SP_INS_RESULT."""

    total_return: float | None
    annualized_return: float | None
    sharpe_ratio: float | None
    max_drawdown: float | None
    calmar_ratio: float | None
    buy_hold_total_return: float | None
    buy_hold_annualized_return: float | None
    buy_hold_sharpe_ratio: float | None
    buy_hold_max_drawdown: float | None
    buy_hold_calmar_ratio: float | None


def extract_shredded_metrics(payload: dict) -> ShreddedResultMetrics:
    """Read shredded column values from an optimize result payload."""
    perf = payload.get("performance") or {}
    strat = _read_metrics(perf.get("strategy_metrics"))
    bh = _read_metrics(perf.get("buy_hold_metrics"))
    return ShreddedResultMetrics(
        total_return=strat[0],
        annualized_return=strat[1],
        sharpe_ratio=strat[2],
        max_drawdown=strat[3],
        calmar_ratio=strat[4],
        buy_hold_total_return=bh[0],
        buy_hold_annualized_return=bh[1],
        buy_hold_sharpe_ratio=bh[2],
        buy_hold_max_drawdown=bh[3],
        buy_hold_calmar_ratio=bh[4],
    )
