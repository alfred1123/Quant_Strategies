import math

import numpy as np
from pydantic import BaseModel


class RangeParam(BaseModel):
    min: float
    max: float
    step: float

    def to_values(self, as_int: bool = False) -> tuple:
        """Expand into a concrete value sequence for the optimizer."""
        if as_int:
            return tuple(range(int(self.min), int(self.max) + 1, int(self.step)))
        return tuple(np.arange(self.min, self.max + self.step / 2, self.step))


class FactorConfig(BaseModel):
    indicator: str
    strategy: str
    data_column: str = "price"
    window_range: RangeParam
    signal_range: RangeParam
    symbol: str | None = None          # internal_cusip for cross-product factor
    vendor_symbol: str | None = None   # direct vendor symbol override
    data_source: str | None = None     # per-factor data source override


# ── Requests ────────────────────────────────────────────────────────

class DataRequest(BaseModel):
    symbol: str
    start: str
    end: str


class OptimizeRequest(BaseModel):
    symbol: str
    start: str
    end: str
    mode: str  # "single" | "multi"
    trading_period: int
    fee_bps: float = 5.0
    data_source: str = "yahoo"  # REFDATA.APP.NAME
    # Single-factor
    indicator: str | None = None
    strategy: str | None = None
    window_range: RangeParam | None = None
    signal_range: RangeParam | None = None
    # Multi-factor
    conjunction: str | None = None
    factors: list[FactorConfig] | None = None
    # Walk-forward (run inline with optimization when True)
    walk_forward: bool = False
    split_ratio: float = 0.5


class PerformanceRequest(BaseModel):
    symbol: str
    start: str
    end: str
    mode: str
    trading_period: int
    fee_bps: float = 5.0
    data_source: str = "yahoo"  # REFDATA.APP.NAME
    # Single-factor
    indicator: str | None = None
    strategy: str | None = None
    window: int | None = None
    signal: float | None = None
    # Multi-factor
    conjunction: str | None = None
    factors: list[FactorConfig] | None = None
    windows: list[int] | None = None
    signals: list[float] | None = None


class WalkForwardRequest(OptimizeRequest):
    split_ratio: float = 0.5


# ── Responses ───────────────────────────────────────────────────────

class DataResponse(BaseModel):
    rows: int
    start_date: str
    end_date: str
    data: list[dict]


class EquityPoint(BaseModel):
    datetime: str
    cumu: float
    buy_hold_cumu: float
    dd: float
    buy_hold_dd: float


class PerformanceResponse(BaseModel):
    strategy_metrics: dict
    buy_hold_metrics: dict
    equity_curve: list[EquityPoint]
    perf_csv: str


class WalkForwardResponse(BaseModel):
    best_window: int | list[int]
    best_signal: float | list[float]
    is_metrics: dict
    oos_metrics: dict
    overfitting_ratio: float | None
    equity_curve: list[EquityPoint]
    split_date: str


class OptimizeResponse(BaseModel):
    total_trials: int
    valid: int
    best: dict
    top10: list[dict]
    grid: list[dict]
    optuna_plots: dict | None = None
    # Inline performance for best params (when available)
    performance: PerformanceResponse | None = None
    # Inline walk-forward (when walk_forward=True in request)
    walk_forward: WalkForwardResponse | None = None
