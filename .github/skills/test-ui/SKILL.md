---
name: test-ui
description: 'Test the Streamlit backtest UI — locally with AppTest and on cloud (Streamlit Community Cloud). Use when verifying UI behaviour after changes to app.py or pipeline modules.'
argument-hint: 'Scenario to test, e.g. backtest-tab, grid-search-tab, walk-forward-tab, trading-tab'
---

# Test the Streamlit UI

## When to Use
- After modifying `src/app.py` — verify widgets render and actions trigger correctly
- After changing pipeline modules (`perf.py`, `param_opt.py`, `walk_forward.py`) — confirm the UI reflects the new behaviour
- Before deploying to Streamlit Community Cloud — run the full suite to catch regressions

## Local Testing with `AppTest`

Streamlit ships a headless test framework (`streamlit.testing.v1.AppTest`) that runs the app
in-process without a browser. Tests live in [tests/unit/test_app.py](../../tests/unit/test_app.py).

### Structure of a test

```python
from streamlit.testing.v1 import AppTest
import pandas as pd

def test_backtest_tab_loads():
    """App renders without exceptions on startup."""
    at = AppTest.from_file("src/app.py", default_timeout=30)
    at.run()
    assert not at.exception
```

### Interacting with widgets

```python
def test_run_backtest_button():
    at = AppTest.from_file("src/app.py", default_timeout=30)
    at.run()

    # Fill sidebar inputs
    at.text_input[0].set_value("AAPL").run()   # Symbol
    at.selectbox[0].set_value("Equity (252 trading days/year)").run()

    # Click primary button
    at.button[0].click().run()

    # Assert result rendered (no exception, success/error element present)
    assert not at.exception
```

### Available assertions

| Element | Accessor | Common assertions |
|---------|----------|-------------------|
| Title / header | `at.title`, `at.header` | `.value`, `len()` |
| Markdown text | `at.markdown` | `.value` contains substring |
| DataFrames | `at.dataframe` | `len() > 0`, `.value` shape |
| Charts | `at.plotly_chart` | `len() > 0` |
| Success / Error / Warning | `at.success`, `at.error`, `at.warning` | `len() > 0`, `.value` |
| Buttons | `at.button` | `.click().run()` |
| Text inputs | `at.text_input` | `.set_value("...").run()` |
| Select boxes | `at.selectbox` | `.set_value("...").run()` |
| Number inputs | `at.number_input` | `.set_value(20).run()` |

> **Note:** Widget indices are 0-based in render order. Use `.key` to address by key
> instead: `at.button(key="run_bt").click().run()`.

### Running UI tests

```bash
# All UI tests
python -m pytest tests/unit/test_app.py -v

# Single scenario
python -m pytest tests/unit/test_app.py -v -k "backtest"
```

### Mocking external data in UI tests

AppTest runs the full app code. Mock `yfinance.download` (or the relevant data source) so
the test never hits the network:

```python
from unittest.mock import patch
import pandas as pd
import numpy as np

def _fake_price_df():
    dates = pd.date_range("2020-01-01", periods=200, freq="D")
    close = 100 + np.cumsum(np.random.randn(200) * 0.5)
    return pd.DataFrame({"Close": close, "Volume": 1e6}, index=dates)

def test_run_backtest_with_mock_data():
    with patch("yfinance.download", return_value=_fake_price_df()):
        at = AppTest.from_file("src/app.py", default_timeout=30)
        at.run()
        at.button(key="run_bt").click().run()
        assert not at.exception
        assert len(at.plotly_chart) > 0
```

## Cloud Testing (Streamlit Community Cloud)

### 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| GitHub repo (public or private) | Must contain `src/app.py` and `requirements.txt` |
| Streamlit account | <https://share.streamlit.io> — free tier available |
| `requirements.txt` in project root | Must include `streamlit`, `plotly`, `pandas`, `numpy`, `yfinance` |

### 2. Deploy to Streamlit Community Cloud

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. Click **New app** → select the repository and branch.
3. Set **Main file path** to `src/app.py`.
4. Click **Deploy**.

Streamlit Cloud installs `requirements.txt` and launches the app. The URL will be:
```
https://<app-name>.streamlit.app
```

### 3. Environment secrets on the cloud

API keys live in `.env` locally (gitignored). On Streamlit Cloud, set them as **Secrets**:

1. In the app dashboard, click ⋮ → **Settings** → **Secrets**.
2. Add secrets in TOML format:
   ```toml
   GLASSNODE_API_KEY = "your_key_here"
   ALPHAVANTAGE_API_KEY = "your_key_here"
   FUTU_HOST = "127.0.0.1"
   FUTU_PORT = "11111"
   ```
3. Redeploy the app.

> **Note:** `YahooFinance` requires no API key and works on the cloud out of the box.
> `FutuOpenD` requires a local gateway — it is **not available** on Streamlit Cloud.
> The Trading tab will be non-functional in cloud deployments.

### 4. Smoke-test the cloud deployment

After deploy, manually verify each tab:

| Tab | What to check |
|-----|---------------|
| **Backtest** | Enter symbol, click **Run Backtest**, confirm chart renders |
| **Grid Search** | Add a grid row, click **Run Grid Search**, confirm heatmap renders |
| **Walk-Forward** | Click **Run Walk-Forward Test**, confirm summary table renders |
| **Trading** | Confirm a clear "connection failed" or disabled message (Futu not available) |

### 5. (Optional) Automated smoke test via Playwright

For CI smoke-testing the live cloud URL:

```bash
pip install playwright pytest-playwright
playwright install chromium
```

```python
# tests/e2e/test_app_cloud.py
import pytest
from playwright.sync_api import Page

CLOUD_URL = "https://<app-name>.streamlit.app"

@pytest.mark.e2e
def test_cloud_app_loads(page: Page):
    page.goto(CLOUD_URL, timeout=60_000)
    page.wait_for_selector("text=Quant Strategies", timeout=30_000)
    assert "Quant Strategies" in page.title()

@pytest.mark.e2e
def test_cloud_backtest_tab_visible(page: Page):
    page.goto(CLOUD_URL, timeout=60_000)
    page.wait_for_selector("text=Backtest", timeout=30_000)
    assert page.locator("text=Backtest").count() > 0
```

Run with:
```bash
python -m pytest tests/e2e/test_app_cloud.py -v -m e2e
```

> E2E tests are excluded from the default test run (`addopts = "-m 'not e2e'"` in `pyproject.toml`).
> Run explicitly with `-m e2e` when verifying the cloud deployment.

## Checklist
- [ ] `tests/unit/test_app.py` covers: app loads, backtest runs, grid search runs, walk-forward runs
- [ ] All data source calls are mocked (no live API calls in unit tests)
- [ ] `python -m pytest tests/unit/test_app.py -v` passes
- [ ] App deploys to Streamlit Community Cloud without errors
- [ ] All four tabs render correctly on the cloud
- [ ] Secrets are configured for any data sources used in production
