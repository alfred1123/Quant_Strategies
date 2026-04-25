---
name: add-data-source
description: 'Add a new data source to the backtest pipeline. Use when integrating a new pricing API or data provider (e.g. Yahoo Finance, Tiingo, EODHD, Binance) into data.py with tests and pipeline wiring.'
argument-hint: 'Data source name, e.g. Tiingo, Binance, EODHD'
---

# Add Data Source

## When to Use
- Adding a new pricing data provider to `src/data.py`
- Integrating a free or paid API for equity, crypto, or ETF data
- Replacing or supplementing an existing data source

## Procedure

### 1. Implement the class

Add a class to [data.py](../../src/data.py) following the existing pattern:

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
| `src/main.py` | Add to import: `from data import ..., <SourceName>` |
| `requirements.txt` | Add the library (e.g. `yfinance`, `tiingo`) |
| `.env.example` | Add placeholder for API key (or note if none needed) |
| `.github/instructions/backtest-pipeline.instructions.md` | Add class to data.py section |

### 4. Install and verify

```bash
pip install <library>
python -m pytest tests/unit/test_data.py -v --tb=short
```

### 5. Smoke test with real data

Quick sanity check from `src/`:

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
| `NasdaqDataLink` | `nasdaqdatalink` | Yes | Time-series + table data (formerly Quandl), free tier 50 calls/day |

---

## Paid / Rate-Limited Data Sources \u2014 Rate-Limit Guard

Data-source classes do **not** persist API responses themselves. The central
`BacktestCache` (see [src/data.py](../../../src/data.py) and
[docs/design/separate-underlying.md](../../../docs/design/separate-underlying.md))
caches every provider payload in `BT.API_REQUEST` / `BT.API_REQUEST_PAYLOAD`
and only invokes the data-source class when the user explicitly ticks
**Refresh dataset** in the UI. From the data-source's perspective, every call
to `get_historical_price` is a real provider hit.

For rate-limited / paid providers, that means each `get_historical_price` call
must first verify the provider quota.

### Data flow

```
UI request \u2014\u2192 BacktestCache.get_or_fetch_payload(refresh=False|True)
                  \u2502
        \u250C\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2524
   refresh=False           refresh=True
   (read-only)             (user opted in)
        \u2502                        \u2502
   serve cached row        call data_source.get_historical_price(...)
   or raise CacheMiss               \u2502
                            1. Rate-limit check  \u2500\u2500\u2500\u2500\u2500\u2500\u25BA SP_GET_API_LIMIT_CHK
                                     \u2502
                               \u250C\u2500\u2500\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2500\u2500\u2510
                          OUT_ALLOWED='Y'   'N'
                                     \u2502        \u2502
                            2. Fetch from API   raise RateLimitError
                                     \u2502
                            3. Return ['t', 'v'] DataFrame
                                     \u2502
                            (BacktestCache then persists via SP_INS_API_REQUEST)
```

### DB tables involved

| Table | Schema | Purpose |
|-------|--------|---------|
| `REFDATA.APP` | REFDATA | Provider registry (`APP_ID`). Add seed row. |
| `REFDATA.APP_METRIC` | REFDATA | Metric per provider (`APP_METRIC_ID`). Add seed row. |
| `REFDATA.TM_INTERVAL` | REFDATA | Time interval (e.g. `daily`). |
| `REFDATA.API_LIMIT` | REFDATA | Rate limits per provider. Add seed row. |
| `BT.API_REQUEST` | BT | Subscription metadata — one row per (symbol, source, interval). Soft-versioned via `API_REQ_VID`. |
| `BT.API_REQUEST_PAYLOAD` | BT | Full merged history as JSONB. Append-only, yearly-partitioned. |

### Stored procedures

| Procedure | Direction | Purpose |
|-----------|-----------|---------|
| `BT.SP_GET_API_REQUEST` | **Read** | Returns the current `API_REQUEST` row joined with its JSONB payload, filtered by `(APP_ID, APP_METRIC_ID, TM_INTERVAL_ID, INTERNAL_CUSIP)`. |
| `BT.SP_GET_API_LIMIT_CHK(IN_APP_ID)` | **Read** | Check all `REFDATA.API_LIMIT` rules for the provider. Returns `OUT_ALLOWED='Y'` if safe to call, `'N'` with breach details if any limit is exceeded. **Must be called before every provider API request.** |
| `BT.SP_INS_API_REQUEST` | **Write** | Combined header + JSONB payload insert. Bumps `API_REQ_VID` and closes the prior current row in one call. |

