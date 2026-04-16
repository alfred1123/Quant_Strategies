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

## Paid / Rate-Limited Data Sources — Persist API Responses

For any data source that is **not free** (or has tight rate limits), every API
response must be persisted to `BT.API_REQUEST_PAYLOAD` so that repeated
backtests never re-fetch the same data from the provider.

### Data flow

```
1. Check DB for existing payload  ──► SP_GET_API_REQUEST_WITH_PAYLOAD
                                         │
                              ┌──────────┴──────────┐
                         payload exists         no payload / stale range
                              │                       │
                       return from DB           2. Check rate limit ──► SP_GET_API_LIMIT_CHK
                                                      │
                                                ┌─────┴─────┐
                                           OUT_ALLOWED='Y'  'N'
                                                │            │
                                           3. Fetch API   raise RateLimitError
                                                │
                                           4. Merge with previous payload (if any)
                                                │
                                           5. SP_INS_API_REQUEST + SP_INS_API_REQUEST_PAYLOAD
                                                │
                                           6. Return merged DataFrame
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
| `BT.SP_GET_API_REQUEST_WITH_PAYLOAD(IN_API_REQ_ID)` | **Read** | Returns the current API_REQUEST joined with its latest payload. Use to check if data already exists before calling the provider API. || `BT.SP_GET_API_LIMIT_CHK(IN_APP_ID)` | **Read** | Check all `REFDATA.API_LIMIT` rules for the provider. Returns `OUT_ALLOWED='Y'` if safe to call, `'N'` with breach details if any limit is exceeded. **Must be called before every provider API request.** || `BT.SP_INS_API_REQUEST(IN_API_REQ_ID, IN_APP_ID, IN_APP_METRIC_ID, IN_TM_INTERVAL_ID, IN_SYMBOL, IN_FULL_RANGE_START, IN_FULL_RANGE_END, IN_USER_ID)` | **Write** | Upsert subscription metadata (bumps VID, flips old row to `IS_CURRENT_IND='N'`). |
| `BT.SP_INS_API_REQUEST_PAYLOAD(IN_API_REQ_ID, IN_API_REQ_VID, IN_RANGE_START_TS, IN_RANGE_END_TS, IN_PAYLOAD, IN_USER_ID)` | **Write** | Store the complete merged history as JSONB. |

### Implementation pattern

The class must implement a **cache-first** strategy. On `get_historical_price`:

1. **Lookup** — call `SP_GET_API_REQUEST_WITH_PAYLOAD` with the deterministic
   `API_REQ_ID` (UUID v5 from namespace + `"{app_name}:{symbol}:{metric}:{interval}"`).
2. **Hit** — if the stored `RANGE_END_TS` already covers the requested
   `end_date`, deserialise the JSONB payload directly into the DataFrame and
   return. No API call.
3. **Rate-limit check** — call `SP_GET_API_LIMIT_CHK(APP_ID)`. If
   `OUT_ALLOWED = 'N'`, raise a `RateLimitError` with breach details
   (`OUT_LIMIT_TYPE`, `OUT_CURRENT_CNT`, `OUT_MAX_VALUE`). **Never skip this.**
4. **Miss / stale** — fetch only the **delta** (from `RANGE_END_TS + 1 day`
   to `end_date`) from the provider API.
5. **Merge** — concatenate previous payload rows with new rows, deduplicate on
   date, sort ascending.
6. **Persist** — call `SP_INS_API_REQUEST` (bumps VID) then
   `SP_INS_API_REQUEST_PAYLOAD` (stores merged JSONB).
7. **Return** — filter the merged DataFrame to `[start_date, end_date]` and
   return `['t', 'v']`.

```python
import json
import uuid
from datetime import datetime, timedelta

import psycopg

# Deterministic UUID namespace for API_REQ_ID
_NDL_UUID_NS = uuid.UUID("a1b2c3d4-0000-0000-0000-000000000000")  # project-specific

def _make_api_req_id(app_name: str, symbol: str, metric: str, interval: str) -> uuid.UUID:
    """Deterministic UUID v5 so the same subscription always maps to the same PK."""
    return uuid.uuid5(_NDL_UUID_NS, f"{app_name}:{symbol}:{metric}:{interval}")


class RateLimitError(RuntimeError):
    """Raised when SP_GET_API_LIMIT_CHK returns OUT_ALLOWED='N'."""


