"""
Data source classes for the backtest pipeline.

Supported sources:
    1. FutuOpenD — HK/US equity via Futu API
    2. Glassnode — on-chain crypto metrics
    3. AlphaVantage — equity and crypto price data
    4. YahooFinance — free equity/crypto/ETF data via yfinance
    5. NasdaqDataLink — time-series and table data via Nasdaq Data Link API

BybitData class moved to backup/deco/ — platform decommissioned.
"""

import os
import json
import logging
import time
import uuid
from functools import lru_cache

import futu
import pandas as pd
import psycopg
import requests
from dotenv import load_dotenv

from db import DbGateway

logger = logging.getLogger(__name__)


# ── REFDATA cache ────────────────────────────────────────────────────────────

_REFDATA_EXCLUDE = frozenset({"databasechangelog", "databasechangeloglock"})


class RefDataCache(DbGateway):
    """In-process cache for REFDATA tables.

    Thread-safe for reads (immutable snapshot after load).
    Tables are discovered dynamically from ``information_schema.tables``.
    """

    def __init__(self, conninfo: str):
        super().__init__(conninfo)
        self._store: dict[str, list[dict]] = {}

    def _discover_tables(self, cur) -> list[str]:
        """Return REFDATA table names from the catalog, excluding Liquibase internals."""
        cur.execute(
            "SELECT table_name \
                FROM information_schema.tables \
                WHERE table_schema = 'refdata' \
                    AND table_type = 'BASE TABLE' \
                ORDER BY table_name"
            )
        return [r[0] for r in cur.fetchall() if r[0] not in _REFDATA_EXCLUDE]

    def load_all(self) -> None:
        """Fetch every REFDATA table into memory via SP_GET_ENUM."""
        with psycopg.connect(self._conninfo) as conn, conn.cursor() as cur:
            tables = self._discover_tables(cur)
            for table in tables:
                try:
                    self._store[table] = self._drain_cursor(cur, "CALL REFDATA.SP_GET_ENUM(%s, NULL, NULL, NULL, NULL)", (table,))
                except Exception:
                    logger.warning("Failed to load REFDATA.%s — SP_GET_ENUM may not support it yet", table, exc_info=True)
                    self._store[table] = []
        logger.info("RefDataCache loaded %d tables: %s", len(self._store), sorted(self._store))

    def get(self, table: str) -> list[dict]:
        if table not in self._store:
            raise ValueError(f"Unknown REFDATA table: {table}")
        rows = self._store[table]
        if not rows:
            raise ValueError(f"REFDATA.{table.upper()} is empty — check SP_GET_ENUM or seed data")
        return rows

    def get_indicator_defaults(self) -> dict[str, dict]:
        """Return ``{method_name: {win_min, win_max, ..., is_bounded_ind}}``."""
        result = {}
        for r in self.get("indicator"):
            result[r["method_name"]] = {
                "win_min": r.get("win_min"),
                "win_max": r.get("win_max"),
                "win_step": r.get("win_step"),
                "sig_min": float(r["sig_min"]) if r.get("sig_min") is not None else None,
                "sig_max": float(r["sig_max"]) if r.get("sig_max") is not None else None,
                "sig_step": float(r["sig_step"]) if r.get("sig_step") is not None else None,
                "is_bounded_ind": r.get("is_bounded_ind"),
            }
        return result

    def resolve_app_id(self, name: str) -> int | None:
        """Resolve a data-source name (e.g. 'yahoo') to its APP_ID."""
        for r in self.get("app"):
            if r["name"] == name:
                return r["app_id"]
        return None

    def refresh(self) -> None:
        self.load_all()


# ── INST cache ───────────────────────────────────────────────────────────────


