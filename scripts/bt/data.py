"""
Data source classes for the backtest pipeline.

Supported sources:
    1. FutuOpenD — HK/US equity via Futu API
    2. Glassnode — on-chain crypto metrics
    3. AlphaVantage — equity and crypto price data
    4. YahooFinance — free equity/crypto/ETF data via yfinance

BybitData class moved to backup/deco/ — platform decommissioned.
"""

import os
import time
from functools import lru_cache

import futu
import pandas as pd
import requests
from dotenv import load_dotenv


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
            raise RuntimeError(f"Futu API error (ret={ret}): {data}")
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
            raise ValueError(f"AlphaVantage error: {data.get('Error Message', data)}")
        rows = [
            {"t": date, "v": float(vals[close_field])}
            for date, vals in data[ts_key].items()
        ]
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
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
        else:
            raise RuntimeError(
                f"Yahoo Finance failed after {self.MAX_RETRIES} attempts "
                f"for '{symbol}': {last_err}"
            ) from last_err

        if hist.empty:
            raise ValueError(
                f"Yahoo Finance returned no data for '{symbol}' "
                f"({start_date} to {end_date})"
            )

        df = pd.DataFrame({
            "t": hist.index.strftime("%Y-%m-%d"),
            "v": hist["Close"].values,
        })
        df["v"] = df["v"].astype(float)
        return df.reset_index(drop=True)


if __name__ == "__main__":
    start = time.time()
    av = AlphaVantage()
    data = av.get_historical_price('BTC', '2020-05-11', '2021-04-03')
    end = time.time()
    print(f"Elapsed: {end - start:.2f}s")
    print(data.head())