class PaidSourceExample:

    APP_ID = 4  # nasdaq_data_link — must match REFDATA.APP seed

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        # ... validate API key from .env ...

    def get_historical_price(self, symbol, start_date, end_date):
        api_req_id = _make_api_req_id("nasdaq_data_link", symbol, "price", "daily")

        # 1. Check DB for existing payload
        existing = self._load_payload(api_req_id)

        if existing is not None:
            stored_end = existing["range_end"]
            if stored_end >= end_date:
                # Full cache hit — no API call needed
                return self._filter(existing["rows"], start_date, end_date)
            # Partial hit — fetch delta only
            fetch_start = (datetime.strptime(stored_end, "%Y-%m-%d")
                           + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            fetch_start = start_date

        # 2. Rate-limit check — must pass before any provider API call
        self._check_rate_limit()

        # 3. Fetch delta from provider API
        new_rows = self._fetch_from_api(symbol, fetch_start, end_date)

        # 4. Merge
        if existing is not None:
            merged = existing["rows"] + new_rows
        else:
            merged = new_rows
        # Deduplicate on date, keep latest
        seen = {}
        for row in merged:
            seen[row["t"]] = row["v"]
        merged = [{"t": t, "v": v} for t, v in sorted(seen.items())]

        # 5. Persist via stored procedures
        range_start = merged[0]["t"]
        range_end = merged[-1]["t"]
        vid = self._persist(api_req_id, symbol, range_start, range_end, merged)

        # 6. Return filtered
        return self._filter(merged, start_date, end_date)

    def _check_rate_limit(self) -> None:
        """Call SP_GET_API_LIMIT_CHK. Raises RateLimitError if any limit breached."""
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "CALL BT.SP_GET_API_LIMIT_CHK(%s, NULL, NULL, NULL, NULL, NULL, NULL, NULL)",
                    (self.APP_ID,),
                )
                row = cur.fetchone()
                # OUT params: OUT_ALLOWED, OUT_LIMIT_TYPE, OUT_CURRENT_CNT,
                #             OUT_MAX_VALUE, OUT_SQLSTATE, OUT_SQLMSG, OUT_SQLERRMC
                allowed = row[0]
                if allowed != 'Y':
                    limit_type = row[1]
                    current_cnt = row[2]
                    max_value = row[3]
                    raise RateLimitError(
                        f"Rate limit breached for APP_ID={self.APP_ID}: "
                        f"{limit_type} {current_cnt}/{max_value}"
                    )

    def _load_payload(self, api_req_id: uuid.UUID) -> dict | None:
        """Call SP_GET_API_REQUEST_WITH_PAYLOAD. Returns None on miss."""
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "CALL BT.SP_GET_API_REQUEST_WITH_PAYLOAD(%s, NULL, NULL, NULL, NULL)",
                    (str(api_req_id),),
                )
                row = cur.fetchone()
                cursor_name, sqlstate = row[0], row[1]
                if sqlstate != "00000":
                    return None
                cur.execute(f'FETCH ALL FROM "{cursor_name}"')
                rows = cur.fetchall()
                cur.execute(f'CLOSE "{cursor_name}"')
                if not rows:
                    return None
                # Columns: API_REQ_ID, API_REQ_VID, APP_ID, APP_METRIC_ID,
                #          TM_INTERVAL_ID, SYMBOL, FULL_RANGE_START,
                #          FULL_RANGE_END, RANGE_START_TS, RANGE_END_TS, PAYLOAD
                r = rows[0]
                payload_json = r[10]  # PAYLOAD column
                if payload_json is None:
                    return None
                return {
                    "vid": r[1],
                    "range_start": r[8].strftime("%Y-%m-%d") if r[8] else None,
                    "range_end": r[9].strftime("%Y-%m-%d") if r[9] else None,
                    "rows": payload_json,  # already parsed from JSONB by psycopg
                }

    def _persist(self, api_req_id, symbol, range_start, range_end, merged):
        """Call SP_INS_API_REQUEST then SP_INS_API_REQUEST_PAYLOAD."""
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                # Insert/version the subscription
                cur.execute(
                    "CALL BT.SP_INS_API_REQUEST(%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL)",
                    (str(api_req_id), APP_ID, APP_METRIC_ID, TM_INTERVAL_ID,
                     symbol, range_start, range_end, USER_ID),
                )
                row = cur.fetchone()
                # sqlstate at index 0
                if row[0] != "00000":
                    raise RuntimeError(f"SP_INS_API_REQUEST failed: {row}")

                # Get new VID (max for this req)
                cur.execute(
                    "SELECT MAX(API_REQ_VID) FROM BT.API_REQUEST WHERE API_REQ_ID = %s",
                    (str(api_req_id),),
                )
                vid = cur.fetchone()[0]

                # Store payload
                cur.execute(
                    "CALL BT.SP_INS_API_REQUEST_PAYLOAD(%s, %s, %s, %s, %s::jsonb, %s, NULL, NULL, NULL)",
                    (str(api_req_id), vid, range_start, range_end,
                     json.dumps(merged), USER_ID),
                )
                row = cur.fetchone()
                if row[0] != "00000":
                    raise RuntimeError(f"SP_INS_API_REQUEST_PAYLOAD failed: {row}")
            conn.commit()
        return vid

    @staticmethod
    def _filter(rows, start_date, end_date):
        """Filter merged rows to requested range and return pipeline DataFrame."""
        import pandas as pd
        filtered = [r for r in rows if start_date <= r["t"] <= end_date]
        df = pd.DataFrame(filtered)
        df.columns = ["t", "v"]
        df["v"] = df["v"].astype(float)
        return df.reset_index(drop=True)
```

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
class Test<SourceName>Persistence:
    """Tests for DB persistence (cache-first pattern)."""

    @patch("<db connect>")
    def test_returns_from_cache_on_full_hit(self, mock_conn):
        """Verify no API call when DB payload covers the full date range."""

    @patch("<db connect>")
    @patch("<api fetch>")
    def test_fetches_delta_on_partial_hit(self, mock_api, mock_conn):
        """Verify only the missing date range is fetched from the API."""

    @patch("<db connect>")
    @patch("<api fetch>")
    def test_persists_merged_payload(self, mock_api, mock_conn):
        """Verify SP_INS_API_REQUEST and SP_INS_API_REQUEST_PAYLOAD are called
        with the correct merged payload."""

    @patch("<db connect>")
    @patch("<api fetch>")
    def test_full_miss_fetches_entire_range(self, mock_api, mock_conn):
        """Verify full range is fetched when no prior payload exists."""

    @patch("<db connect>")
    def test_rate_limit_check_blocks_when_breached(self, mock_conn):
        """Verify RateLimitError raised when SP_GET_API_LIMIT_CHK returns 'N'.
        Mock cursor to return ('N', 'requests_per_day', 200, 200, '00000', ...)."""

    @patch("<db connect>")
    @patch("<api fetch>")
    def test_rate_limit_check_passes_before_api_call(self, mock_api, mock_conn):
        """Verify SP_GET_API_LIMIT_CHK is called before the provider API
        on cache miss. Mock returns ('Y', ...) to allow the fetch."""
```
