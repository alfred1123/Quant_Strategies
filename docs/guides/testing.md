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

E2E tests are excluded by default. Pytest configuration (markers, default options, `pythonpath`) lives under `[tool.pytest.ini_options]` in `pyproject.toml`.

## Test Structure

```
tests/
├── conftest.py                # Shared fixtures
├── unit/                      # Fast, mocked tests
│   ├── test_data.py
│   ├── test_strat.py
│   ├── test_perf.py
│   ├── test_param_opt.py
│   ├── test_walk_forward.py
│   ├── test_main.py
│   ├── test_ta.py
│   ├── test_trade.py
│   ├── test_api.py
│   ├── test_auth_service.py
│   └── test_log_config.py
├── integration/
│   └── test_backtest_pipeline.py
└── e2e/
    ├── test_yahoo_finance_e2e.py
    ├── test_alphavantage_e2e.py
    └── test_futu_trader_e2e.py
```

## Frontend Tests

The React frontend uses Vitest + React Testing Library + happy-dom.

```bash
cd frontend

# Run all tests once
npm test

# Watch mode
npm run test:watch
```

Test files live next to the code they cover (e.g. `src/utils/grid.ts` ↔ `src/utils/grid.test.ts`). The shared render wrapper (with `QueryClient` + MUI theme) lives at `frontend/src/test/wrapper.tsx`.

## Conventions

- Every change to `src/` or `frontend/src/` must have corresponding test updates.
- New functions/classes must have unit tests.
- Use `tests/conftest.py` fixtures for shared synthetic data on the Python side.
- Mock external APIs in unit tests — only E2E tests hit real services.
