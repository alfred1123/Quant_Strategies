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
        assert params["api_key"] == "test_key"

    @patch.dict("os.environ", {"GLASSNODE_API_KEY": "test_key"})
    @patch("data.pd.read_json", return_value=pd.DataFrame({"t": ["x"], "v": [1]}))
    @patch("data.requests.get")
    def test_get_historical_price_default_resolution(self, mock_get, _):
        mock_response = MagicMock()
        mock_response.text = "[]"
        mock_get.return_value = mock_response

        from data import Glassnode
        gn = Glassnode()
        gn.get_historical_price.cache_clear()
        gn.get_historical_price("BTC", "2020-05-11", "2020-05-12")

        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[1].get("params")
        assert params["i"] == "24h"


class TestFutuOpenD:
    @patch.dict("os.environ", {"FUTU_HOST": "127.0.0.1", "FUTU_PORT": "11111"})
    @patch("data.futu.OpenQuoteContext")
    def test_init_loads_env(self, mock_ctx):
        from data import FutuOpenD
        futu = FutuOpenD()
        assert futu._FutuOpenD__host == "127.0.0.1"
        assert futu._FutuOpenD__port == 11111

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
        futu = FutuOpenD()
        futu.get_historical_data.cache_clear()
        result = futu.get_historical_data("HK.00700", "2021-01-01", "2021-01-31")

        assert isinstance(result, pd.DataFrame)
