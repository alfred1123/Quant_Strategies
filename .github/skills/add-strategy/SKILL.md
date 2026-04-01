---
name: add-strategy
description: 'Add a new trading strategy to the backtest pipeline. Use when creating momentum, reversion, mean-reversion, breakout, or custom signal generation logic in strat.py with tests.'
argument-hint: 'Strategy name, e.g. breakout, mean-reversion-band'
---

# Add Trading Strategy

## When to Use
- Adding a new signal generation strategy to `scripts/backtest/strat.py`
- Creating a new position-sizing or signal logic

## Procedure

### 1. Implement the strategy

Add a static method to `Strategy` in [strat.py](../../scripts/backtest/strat.py):

```python
def <name>_signal(data_col, signal):
    """
    Args:
        data_col: indicator values (numpy array or pd.Series)
        signal: threshold parameter
    Returns:
        numpy array of float: positions {-1.0, 0.0, 1.0}, NaN where input is NaN
    """
    position = np.where(<long_condition>, 1, np.where(<short_condition>, -1, 0))
    position = position.astype(float)
    position[np.isnan(data_col)] = np.nan
    return position
```

**Requirements:**
- Signature: `(data_col, signal)` — must match `strategy_func(data['indicator'], signal)` used by `Performance`
- Output: numpy float array of `{-1.0, 0.0, 1.0}`
- Propagate NaN from input (set `position[np.isnan(data_col)] = np.nan`)
- Use vectorized numpy operations — no loops

### 2. Add unit tests

Create tests in [tests/unit/test_strat.py](../../tests/unit/test_strat.py):

```python
class Test<Name>Signal:
    def test_long_condition(self):
        """Verify long signal (+1) for known inputs."""

    def test_short_condition(self):
        """Verify short signal (-1) for known inputs."""

    def test_flat_condition(self):
        """Verify flat (0) when between thresholds."""

    def test_nan_propagation(self):
        """NaN inputs produce NaN positions."""

    def test_output_dtype_float(self):
        """Output must be float dtype."""
```

### 3. Add integration test

Add a pipeline test in [tests/integration/test_backtest_pipeline.py](../../tests/integration/test_backtest_pipeline.py):

```python
def test_<indicator>_<name>_pipeline(self, synthetic_market_data):
    df = synthetic_market_data.copy()
    ta = TechnicalAnalysis(df)
    perf = Performance(
        ta.data, 252, ta.get_bollinger_band, Strategy.<name>_signal, 20, 1.0
    )
    result = perf.get_strategy_performance()
    assert isinstance(result, pd.Series)
```

### 4. Verify

```bash
python -m pytest tests/ -v -k "<name>"
```

## Checklist
- [ ] Static method added to `Strategy` with docstring
- [ ] Returns numpy float array of `{-1, 0, 1}` with NaN propagation
- [ ] Compatible with `Performance(strategy_func=Strategy.<name>_signal)` signature
- [ ] Unit tests cover: long/short/flat, NaN, dtype
- [ ] Integration test runs full pipeline
- [ ] All tests pass