### Implementation pattern

**Caching is centralised in `BacktestCache.get_or_fetch_payload(refresh=False|True)` — do NOT re-implement per-source cache logic.** Each new data-source class only needs a clean `get_historical_price(symbol, start, end)` that always hits the upstream provider and returns a normalised `["t", "v"]` DataFrame. The service layer wraps the call in a `fetcher` closure and passes it to `BacktestCache`, which decides (based on the user's *Refresh dataset* checkbox) whether to call the closure at all and whether to persist a new version.

A new data-source class therefore needs:

1. **Constructor** — load the API key from `.env`, validate, hold any session/client.
2. **`get_historical_price(symbol, start_date, end_date)`** — fetch directly from the provider, normalise to a DataFrame with at least columns `t` (date) and `v` (price). No DB calls.
3. **Optional rate-limit guard** — for paid/rate-limited providers, call `BT.SP_GET_API_LIMIT_CHK(APP_ID)` at the top of `get_historical_price` and raise `RateLimitError` if `OUT_ALLOWED='N'`. This is independent of the cache — it protects the provider quota even when *Refresh dataset* is ticked.

```python
class PaidSourceExample:

    APP_ID = 4  # nasdaq_data_link \u2014 must match REFDATA.APP seed

    def __init__(self) -> None:
        load_dotenv()
        self._api_key = os.getenv("NDL_API_KEY")
        if not self._api_key:
            raise ValueError("NDL_API_KEY must be set in .env")
        # Optional: hold a DB conninfo only if you implement the rate-limit guard.

    def get_historical_price(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        # Optional rate-limit check (paid / quota-bound providers only).
        # self._check_rate_limit()

        # Hit the provider for the full requested range. The BacktestCache
        # layer decides whether this method is even called \u2014 you do not
        # check the cache here.
        rows = self._fetch_from_api(symbol, start_date, end_date)
        df = pd.DataFrame(rows)
        df.columns = ["t", "v"]
        df["v"] = df["v"].astype(float)
        return df.reset_index(drop=True)
```

See `BacktestCache.get_or_fetch_payload` in [src/data.py](../../../src/data.py) and the design doc [docs/design/separate-underlying.md](../../../docs/design/separate-underlying.md) for how the cache wraps your class.

### REFDATA seed data checklist

When adding a paid source, add seed rows to these files:

| File | What to add |
|------|------------|
| `db/liquidbase/refdata/data/APP.sql` (or a new `APP_<SOURCE>.sql`) | Provider row: `(name, display_name, class_name, ...)` |
| `db/liquidbase/refdata/data/APP_METRIC.sql` | One row per metric: `(app_id, metric_nm, display_name, metric_path, data_category, method_name, ...)` |
| `db/liquidbase/refdata/data/API_LIMIT.sql` | Rate limit rows per the provider's published limits |

**Existing APP_IDs:** yahoo=1, glassnode=2, futu=3, nasdaq_data_link=4.

### Unit test additions for paid sources

In addition to the standard tests (see above), paid sources need:

```python
class Test<SourceName>RateLimit:
    """Verify the rate-limit guard around the provider API call."""

    @patch("<db connect>")
    def test_rate_limit_check_blocks_when_breached(self, mock_conn):
        """Verify RateLimitError raised when SP_GET_API_LIMIT_CHK returns 'N'.
        Mock cursor to return ('N', 'requests_per_day', 200, 200, '00000', ...)."""

    @patch("<db connect>")
    @patch("<api fetch>")
    def test_rate_limit_check_passes_before_api_call(self, mock_api, mock_conn):
        """Verify SP_GET_API_LIMIT_CHK is called before the provider API.
        Mock returns ('Y', ...) to allow the fetch."""
```

> **Note:** Cache hit / miss / merge / persistence behaviour is covered centrally by `tests/unit/test_data.py::TestBacktestCacheGetOrFetch`. Do **not** re-test it per data source.
