---
name: add-data-source
description: 'Add a new data source to the backtest pipeline. Use when integrating a new pricing API or data provider (e.g. Yahoo Finance, Tiingo, EODHD, Binance) into data.py with tests and pipeline wiring.'
argument-hint: 'Data source name, e.g. Tiingo, Binance, EODHD'
---

# Add Data Source

## When to Use
- Adding a new pricing data provider to `scripts/backtest/data.py`
- Integrating a free or paid API for equity, crypto, or ETF data
- Replacing or supplementing an existing data source

## Procedure

### 1. Implement the class

Add a class to [data.py](../../scripts/backtest/data.py) following the existing pattern:

```python
class <SourceName>:
    """Retrieve historical price data from <source>.

    <Note API key requirements or lack thereof.>
    """

    def __init__(self) -> None:
        load_dotenv()
        # Validate required env vars (skip if no API key needed)
        self.__api_key = os.getenv('<SOURCE>_API_KEY')
        if not self.__api_key:
            raise ValueError("<SOURCE>_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date):
        """Fetch daily close prices.

        Args:
            symbol: Ticker symbol (source-specific format).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns ['t', 'v'] matching the pipeline interface.
            't' = date strings (YYYY-MM-DD), 'v' = float close prices.

        Raises:
            ValueError: If no data returned.
            requests.HTTPError: If API request fails.
        """
        # ... fetch and transform ...
        df = pd.DataFrame({"t": dates, "v": closes})
        df["v"] = df["v"].astype(float)
        return df.reset_index(drop=True)
```

**Requirements:**
- Return DataFrame with exactly columns `['t', 'v']` — this is the pipeline interface
- `t` = date strings in `YYYY-MM-DD` format
- `v` = float close prices
- Use `@lru_cache(maxsize=32)` on `get_historical_price`
- Validate env vars in `__init__` with `raise ValueError` (unless no key needed)
- Add `timeout=30` to all network requests
- Use `raise_for_status()` on HTTP responses

**For unofficial/scraper sources (e.g. yfinance):**
- Lazy-import the library inside the method to avoid import-time network calls
- Add retry logic with exponential backoff (`MAX_RETRIES`, `RETRY_DELAY`)
- Raise `RuntimeError` after max retries exhausted

### 2. Add unit tests

Add a test class to [tests/unit/test_data.py](../../tests/unit/test_data.py):

```python
class Test<SourceName>:
    """Tests for <SourceName> data source.

    Mock structure mirrors the real API response.
    See: <link to API docs or sample response>
    """

    @patch("<mock target>")
    def test_get_historical_price_returns_dataframe(self, mock_obj):
        """Verify ['t', 'v'] columns, correct values, float dtype."""

    @patch("<mock target>")
    def test_get_historical_price_passes_correct_params(self, mock_obj):
        """Verify API is called with expected arguments."""

    @patch("<mock target>")
    def test_raises_on_empty_response(self, mock_obj):
        """Verify ValueError when no data returned."""

    def test_init_raises_without_api_key(self, monkeypatch):
        """Verify ValueError when env var missing. Skip if no key needed."""
        monkeypatch.setattr("data.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("<SOURCE>_API_KEY", raising=False)

    @patch("<mock target>")
    def test_close_values_are_float(self, mock_obj):
        """Verify v column dtype is float."""
```

**Test rules:**
- Mock all network calls — never hit real APIs in unit tests
- Mock `load_dotenv` + use `monkeypatch.delenv()` for "missing key" tests (not `clear=True`)
- Clear `@lru_cache` with `.cache_clear()` in each test
- Mock responses must mirror real API structure — cite source docs in a comment

### 3. Wire into the pipeline

Update these files:

| File | Change |
|------|--------|
| `scripts/backtest/main.py` | Add to import: `from data import ..., <SourceName>` |
| `requirements.txt` | Add the library (e.g. `yfinance`, `tiingo`) |
| `scripts/.env.example` | Add placeholder for API key (or note if none needed) |
| `.github/instructions/backtest-pipeline.instructions.md` | Add class to data.py section |

### 4. Install and verify

```bash
pip install <library>
python -m pytest tests/unit/test_data.py -v --tb=short
```

### 5. Smoke test with real data

Quick sanity check from `scripts/backtest/`:

```python
from data import <SourceName>
src = <SourceName>()
df = src.get_historical_price('<symbol>', '2016-01-01', '2026-04-01')
print(f"Rows: {len(df)}, Range: {df['t'].iloc[0]} → {df['t'].iloc[-1]}")
```

Verify 10+ years of data are available for backtesting (5 years testing + 5 years overfitting checks).

## Existing sources

| Class | Library | API Key | Notes |
|-------|---------|---------|-------|
| `FutuOpenD` | `futu-api` | No (gateway) | HK/US equity, requires local OpenD gateway |
| `Glassnode` | `requests` | Yes | On-chain crypto metrics |
| `AlphaVantage` | `requests` | Yes | Equity + crypto, free tier limited to 25 req/day |
| `YahooFinance` | `yfinance` | No | Free, 10+ years daily data, unofficial scraper |
