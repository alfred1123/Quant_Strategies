import numpy as np
from pydantic import BaseModel, Field


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
    """One factor in a backtest.

    Where the indicator reads from is fully described on the factor
    itself — never inferred from the request-level ``symbol`` (which is
    the *trade* asset). Set ``symbol`` (internal CUSIP, e.g.
    ``"vix.equity_us"``) and/or ``vendor_symbol`` (direct override,
    e.g. ``"^VIX"``) to read the indicator from a different product
    than the trade asset (cross-product / pair-trade signals).
    """

    # Where the indicator reads from
    symbol: str | None = None          # internal_cusip for cross-product factor
    vendor_symbol: str | None = None   # direct vendor symbol override
    data_source: str | None = None     # per-factor data source override
    data_column: str = "price"

    # What the indicator computes
    indicator: str
    strategy: str
    window_range: RangeParam
    signal_range: RangeParam


# ── Requests ────────────────────────────────────────────────────────
#
# Backtest requests are uniformly factor-list shaped. A "single factor"
# strategy is just a 1-element ``factors`` list — there is no separate
# top-level indicator/window/signal branch. This keeps cross-product
# semantics (factor on a different symbol than the trade asset)
# available regardless of factor count.

class DataRequest(BaseModel):
    symbol: str
    start: str
    end: str


class OptimizeRequest(BaseModel):
    symbol: str
    start: str
    end: str
    trading_period: int
    fee_bps: float = 5.0
    data_source: str = "yahoo"  # REFDATA.APP.NAME
    # Cache control — when True, refetch every product+factor from the
    # provider and insert a new BT.API_REQUEST version. When False
    # (default), serve from cache only and 400 on miss.
    refresh_dataset: bool = False
    factors: list[FactorConfig] = Field(min_length=1)
    # ``conjunction`` is only meaningful when len(factors) >= 2 — it is
    # how the per-factor positions are combined ("AND" / "OR" / "FILTER").
    # For a 1-factor request it must be ``None`` (sent or omitted is
    # equivalent); leaving it required would force callers to send a
    # nonsensical value for the single-factor case.
    conjunction: str | None = None
    # Walk-forward (run inline with optimization when True)
    walk_forward: bool = False
    split_ratio: float = 0.5


class PerformanceRequest(BaseModel):
    symbol: str
    start: str
    end: str
    trading_period: int
    fee_bps: float = 5.0
    data_source: str = "yahoo"  # REFDATA.APP.NAME
    # See OptimizeRequest.refresh_dataset.
    refresh_dataset: bool = False
    factors: list[FactorConfig] = Field(min_length=1)
    conjunction: str | None = None
    # One value per factor (same order as ``factors``). Selected by the
    # caller from a top-10 row after running /optimize.
    windows: list[int] = Field(min_length=1)
    signals: list[float] = Field(min_length=1)


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