class InstrumentCache(DbGateway):
    """In-process cache for INST product and cross-reference data.

    Loads all current products and xrefs at startup via stored procedures,
    then serves lookups from memory.  Refresh via ``load_all()`` or
    ``POST /api/v1/inst/refresh``.
    """

    def __init__(self, conninfo: str) -> None:
        super().__init__(conninfo)
        self._products: list[dict] = []
        self._xrefs: list[dict] = []

    # ── load ─────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        """Fetch all current products and xrefs into memory."""
        self._products = self._call_get(
            "CALL INST.SP_GET_PRODUCT(%s, %s, NULL, NULL, NULL, NULL)",
            (None, None),
        )
        self._xrefs = self._call_get(
            "CALL INST.SP_GET_PRODUCT_XREF(%s, %s, %s, NULL, NULL, NULL, NULL)",
            (None, None, None),
        )
        logger.info(
            "InstrumentCache loaded %d products, %d xrefs",
            len(self._products), len(self._xrefs),
        )

    # ── product lookups ──────────────────────────────────────────────────

    def get_products(self) -> list[dict]:
        """Return all current products."""
        return self._products

    def get_product_by_id(self, product_id: int) -> dict | None:
        """Lookup a single product by PRODUCT_ID."""
        for p in self._products:
            if p["product_id"] == product_id:
                return p
        return None

    def get_product_by_cusip(self, internal_cusip: str) -> dict | None:
        """Lookup a single product by INTERNAL_CUSIP."""
        for p in self._products:
            if p["internal_cusip"] == internal_cusip:
                return p
        return None

    # ── xref lookups ─────────────────────────────────────────────────────

    def get_xrefs(self, product_id: int | None = None, app_id: int | None = None) -> list[dict]:
        """Return xrefs filtered by product and/or app."""
        result = self._xrefs
        if product_id is not None:
            result = [x for x in result if x["product_id"] == product_id]
        if app_id is not None:
            result = [x for x in result if x["app_id"] == app_id]
        return result

    def resolve_vendor_symbol(self, product_id: int, app_id: int) -> str | None:
        """Resolve a (product, app) pair to the current vendor symbol.

        Returns ``None`` if no mapping exists.
        """
        for x in self._xrefs:
            if x["product_id"] == product_id and x["app_id"] == app_id:
                return x["vendor_symbol"]
        return None

    def refresh(self) -> None:
        self.load_all()


# ── BT cache ─────────────────────────────────────────────────────────────────

class BacktestCache(DbGateway):
    """BT cache read/write via stored procedures.

    Inherits connection handling and cursor protocol from ``DbGateway``.
    Uses ``RefDataCache`` for denormalized ID lookups (APP_ID, etc.).
    """

    REQUIRED_COVERAGE_YEARS = 10

    def __init__(self, conninfo: str, refdata: RefDataCache, user_id: str = "alfcheun") -> None:
        super().__init__(conninfo, user_id)
        self.refdata = refdata

    # ── helpers ─────────────────────────────────────────────────────────

    def _coverage_years(self, rows: list[dict]) -> float:
        """Return cached data range in years, or 0.0 if unknown."""
        if not rows:
            return 0.0
        start = rows[0].get("range_start_ts")
        end = rows[0].get("range_end_ts")
        if not start or not end:
            return 0.0
        return (end - start).days / 365.25

    # ── proc wrappers ──────────────────────────────────────────────────

    def _get_api_request(self, app_id, app_metric_id, tm_interval_id, internal_cusip) -> list[dict]:
        return self._call_get("CALL BT.SP_GET_API_REQUEST(%s, %s, %s, %s, NULL, NULL, NULL, NULL)", (app_id, app_metric_id, tm_interval_id, internal_cusip))

    def _insert_api_request(self, api_req_id, app_id, app_metric_id, tm_interval_id, product_grp_id, start_ts, end_ts, payload_json, internal_cusip):
        self._call_write("CALL BT.SP_INS_API_REQUEST(%s::uuid, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s::jsonb, %s, %s, NULL, NULL, NULL)", (api_req_id, app_id, app_metric_id, tm_interval_id, product_grp_id, start_ts, end_ts, payload_json, self.user_id, internal_cusip))

    # ── public API ───────────────────────────────────────────────────────

    def load_cached_api_payload(
        self,
        app_id: int | None = None,
        app_metric_id: int | None = None,
        tm_interval_id: int | None = None,
        internal_cusip: str | None = None,
    ) -> pd.DataFrame | None:
        """Load cached payload via SP_GET_API_REQUEST.

        Returns a DataFrame built from the JSONB ``payload`` column, or
        ``None`` when no matching row exists or the cached range is less
        than ``REQUIRED_COVERAGE_YEARS``.
        """
        try:
            rows = self._get_api_request(app_id, app_metric_id, tm_interval_id, internal_cusip)
        except RuntimeError:
            return None

        if not rows:
            return None

        coverage = self._coverage_years(rows)
        if coverage < self.REQUIRED_COVERAGE_YEARS:
            logger.info("Cached range %.1f yr < %d yr required — cache miss", coverage, self.REQUIRED_COVERAGE_YEARS)
            return None

        payload = rows[0].get("payload")
        if not payload:
            return None
        return pd.DataFrame(payload)

    def persist_api_request_payload(
        self,
        app_id: int | None = None,
        app_metric_id: int | None = None,
        tm_interval_id: int | None = None,
        product_grp_id: int | None = None,
        range_start: str = "",
        range_end: str = "",
        payload_df: pd.DataFrame | None = None,
        internal_cusip: str | None = None,
    ) -> None:
        """Insert a new API request version via SP_INS_API_REQUEST.

        Skips the insert when the existing cache already covers
        ``REQUIRED_COVERAGE_YEARS``.  Otherwise generates a new UUID —
        the unique index on (APP_ID, APP_METRIC_ID, TM_INTERVAL_ID,
        INTERNAL_CUSIP) with TRANSACT_TO_TS='9999-12-31' guarantees one
        current row, and SP_INS closes the old row automatically.
        """
        # Guard — skip if cache already has sufficient range
        try:
            existing = self._get_api_request(app_id, app_metric_id, tm_interval_id, internal_cusip)
        except RuntimeError:
            existing = []
        coverage = self._coverage_years(existing)
        if coverage >= self.REQUIRED_COVERAGE_YEARS:
            logger.info("Cache already covers %.1f yr — skipping persist", coverage)
            return
        # TODO: append new data to existing payload to extend range (future)
        api_req_id = str(uuid.uuid4())
        payload_json = json.dumps(payload_df.to_dict(orient="records")) if payload_df is not None else None
        start_ts = f"{range_start} 00:00:00+00"
        end_ts = f"{range_end} 00:00:00+00"
        try:
            self._insert_api_request(api_req_id, app_id, app_metric_id, tm_interval_id, product_grp_id, start_ts, end_ts, payload_json, internal_cusip)
        except RuntimeError:
            pass  # already logged in _call_write


