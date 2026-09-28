"""Invalid parameter grids are rejected before a run expands them."""

import pytest
from pydantic import ValidationError

from quant.schemas.backtest import FactorConfig, RangeParam


def _factor(window: RangeParam, signal: RangeParam | None = None) -> FactorConfig:
    return FactorConfig(
        indicator="get_ema",
        strategy="momentum",
        window_range=window,
        signal_range=signal or RangeParam(min=-1.0, max=1.0, step=0.5),
    )


def test_window_zero_is_rejected():
    with pytest.raises(ValidationError, match="window must be at least 2"):
        _factor(RangeParam(min=0, max=20, step=5))


def test_negative_window_is_rejected():
    with pytest.raises(ValidationError, match="window must be at least 2"):
        _factor(RangeParam(min=-5, max=20, step=5))


def test_window_one_is_rejected():
    with pytest.raises(ValidationError, match="window must be at least 2"):
        _factor(RangeParam(min=1, max=10, step=1))


def test_step_zero_is_rejected():
    with pytest.raises(ValidationError, match="greater than 0"):
        RangeParam(min=2, max=20, step=0)


def test_max_below_min_is_rejected():
    with pytest.raises(ValidationError, match="max must be >= min"):
        RangeParam(min=10, max=2, step=1)


def test_valid_range_keeps_a_signal_below_two():
    window = RangeParam(min=2, max=10, step=2)
    signal = RangeParam(min=-1.0, max=1.0, step=0.5)
    factor = _factor(window, signal)
    assert factor.window_range.to_values(as_int=True) == (2, 4, 6, 8, 10)
    assert factor.signal_range.min == -1.0
