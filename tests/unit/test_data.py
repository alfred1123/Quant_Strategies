import json
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock


class TestGlassnode:
    @patch.dict("os.environ", {"GLASSNODE_API_KEY": "test_key"})
    @patch("data.pd.read_json")
    @patch("data.requests.get")
    def test_get_historical_price_returns_dataframe(self, mock_get, mock_read_json):
        mock_response = MagicMock()
        mock_response.text = '[{"t":"2020-05-11","v":8500},{"t":"2020-05-12","v":8600}]'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        expected_df = pd.DataFrame([
            {"t": "2020-05-11", "v": 8500.0},
            {"t": "2020-05-12", "v": 8600.0},
        ])
        mock_read_json.return_value = expected_df

        from data import Glassnode
        gn = Glassnode()
        gn.get_historical_price.cache_clear()
        df = gn.get_historical_price("BTC", "2020-05-11", "2020-05-13")

        assert isinstance(df, pd.DataFrame)
        assert "t" in df.columns
        assert "v" in df.columns
        assert len(df) == 2

    @patch.dict("os.environ", {"GLASSNODE_API_KEY": "test_key"})
    @patch("data.pd.read_json", return_value=pd.DataFrame({"t": ["x"], "v": [1]}))
    @patch("data.requests.get")
    def test_get_historical_price_calls_api_with_params(self, mock_get, _):
        mock_response = MagicMock()
        mock_response.text = "[]"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import Glassnode
        gn = Glassnode()
        gn.get_historical_price.cache_clear()
        gn.get_historical_price("ETH", "2021-01-01", "2021-01-02", "1h")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["a"] == "ETH"
        assert params["i"] == "1h"
        # API key now sent via header, not query params
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["X-Api-Key"] == "test_key"

    @patch.dict("os.environ", {"GLASSNODE_API_KEY": "test_key"})
    @patch("data.pd.read_json", return_value=pd.DataFrame({"t": ["x"], "v": [1]}))
    @patch("data.requests.get")
    def test_get_historical_price_default_resolution(self, mock_get, _):
        mock_response = MagicMock()
        mock_response.text = "[]"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import Glassnode
        gn = Glassnode()
        gn.get_historical_price.cache_clear()
        gn.get_historical_price("BTC", "2020-05-11", "2020-05-12")

        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[1].get("params")
        assert params["i"] == "24h"

    def test_init_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr("data.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("GLASSNODE_API_KEY", raising=False)
        from data import Glassnode
        with pytest.raises(ValueError, match="GLASSNODE_API_KEY"):
            Glassnode()


class TestFutuOpenD:
    @patch("data.load_dotenv", lambda *a, **kw: None)
    @patch.dict("os.environ", {"FUTU_HOST": "127.0.0.1", "FUTU_PORT": "11111"})
    @patch("data.futu.OpenQuoteContext")
    def test_init_loads_env(self, mock_ctx):
        from data import FutuOpenD
        futu_src = FutuOpenD()
        assert futu_src._FutuOpenD__host == "127.0.0.1"
        assert futu_src._FutuOpenD__port == 11111

    @patch("data.load_dotenv", lambda *a, **kw: None)
    @patch.dict("os.environ", {"FUTU_HOST": "127.0.0.1", "FUTU_PORT": "11111"})
    @patch("data.futu.OpenQuoteContext")
    def test_get_historical_data_calls_api(self, mock_ctx_cls):
        mock_ctx = MagicMock()
        mock_ctx_cls.return_value = mock_ctx
        mock_df = pd.DataFrame({"close": [100, 101]})
        mock_ctx.request_history_kline.return_value = (0, mock_df, None)
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        from data import FutuOpenD
        futu_src = FutuOpenD()
        futu_src.get_historical_data.cache_clear()
        result = futu_src.get_historical_data("HK.00700", "2021-01-01", "2021-01-31")

        assert isinstance(result, pd.DataFrame)

    @patch("data.load_dotenv", lambda *a, **kw: None)
    @patch.dict("os.environ", {"FUTU_HOST": "127.0.0.1", "FUTU_PORT": "11111"})
    @patch("data.futu.OpenQuoteContext")
    def test_get_historical_data_raises_on_error(self, mock_ctx_cls):
        mock_ctx = MagicMock()
        mock_ctx_cls.return_value = mock_ctx
        mock_ctx.request_history_kline.return_value = (-1, "connection error", None)
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        from data import FutuOpenD
        futu_src = FutuOpenD()
        futu_src.get_historical_data.cache_clear()
        with pytest.raises(RuntimeError, match="Futu API error"):
            futu_src.get_historical_data("HK.00700", "2021-01-01", "2021-01-31")

    @patch("data.load_dotenv", lambda *a, **kw: None)
    def test_init_raises_without_env_vars(self, monkeypatch):
        monkeypatch.delenv("FUTU_HOST", raising=False)
        monkeypatch.delenv("FUTU_PORT", raising=False)
        from data import FutuOpenD
        with pytest.raises(ValueError, match="FUTU_HOST"):
            FutuOpenD()


class TestAlphaVantage:
    EQUITY_RESPONSE = {
        "Meta Data": {"1. Information": "Daily Prices"},
        "Time Series (Daily)": {
            "2021-01-04": {"1. open": "133.52", "2. high": "133.61", "3. low": "126.76", "4. close": "129.41", "5. volume": "143301900"},
            "2021-01-05": {"1. open": "128.89", "2. high": "131.74", "3. low": "128.43", "4. close": "131.01", "5. volume": "97664900"},
        },
    }

    CRYPTO_RESPONSE = {
        "Meta Data": {"1. Information": "Daily Prices"},
        "Time Series (Digital Currency Daily)": {
            "2021-01-04": {"1a. open (USD)": "33000", "2a. high (USD)": "34000", "3a. low (USD)": "32000", "4a. close (USD)": "33500", "5. volume": "1234", "6. market cap (USD)": "0"},
            "2021-01-05": {"1a. open (USD)": "33500", "2a. high (USD)": "35000", "3a. low (USD)": "33000", "4a. close (USD)": "34200", "5. volume": "1345", "6. market cap (USD)": "0"},
        },
    }

    @patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"})
    @patch("data.requests.get")
    def test_get_equity_price_returns_dataframe(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = self.EQUITY_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import AlphaVantage
        av = AlphaVantage()
        av.get_historical_price.cache_clear()
        df = av.get_historical_price("IBM", "2021-01-04", "2021-01-05")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["t", "v"]
        assert len(df) == 2
        assert df.iloc[0]["v"] == 129.41
        assert df.iloc[1]["v"] == 131.01

    @patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"})
    @patch("data.requests.get")
    def test_get_crypto_price_returns_dataframe(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = self.CRYPTO_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import AlphaVantage
        av = AlphaVantage()
        av.get_historical_price.cache_clear()
        df = av.get_historical_price("BTC", "2021-01-04", "2021-01-05")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["t", "v"]
        assert len(df) == 2
        assert df.iloc[0]["v"] == 33500.0

    @patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"})
    @patch("data.requests.get")
    def test_filters_by_date_range(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = self.EQUITY_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import AlphaVantage
        av = AlphaVantage()
        av.get_historical_price.cache_clear()
        df = av.get_historical_price("IBM", "2021-01-04", "2021-01-04")

        assert len(df) == 1
        assert df.iloc[0]["t"] == "2021-01-04"

    @patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"})
    @patch("data.requests.get")
    def test_raises_on_api_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"Error Message": "Invalid API call"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import AlphaVantage
        av = AlphaVantage()
        av.get_historical_price.cache_clear()
        with pytest.raises(ValueError, match="AlphaVantage error"):
            av.get_historical_price("INVALID", "2021-01-01", "2021-01-02")

    def test_init_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr("data.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
        from data import AlphaVantage
        with pytest.raises(ValueError, match="ALPHAVANTAGE_API_KEY"):
            AlphaVantage()

    @patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"})
    @patch("data.requests.get")
    def test_uses_correct_endpoint_for_equity(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = self.EQUITY_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import AlphaVantage
        av = AlphaVantage()
        av.get_historical_price.cache_clear()
        av.get_historical_price("IBM", "2021-01-04", "2021-01-05")

        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[1].get("params")
        assert params["function"] == "TIME_SERIES_DAILY"

    @patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"})
    @patch("data.requests.get")
    def test_uses_correct_endpoint_for_crypto(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = self.CRYPTO_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from data import AlphaVantage
        av = AlphaVantage()
        av.get_historical_price.cache_clear()
        av.get_historical_price("BTC", "2021-01-04", "2021-01-05")

        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[1].get("params")
        assert params["function"] == "DIGITAL_CURRENCY_DAILY"


class TestYahooFinance:
    """Tests for YahooFinance data source.

    Mock structure mirrors yfinance.Ticker.history() which returns a
    DataFrame with DatetimeIndex and 'Close' column (among others).
    yfinance is lazy-imported inside the method, so we patch 'yfinance.Ticker'.
    See: https://github.com/ranaroussi/yfinance#quick-start
    """

    def _make_mock_history(self, dates, closes):
        """Build a DataFrame matching yfinance Ticker.history() output."""
        idx = pd.DatetimeIndex(dates)
        return pd.DataFrame({"Close": closes, "Open": closes, "High": closes, "Low": closes, "Volume": [100] * len(closes)}, index=idx)

    @patch("yfinance.Ticker")
    def test_get_historical_price_returns_dataframe(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_history(
            ["2021-01-04", "2021-01-05"],
            [129.41, 131.01],
        )
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        df = yf_src.get_historical_price("AAPL", "2021-01-04", "2021-01-05")

        assert isinstance(df, pd.DataFrame)
        assert "t" in df.columns
        assert "v" in df.columns
        assert "High" in df.columns
        assert "Low" in df.columns
        assert "Close" in df.columns
        assert len(df) == 2
        assert df.iloc[0]["v"] == pytest.approx(129.41)
        assert df.iloc[1]["v"] == pytest.approx(131.01)

    @patch("yfinance.Ticker")
    def test_get_historical_price_formats_dates(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_history(
            ["2021-06-15"], [150.0],
        )
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        df = yf_src.get_historical_price("MSFT", "2021-06-15", "2021-06-15")

        assert df.iloc[0]["t"] == "2021-06-15"

    @patch("yfinance.Ticker")
    def test_get_historical_price_passes_correct_params(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_history(
            ["2021-01-04"], [100.0],
        )
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        yf_src.get_historical_price("AAPL", "2016-01-01", "2026-01-01")

        mock_ticker_cls.assert_called_once_with("AAPL")
        mock_ticker.history.assert_called_once_with(
            start="2016-01-01", end="2026-01-01", auto_adjust=True,
            timeout=30,
        )

    @patch("yfinance.Ticker")
    def test_raises_on_empty_response(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        with pytest.raises(ValueError, match="no data"):
            yf_src.get_historical_price("INVALID", "2021-01-01", "2021-01-02")

    @patch("yfinance.Ticker")
    def test_close_values_are_float(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_history(
            ["2021-01-04", "2021-01-05"], [100, 200],
        )
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        df = yf_src.get_historical_price("SPY", "2021-01-04", "2021-01-05")

        assert df["v"].dtype == float

    @patch("time.sleep")
    @patch("yfinance.Ticker")
    def test_retries_on_failure(self, mock_ticker_cls, _mock_sleep):
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = [
            Exception("rate limited"),
            self._make_mock_history(["2021-01-04"], [100.0]),
        ]
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        df = yf_src.get_historical_price("AAPL", "2021-01-04", "2021-01-04")

        assert len(df) == 1
        assert mock_ticker.history.call_count == 2

    @patch("time.sleep")
    @patch("yfinance.Ticker")
    def test_raises_after_max_retries(self, mock_ticker_cls, _mock_sleep):
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("blocked")
        mock_ticker_cls.return_value = mock_ticker

        from data import YahooFinance
        yf_src = YahooFinance()
        yf_src.get_historical_price.cache_clear()
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            yf_src.get_historical_price("AAPL", "2021-01-04", "2021-01-04")


class TestNasdaqDataLink:
    """Tests for NasdaqDataLink data source.

    Mocks nasdaqdatalink.get() which returns a DataFrame with DatetimeIndex.
    See: https://github.com/Nasdaq/data-link-python#retrieving-data
    """

    def _make_time_series(self, dates, values, col_name="Close"):
        """Build a DataFrame matching nasdaqdatalink.get() output."""
        idx = pd.DatetimeIndex(dates)
        return pd.DataFrame({col_name: values}, index=idx)

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_get_historical_price_returns_dataframe(self, mock_get, _mock_cfg):
        mock_get.return_value = self._make_time_series(
            ["2021-01-04", "2021-01-05"], [129.41, 131.01],
        )

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        df = src.get_historical_price("WIKI/AAPL", "2021-01-04", "2021-01-05")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["t", "v"]
        assert len(df) == 2
        assert df.iloc[0]["v"] == pytest.approx(129.41)
        assert df.iloc[1]["v"] == pytest.approx(131.01)

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_get_historical_price_passes_correct_params(self, mock_get, _mock_cfg):
        mock_get.return_value = self._make_time_series(
            ["2021-01-04"], [100.0],
        )

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        src.get_historical_price("CHRIS/CME_CL1", "2016-01-01", "2026-01-01")

        mock_get.assert_called_once_with(
            "CHRIS/CME_CL1",
            start_date="2016-01-01",
            end_date="2026-01-01",
        )

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_raises_on_empty_response(self, mock_get, _mock_cfg):
        mock_get.return_value = pd.DataFrame()

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        with pytest.raises(ValueError, match="no data"):
            src.get_historical_price("INVALID/CODE", "2021-01-01", "2021-01-02")

    def test_init_raises_without_api_key(self, monkeypatch):
        monkeypatch.setattr("data.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("NASDAQ_DATA_LINK_API_KEY", raising=False)
        from data import NasdaqDataLink
        with pytest.raises(ValueError, match="NASDAQ_DATA_LINK_API_KEY"):
            NasdaqDataLink()

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_close_values_are_float(self, mock_get, _mock_cfg):
        mock_get.return_value = self._make_time_series(
            ["2021-01-04", "2021-01-05"], [100, 200],
        )

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        df = src.get_historical_price("WIKI/AAPL", "2021-01-04", "2021-01-05")

        assert df["v"].dtype == float

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_formats_dates_as_strings(self, mock_get, _mock_cfg):
        mock_get.return_value = self._make_time_series(
            ["2021-06-15"], [150.0],
        )

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        df = src.get_historical_price("WIKI/MSFT", "2021-06-15", "2021-06-15")

        assert df.iloc[0]["t"] == "2021-06-15"

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_falls_back_to_last_column(self, mock_get, _mock_cfg):
        """When the requested column doesn't exist, use the last column."""
        idx = pd.DatetimeIndex(["2021-01-04"])
        mock_get.return_value = pd.DataFrame(
            {"Value": [42.0], "Settle": [43.0]}, index=idx,
        )

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        df = src.get_historical_price("CHRIS/CME_CL1", "2021-01-04", "2021-01-04")

        # 'Close' not found → falls back to last column 'Settle'
        assert df.iloc[0]["v"] == pytest.approx(43.0)

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get")
    def test_custom_column_parameter(self, mock_get, _mock_cfg):
        """User can specify which column to extract as 'v'."""
        idx = pd.DatetimeIndex(["2021-01-04"])
        mock_get.return_value = pd.DataFrame(
            {"Value": [42.0], "Settle": [43.0]}, index=idx,
        )

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        src.get_historical_price.cache_clear()
        df = src.get_historical_price(
            "CHRIS/CME_CL1", "2021-01-04", "2021-01-04", column="Value",
        )

        assert df.iloc[0]["v"] == pytest.approx(42.0)

    @patch.dict("os.environ", {"NASDAQ_DATA_LINK_API_KEY": "test_key"})
    @patch("nasdaqdatalink.ApiConfig")
    @patch("nasdaqdatalink.get_table")
    def test_get_table_data_returns_dataframe(self, mock_get_table, _mock_cfg):
        mock_get_table.return_value = pd.DataFrame({
            "ticker": ["AAPL", "AAPL"],
            "date": ["2021-01-04", "2021-01-05"],
            "close": [129.41, 131.01],
        })

        from data import NasdaqDataLink
        src = NasdaqDataLink()
        df = src.get_table_data("WIKI/PRICES", ticker="AAPL")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        mock_get_table.assert_called_once_with(
            "WIKI/PRICES", paginate=True, ticker="AAPL",
        )


class TestInstrumentCache:
    """Unit tests for InstrumentCache — all DB calls mocked."""

    SAMPLE_PRODUCTS = [
        {"product_id": 1, "product_vid": 1, "is_current_ind": "Y",
         "internal_cusip": "btc-usd.crypto", "display_nm": "Bitcoin",
         "asset_type_id": 1, "exchange": None, "ccy": "USD", "description": None},
        {"product_id": 2, "product_vid": 1, "is_current_ind": "Y",
         "internal_cusip": "eth-usd.crypto", "display_nm": "Ethereum",
         "asset_type_id": 1, "exchange": None, "ccy": "USD", "description": None},
    ]

    SAMPLE_XREFS = [
        {"product_xref_id": 1, "product_xref_vid": 1, "product_id": 1,
         "internal_cusip": "btc-usd.crypto", "display_nm": "Bitcoin",
         "app_id": 1, "vendor_symbol": "BTC-USD", "is_current_ind": "Y"},
        {"product_xref_id": 2, "product_xref_vid": 1, "product_id": 1,
         "internal_cusip": "btc-usd.crypto", "display_nm": "Bitcoin",
         "app_id": 2, "vendor_symbol": "BTC", "is_current_ind": "Y"},
        {"product_xref_id": 3, "product_xref_vid": 1, "product_id": 2,
         "internal_cusip": "eth-usd.crypto", "display_nm": "Ethereum",
         "app_id": 1, "vendor_symbol": "ETH-USD", "is_current_ind": "Y"},
    ]

    @pytest.fixture()
    def cache(self):
        from data import InstrumentCache
        c = InstrumentCache.__new__(InstrumentCache)
        c._conninfo = "dummy"
        c.user_id = "test"
        c._products = list(self.SAMPLE_PRODUCTS)
        c._xrefs = list(self.SAMPLE_XREFS)
        return c

    def test_get_products_returns_all(self, cache):
        assert len(cache.get_products()) == 2

    def test_get_product_by_id_found(self, cache):
        p = cache.get_product_by_id(1)
        assert p["internal_cusip"] == "btc-usd.crypto"

    def test_get_product_by_id_not_found(self, cache):
        assert cache.get_product_by_id(999) is None

    def test_get_product_by_cusip_found(self, cache):
        p = cache.get_product_by_cusip("eth-usd.crypto")
        assert p["product_id"] == 2

    def test_get_product_by_cusip_not_found(self, cache):
        assert cache.get_product_by_cusip("nonexistent") is None

    def test_get_xrefs_unfiltered(self, cache):
        assert len(cache.get_xrefs()) == 3

    def test_get_xrefs_by_product_id(self, cache):
        xrefs = cache.get_xrefs(product_id=1)
        assert len(xrefs) == 2
        assert all(x["product_id"] == 1 for x in xrefs)

    def test_get_xrefs_by_app_id(self, cache):
        xrefs = cache.get_xrefs(app_id=1)
        assert len(xrefs) == 2
        assert all(x["app_id"] == 1 for x in xrefs)

    def test_get_xrefs_by_product_and_app(self, cache):
        xrefs = cache.get_xrefs(product_id=1, app_id=2)
        assert len(xrefs) == 1
        assert xrefs[0]["vendor_symbol"] == "BTC"

    def test_resolve_vendor_symbol_found(self, cache):
        assert cache.resolve_vendor_symbol(1, 1) == "BTC-USD"
        assert cache.resolve_vendor_symbol(1, 2) == "BTC"
        assert cache.resolve_vendor_symbol(2, 1) == "ETH-USD"

    def test_resolve_vendor_symbol_not_found(self, cache):
        assert cache.resolve_vendor_symbol(2, 2) is None
        assert cache.resolve_vendor_symbol(999, 1) is None

    @patch("data.DbGateway._call_get")
    def test_load_all_calls_both_procs(self, mock_call_get):
        from data import InstrumentCache
        mock_call_get.side_effect = [self.SAMPLE_PRODUCTS, self.SAMPLE_XREFS]
        c = InstrumentCache("dummy")
        c.load_all()
        assert len(c.get_products()) == 2
        assert len(c.get_xrefs()) == 3
        assert mock_call_get.call_count == 2
