# Running Tests

## Quick Commands

```bash
# All tests (from project root)
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Specific test file
python -m pytest tests/unit/test_strat.py -v

# Filter by name
python -m pytest tests/ -v -k "bollinger"

# End-to-end tests (hit real APIs — requires network + API keys)
python -m pytest tests/e2e/ -v -m e2e
```

E2E tests are excluded by default (configured in `pyproject.toml`).

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── unit/                # Fast, mocked tests
│   ├── test_data.py     # Data source tests
│   ├── test_strat.py    # Indicator + signal tests
│   ├── test_perf.py     # Performance engine tests
│   ├── test_param_opt.py # Grid search tests
│   ├── test_main.py     # CLI integration
│   ├── test_api.py      # FastAPI endpoint tests
│   └── test_log_config.py
├── integration/
│   └── test_backtest_pipeline.py  # Full pipeline with synthetic data
└── e2e/
    ├── test_yahoo_finance_e2e.py
    ├── test_alphavantage_e2e.py
    └── test_futu_trader_e2e.py
```

## Conventions

- Every change to `src/` must have corresponding test updates
- New functions/classes must have unit tests
- Use `conftest.py` fixtures for shared synthetic data
- Mock external APIs in unit tests — only E2E tests hit real services
- Current baseline: **342 tests passing**
