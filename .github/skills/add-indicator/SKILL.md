---
name: add-indicator
description: 'Add a new technical analysis indicator to the backtest pipeline. Use when adding SMA, EMA, RSI, MACD, or any custom indicator to ta.py with tests and integration.'
argument-hint: 'Indicator name, e.g. MACD, VWAP, ATR'
---

# Add Technical Indicator

## When to Use
- Adding a new indicator to `scripts/backtest/ta.py`
- Extending the backtest pipeline with a new signal source

## Procedure

### 1. Implement the indicator

Add a method to `TechnicalAnalysis` in [ta.py](../../scripts/backtest/ta.py):

```python
def get_<name>(self, period):
    """
    Args:
        period (int): lookback window
    Returns:
        pd.Series: indicator values, same length as input, NaN-padded at start
    """
    # Implementation using self.data['factor'] column
    result = ...
    return result
```

**Requirements:**
- Input: `period` (int) — must match `indicator_func(window)` signature used by `Performance`
- Output: `pd.Series` — same length as `self.data`, NaN for insufficient data at start
- Operate on `self.data['factor']` column (or `'High'`/`'Low'`/`'Close'` if OHLC-based)
- Use pandas rolling/ewm operations — avoid row-by-row iteration

### 2. Add unit tests

Create tests in [tests/unit/test_ta.py](../../tests/unit/test_ta.py):

```python
class Test<Name>:
    def test_<name>_known_values(self, simple_factor_df):
        """Test against hand-calculated expected values."""

    def test_<name>_length_matches_input(self, sample_ohlc_df):
        """Output length must equal input length."""

    def test_<name>_leading_nans(self, simple_factor_df):
        """First (period-1) values should be NaN."""

    def test_<name>_value_bounds(self, sample_ohlc_df):
        """If indicator has known bounds (e.g. 0-100), assert them."""
```

### 3. Add integration test

Add a pipeline test in [tests/integration/test_backtest_pipeline.py](../../tests/integration/test_backtest_pipeline.py):

```python
def test_<name>_momentum_pipeline(self, synthetic_market_data):
    df = synthetic_market_data.copy()
    ta = TechnicalAnalysis(df)
    # Use 365 for crypto, 252 for equity
    perf = Performance(
        ta.data, 365, ta.get_<name>, Strategy.momentum_const_signal, <window>, <signal>
    )
    result = perf.get_strategy_performance()
    assert isinstance(result, pd.Series)
```

### 4. Verify

```bash
python -m pytest tests/ -v -k "<name>"
```

## Checklist
- [ ] Method added to `TechnicalAnalysis` with docstring
- [ ] Returns `pd.Series`, same length, NaN-padded
- [ ] Compatible with `Performance(indicator_func=ta.get_<name>)` signature
- [ ] Unit tests cover: known values, length, NaN padding, bounds
- [ ] Integration test runs full pipeline
- [ ] All tests pass
