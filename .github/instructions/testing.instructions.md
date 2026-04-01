---
description: "Use when writing, updating, or reviewing test files. Covers pytest patterns, fixture usage, mocking external APIs, and test structure for the backtest pipeline."
applyTo: "tests/**"
---
# Testing Rules

## Structure

- Unit tests go in `tests/unit/test_<module>.py` — one file per source module.
- Integration tests go in `tests/integration/` — full pipeline runs with synthetic data.
- Shared fixtures live in `tests/conftest.py`.

## Conventions

- Use `pytest` — no unittest.TestCase needed.
- Group related tests in classes (e.g. `TestSMA`, `TestBollingerBand`).
- Name tests `test_<what>_<expected_behavior>` (e.g. `test_rsi_bounded_0_100`).
- Use `pytest.approx()` for floating-point assertions.

## Fixtures

Reuse existing fixtures from `conftest.py` before creating new ones:
- `sample_ohlc_df` — random walk OHLCV with price/factor columns
- `simple_factor_df` — deterministic `[1..10]` for exact value checks
- `trending_up_df` / `trending_down_df` — for directional assertions

## Mocking

- **Never** call live APIs in tests. Mock `requests.get`, `futu.OpenQuoteContext`, etc.
- Use `@patch.dict("os.environ", {...})` for env vars.
- Clear `@lru_cache` with `.cache_clear()` between tests when mocking data sources.
- Mock `pd.read_json` when testing Glassnode (pandas 3.x changed string handling).

## What to Test

- **Indicators (ta.py)**: known values, NaN leading zeros, output length, value bounds (e.g. RSI 0–100).
- **Strategies (strat.py)**: long/short/flat signals, NaN propagation, float dtype.
- **Performance (perf.py)**: metric signs, drawdown non-negative, Series output format.
- **Data (data.py)**: API parameters passed correctly, DataFrame schema returned.
- **Param opt (param_opt.py)**: grid size, generator type, all combinations covered.

## Running

```bash
python -m pytest tests/ -v              # All tests
python -m pytest tests/unit/ -v         # Unit only
python -m pytest tests/integration/ -v  # Integration only
python -m pytest tests/ -k "rsi"        # Filter by name
```
