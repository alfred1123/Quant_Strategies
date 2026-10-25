"""External data sources for the backtest pipeline.

Supported sources:
    1. FutuOpenD — HK/US equity via Futu API
    2. Glassnode — on-chain crypto metrics
    3. AlphaVantage — equity and crypto price data
    4. YahooFinance — free equity/crypto/ETF data via yfinance
    5. NasdaqDataLink — time-series and table data via Nasdaq Data Link API

Live exchange OHLCV and ccxt trading live in ``quant/market_data/`` and ``quant/trade/brokers/ccxt/``.
"""

import logging
import os
import time
from datetime import datetime, timezone
from io import StringIO

import futu
import pandas as pd
import requests

logger = logging.getLogger(__name__)


def utc_epoch(day: str) -> int:
    """Seconds since the epoch at ``00:00 UTC`` on *day* (``YYYY-MM-DD``).

    A vendor window is a UTC fact. ``time.mktime`` would read the same date
    in the host's zone, so one request asked for different bars on a UTC
    server and on a laptop in Hong Kong.
    """
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


class FutuOpenD:
    """Retrieve equity data from Futu OpenD gateway."""

    def __init__(self) -> None:
        self.__host = os.getenv('FUTU_HOST')
        port_str = os.getenv('FUTU_PORT')
        if not self.__host or not port_str:
            raise ValueError("FUTU_HOST and FUTU_PORT are not set")
        self.__port = int(port_str)
        self.quote_ctx = futu.OpenQuoteContext(host=self.__host, port=self.__port)

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
    """Retrieve on-chain crypto metrics from Glassnode.

    ``GLASSNODE_API_KEY`` is read from the process environment. ``load_config()``
    puts it there from SSM or ``.env``. This class does not load a file.
    Every Glassnode HTTP call goes through :meth:`_get`.
    """

    BASE_URL = "https://api.glassnode.com"
    _TIMEOUT_S = 30

    def __init__(self) -> None:
        api_key = os.getenv("GLASSNODE_API_KEY")
        if not api_key:
            raise ValueError("GLASSNODE_API_KEY is not set")
        self.__api_key = api_key

    def get_historical_price(self, symbol, start_date, end_date, resolution="24h", *, metric_path: str):
        """Fetch one Glassnode series.

        ``metric_path`` is ``REFDATA.APP_METRIC.METRIC_PATH`` for the app the
        caller selected. The fetch does not substitute a path of its own.

        Args:
            symbol: Crypto asset (e.g. 'BTC').
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            resolution: Data interval. Defaults to '24h'.
            metric_path: Path under ``/v1/metrics/``.

        Returns:
            DataFrame with columns ['t', 'v'].

        Raises:
            requests.HTTPError: If the API request fails.
        """
        since = utc_epoch(start_date)
        until = utc_epoch(end_date)
        res = self._get(
            f"/v1/metrics/{metric_path}",
            {"a": symbol, "s": since, "u": until, "i": resolution},
        )
        # pandas 3 reads a bare string as a path, so the body has to be a buffer.
        df = pd.read_json(StringIO(res.text), convert_dates=["t"])
        logger.info("Glassnode: fetched %d rows for %s", len(df), symbol)
        return df

    def list_asset_symbols(self) -> list[str]:
        """Assets this provider lists, from ``GET /v1/metadata/assets``.

        ``symbol`` on each ``data`` row is the asset a metric's ``a``
        parameter accepts. An empty ``data`` array is an empty catalog. A
        body without that array is not an empty catalog.

        Raises:
            requests.HTTPError: The asset list could not be read.
            RuntimeError: The body has no ``data`` array.
        """
        symbols = self._asset_symbols(self._get("/v1/metadata/assets").json())
        logger.info("Glassnode: asset list has %d symbol(s)", len(symbols))
        return symbols

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        """One authenticated GET. Callers pass a path under :attr:`BASE_URL`."""
        res = requests.get(
            f"{self.BASE_URL}{path}",
            params=params,
            headers={"X-Api-Key": self.__api_key},
            timeout=self._TIMEOUT_S,
        )
        res.raise_for_status()
        return res

    @staticmethod
    def _asset_symbols(body: object) -> list[str]:
        """``symbol`` values from a metadata-assets body.

        Raises:
            RuntimeError: ``body`` has no ``data`` array.
        """
        rows = body.get("data") if isinstance(body, dict) else None
        if rows is None or not isinstance(rows, list):
            raise RuntimeError("Glassnode asset list has no data array")
        symbols: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                symbols.append(symbol.strip())
        return symbols


class AlphaVantage:
    """Retrieve equity and crypto price data from Alpha Vantage."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        self.__api_key = os.getenv('ALPHAVANTAGE_API_KEY')
        if not self.__api_key:
            raise ValueError("ALPHAVANTAGE_API_KEY is not set")

    def get_historical_price(self, symbol, start_date, end_date, resolution='daily'):
        """Fetch daily close prices from Alpha Vantage.

        Automatically detects crypto symbols (BTC, ETH, etc.) and uses the
        appropriate endpoint (DIGITAL_CURRENCY_DAILY vs TIME_SERIES_DAILY).
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

        df = df[(df['t'] >= start_date) & (df['t'] <= end_date)]
        df = df.sort_values('t').reset_index(drop=True)
        return df

    def _fetch_daily(self, function, symbol, ts_key, close_field, extra_params=None):
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
        res = requests.get(self.BASE_URL, params=params, timeout=30)
        res.raise_for_status()
        return res.json()


class YahooFinance:
    """Retrieve free historical price data via Yahoo Finance (yfinance).

    No API key required. Supports equities, ETFs, indices, and crypto.
    yfinance is an unofficial scraper — Yahoo may rate-limit or block
    requests. This class lazy-imports yfinance, retries on failure, and
    sleeps between attempts.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds between retries

    def get_historical_price(self, symbol, start_date, end_date):
        """Fetch daily close prices from Yahoo Finance."""
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
    """

    def __init__(self) -> None:
        self.__api_key = os.getenv('NASDAQ_DATA_LINK_API_KEY')
        if not self.__api_key:
            raise ValueError("NASDAQ_DATA_LINK_API_KEY is not set")
        import nasdaqdatalink
        nasdaqdatalink.ApiConfig.api_key = self.__api_key

    def get_historical_price(self, dataset_code, start_date, end_date,
                             column='Close'):
        """Fetch time-series data from Nasdaq Data Link."""
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
        """Fetch table (datatable) data from Nasdaq Data Link."""
        import nasdaqdatalink

        kwargs.setdefault('paginate', True)
        data = nasdaqdatalink.get_table(table_code, **kwargs)
        logger.info("NasdaqDataLink: fetched %d rows from table %s",
                     len(data), table_code)
        return data