class FutuOpenD:
    """Retrieve equity data from Futu OpenD gateway."""

    def __init__(self) -> None:
        load_dotenv()
        self.__host = os.getenv('FUTU_HOST')
        port_str = os.getenv('FUTU_PORT')
        if not self.__host or not port_str:
            raise ValueError("FUTU_HOST and FUTU_PORT must be set in .env")
        self.__port = int(port_str)
        self.quote_ctx = futu.OpenQuoteContext(host=self.__host, port=self.__port)

    @lru_cache(maxsize=32)
    def get_historical_data(self, symbol, start_date, end_date, resolution='K_DAY'):
        """Retrieve historical kline data from Futu OpenD.

        Args:
            symbol: Stock symbol (e.g. 'HK.00700').
            start_date: Start of date range (YYYY-MM-DD).
            end_date: End of date range (YYYY-MM-DD).
            resolution: Kline period. Defaults to 'K_DAY'.

        Returns:
            DataFrame with OHLCV columns.

        Raises:
            RuntimeError: If the Futu API returns an error.
        """
        with self.quote_ctx:
            ret, data, page_req_key = self.quote_ctx.request_history_kline(
                symbol, start=start_date, end=end_date,
                ktype=resolution, autype=futu.AuType.QFQ,
            )
        if ret != 0:
            logger.error("Futu API error (ret=%s): %s", ret, data)
            raise RuntimeError(f"Futu API error (ret={ret}): {data}")
        logger.info("FutuOpenD: fetched %d rows for %s", len(data), symbol)
        return data


class Glassnode:
    """Retrieve on-chain crypto metrics from Glassnode."""

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv('GLASSNODE_API_KEY')
        if not self.__api_key:
            raise ValueError("GLASSNODE_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date, resolution='24h'):
        """Fetch historical close price from Glassnode.

        Args:
            symbol: Crypto asset (e.g. 'BTC').
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            resolution: Data interval. Defaults to '24h'.

        Returns:
            DataFrame with columns ['t', 'v'].

        Raises:
            requests.HTTPError: If the API request fails.
        """
        since = int(time.mktime(time.strptime(start_date, "%Y-%m-%d")))
        until = int(time.mktime(time.strptime(end_date, "%Y-%m-%d")))

        res = requests.get(
            "https://api.glassnode.com/v1/metrics/market/price_usd_close",
            params={"a": symbol, "s": since, "u": until, "i": resolution},
            headers={"X-Api-Key": self.__api_key},
            timeout=30,
        )
        res.raise_for_status()
        df = pd.read_json(res.text, convert_dates=['t'])
        logger.info("Glassnode: fetched %d rows for %s", len(df), symbol)
        return df


class AlphaVantage:
    """Retrieve equity and crypto price data from Alpha Vantage."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv('ALPHAVANTAGE_API_KEY')
        if not self.__api_key:
            raise ValueError("ALPHAVANTAGE_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date, resolution='daily'):
        """Fetch daily close prices from Alpha Vantage.

        Automatically detects crypto symbols (BTC, ETH, etc.) and uses the
        appropriate endpoint (DIGITAL_CURRENCY_DAILY vs TIME_SERIES_DAILY).

        Args:
            symbol: Ticker or crypto symbol (e.g. 'IBM', 'BTC').
            start_date: Start date (YYYY-MM-DD) — filters output.
            end_date: End date (YYYY-MM-DD) — filters output.
            resolution: Ignored for now (daily only). Kept for interface
                        compatibility with other data sources.

        Returns:
            DataFrame with columns ['t', 'v'] matching the pipeline interface.

        Raises:
            requests.HTTPError: If the API request fails.
            ValueError: If the API returns an error message.
        """
        crypto_symbols = {
            'BTC', 'ETH', 'LTC', 'XRP', 'DOGE', 'ADA', 'SOL',
            'DOT', 'AVAX', 'MATIC', 'LINK', 'UNI', 'BNB',
        }

        if symbol.upper() in crypto_symbols:
            df = self._fetch_daily(
                function="DIGITAL_CURRENCY_DAILY",
                symbol=symbol,
                ts_key="Time Series (Digital Currency Daily)",
                close_field="4a. close (USD)",
                extra_params={"market": "USD"},
            )
        else:
            df = self._fetch_daily(
                function="TIME_SERIES_DAILY",
                symbol=symbol,
                ts_key="Time Series (Daily)",
                close_field="4. close",
            )

        # Filter to requested date range
        df = df[(df['t'] >= start_date) & (df['t'] <= end_date)]
        df = df.sort_values('t').reset_index(drop=True)
        return df

    def _fetch_daily(self, function, symbol, ts_key, close_field, extra_params=None):
        """Fetch daily price data from Alpha Vantage.

        Args:
            function: API function name (e.g. 'TIME_SERIES_DAILY').
            symbol: Ticker or crypto symbol.
            ts_key: JSON key containing the time series data.
            close_field: Key for the close price within each day's data.
            extra_params: Additional query parameters for the request.

        Returns:
            DataFrame with columns ['t', 'v'].
        """
        params = {
            "function": function,
            "symbol": symbol,
            "apikey": self.__api_key,
        }
        if extra_params:
            params.update(extra_params)
        data = self._request(params)
        if ts_key not in data:
            logger.error("AlphaVantage response missing '%s': %s", ts_key, data)
            raise ValueError(f"AlphaVantage error: {data.get('Error Message', data)}")
        rows = [
            {"t": date, "v": float(vals[close_field])}
            for date, vals in data[ts_key].items()
        ]
        logger.info("AlphaVantage: fetched %d rows for %s", len(rows), symbol)
        return pd.DataFrame(rows)

    def _request(self, params):
        """Make a request to Alpha Vantage and return parsed JSON."""
        res = requests.get(self.BASE_URL, params=params, timeout=30)
        res.raise_for_status()
        return res.json()


class YahooFinance:
    """Retrieve free historical price data via Yahoo Finance (yfinance).

    No API key required. Supports equities, ETFs, indices, and crypto.
    Returns 10+ years of daily data for backtesting and overfitting checks.

    yfinance is an unofficial scraper — Yahoo may rate-limit or block
    requests. This class lazy-imports yfinance (avoid import-time hangs),
    retries on failure, and sleeps between attempts.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds between retries

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date):
        """Fetch daily close prices from Yahoo Finance.

        Args:
            symbol: Yahoo Finance ticker (e.g. 'AAPL', 'BTC-USD', '^GSPC').
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns ['t', 'v'] matching the pipeline interface.

        Raises:
            ValueError: If no data is returned for the given symbol/range.
            RuntimeError: If all retry attempts are exhausted.
        """
        import yfinance as yf  # lazy import — avoids import-time network calls

        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(
                    start=start_date, end=end_date,
                    auto_adjust=True, timeout=30,
                )
                break
            except Exception as exc:
                last_err = exc
                logger.warning("YahooFinance attempt %d/%d failed for '%s': %s",
                               attempt, self.MAX_RETRIES, symbol, exc)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
        else:
            logger.error("YahooFinance exhausted %d retries for '%s'",
                         self.MAX_RETRIES, symbol)
            raise RuntimeError(
                f"Yahoo Finance failed after {self.MAX_RETRIES} attempts "
                f"for '{symbol}': {last_err}"
            ) from last_err

        if hist.empty:
            logger.error("YahooFinance returned no data for '%s' (%s to %s)",
                         symbol, start_date, end_date)
            raise ValueError(
                f"Yahoo Finance returned no data for '{symbol}' "
                f"({start_date} to {end_date})"
            )

        df = pd.DataFrame({
            "t": hist.index.strftime("%Y-%m-%d"),
            "v": hist["Close"].values,
        })
        df["v"] = df["v"].astype(float)
        # Include OHLC columns for indicators that need them (e.g. stochastic)
        for col in ("Open", "High", "Low", "Close", "Volume"):
            if col in hist.columns:
                df[col] = hist[col].values.astype(float)
        logger.info("YahooFinance: fetched %d rows for %s (%s to %s)",
                    len(df), symbol, start_date, end_date)
        return df.reset_index(drop=True)


class NasdaqDataLink:
    """Retrieve data from Nasdaq Data Link (formerly Quandl).

    Supports time-series datasets (e.g. CHRIS/CME_CL1, FRED/GDP) and
    table-based data (e.g. WIKI/PRICES, ZACKS/FC).

    API key required (free tier: 50 calls/day, 300 time-series datasets).
    Set NASDAQ_DATA_LINK_API_KEY in .env.
    See: https://docs.data.nasdaq.com/docs/python-installation
    """

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv('NASDAQ_DATA_LINK_API_KEY')
        if not self.__api_key:
            raise ValueError("NASDAQ_DATA_LINK_API_KEY must be set in .env")
        import nasdaqdatalink
        nasdaqdatalink.ApiConfig.api_key = self.__api_key

    @lru_cache(maxsize=32)
    def get_historical_price(self, dataset_code, start_date, end_date,
                             column='Close'):
        """Fetch time-series data from Nasdaq Data Link.

        Uses nasdaqdatalink.get() which returns a DataFrame with
        DatetimeIndex and one or more value columns.

        Args:
            dataset_code: Dataset code (e.g. 'WIKI/AAPL', 'CHRIS/CME_CL1').
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            column: Column name to use as the value. Defaults to 'Close'.
                Falls back to the last column if not found.

        Returns:
            DataFrame with columns ['t', 'v'] matching the pipeline interface.
            't' = date strings (YYYY-MM-DD), 'v' = float values.

        Raises:
            ValueError: If no data returned for the given dataset/range.
        """
        import nasdaqdatalink

        data = nasdaqdatalink.get(
            dataset_code,
            start_date=start_date,
            end_date=end_date,
        )

        if data.empty:
            raise ValueError(
                f"Nasdaq Data Link returned no data for '{dataset_code}' "
                f"({start_date} to {end_date})"
            )

        col_map = {c.lower(): c for c in data.columns}
        col_key = column.lower()
        if col_key in col_map:
            actual_col = col_map[col_key]
        else:
            actual_col = data.columns[-1]
            logger.warning(
                "Column '%s' not found in %s; using '%s'",
                column, dataset_code, actual_col,
            )

        df = pd.DataFrame({
            "t": data.index.strftime("%Y-%m-%d"),
            "v": data[actual_col].values,
        })
        df["v"] = df["v"].astype(float)
        logger.info("NasdaqDataLink: fetched %d rows for %s (%s to %s)",
                     len(df), dataset_code, start_date, end_date)
        return df.reset_index(drop=True)

    def get_table_data(self, table_code, **kwargs):
        """Fetch table (datatable) data from Nasdaq Data Link.

        Args:
            table_code: Table code (e.g. 'WIKI/PRICES', 'ZACKS/FC').
            **kwargs: Filter arguments passed to nasdaqdatalink.get_table().

        Returns:
            Raw DataFrame from the Nasdaq Data Link table API.
        """
        import nasdaqdatalink

        kwargs.setdefault('paginate', True)
        data = nasdaqdatalink.get_table(table_code, **kwargs)
        logger.info("NasdaqDataLink: fetched %d rows from table %s",
                     len(data), table_code)
        return data


if __name__ == "__main__":
    start = time.time()
    av = AlphaVantage()
    data = av.get_historical_price('BTC', '2020-05-11', '2021-04-03')
    end = time.time()
    print(f"Elapsed: {end - start:.2f}s")
    print(data.head())


