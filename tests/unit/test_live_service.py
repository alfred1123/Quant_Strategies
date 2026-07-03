"""Unit tests for live strategy evaluation."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from quant.queue.repo import BtQueueRepo
from quant.strategy.live_service import (
    LiveEvaluationError,
    build_data_dict_for_signal,
    compute_latest_position,
)
from quant.strategy.signals import Strategy, StrategyConfig, config_from_json, strategy_to_json


def _sample_df(n: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    price = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    return pd.DataFrame({"price": price, "factor": price})


@pytest.fixture
def strategy_json_doc():
    cfg = StrategyConfig.single(
        "btc-usd.crypto",
        "get_bollinger_band",
        Strategy.momentum_band_signal,
        365,
        window=20,
        signal=1.0,
        strategy_id=str(uuid4()),
    )
    return strategy_to_json(cfg)


@pytest.fixture
def data_caches():
    caches = MagicMock()
    caches.refdata.get.side_effect = lambda table: {
        "indicator": [{"method_name": "get_bollinger_band", "is_bounded_ind": "N"}],
        "signal_type": [
            {
                "name": "momentum",
                "func_name_band": "momentum_band_signal",
                "func_name_bounded": "momentum_bounded_signal",
            }
        ],
        "app": [{"name": "glassnode", "app_id": 2, "class_name": "Glassnode"}],
    }.get(table, [])
    caches.instrument_cache = MagicMock()
    caches.backtest_cache = None
    return caches


class TestConfigFromJson:
    def test_round_trip(self, strategy_json_doc):
        cfg = config_from_json(strategy_json_doc)
        assert cfg.internal_cusip == "btc-usd.crypto"
        assert cfg.get_substrategies()[0].window == 20


class TestBuildDataDictForSignal:
    @patch("quant.strategy.live_service.fetch_df")
    @patch("quant.strategy.backtest_service._enforce_date_sync")
    def test_does_not_use_backtest_date_sync(
        self, mock_sync, mock_fetch, strategy_json_doc, data_caches
    ):
        mock_fetch.return_value = _sample_df()
        cfg = config_from_json(strategy_json_doc)
        cache = {
            "app": data_caches.refdata.get("app"),
            "indicator": data_caches.refdata.get("indicator"),
            "signal_type": data_caches.refdata.get("signal_type"),
        }
        build_data_dict_for_signal(
            cfg,
            None,
            start="2024-01-01",
            end="2024-06-01",
            cache=cache,
            inst_cache=data_caches.instrument_cache,
            bt_cache=None,
        )
        mock_sync.assert_not_called()


class TestComputeLatestPosition:
    @patch("quant.strategy.live_service.fetch_df")
    def test_strategy_json_format(self, mock_fetch, strategy_json_doc, data_caches):
        mock_fetch.return_value = _sample_df()

        position, as_of = compute_latest_position(
            strategy_json_doc,
            result_payload=None,
            caches=data_caches,
        )

        assert position in (-1.0, 0.0, 1.0)
        assert as_of

    @patch("quant.strategy.live_service.fetch_df")
    def test_optimize_format_requires_result(self, mock_fetch, data_caches):
        config_json = {
            "symbol": "btc-usd.crypto",
            "start": "2020-01-01",
            "end": "2024-01-01",
            "trading_period": 365,
            "data_source": "glassnode",
            "factors": [
                {
                    "indicator": "get_bollinger_band",
                    "strategy": "momentum",
                    "data_column": "price",
                    "window_range": {"min": 20, "max": 20, "step": 1},
                    "signal_range": {"min": 1.0, "max": 1.0, "step": 0.1},
                }
            ],
        }
        data_caches.refdata.get.side_effect = lambda table: {
            "indicator": [{"method_name": "get_bollinger_band", "is_bounded_ind": "N"}],
            "signal_type": [
                {
                    "name": "momentum",
                    "func_name_band": "momentum_band_signal",
                    "func_name_bounded": "momentum_bounded_signal",
                }
            ],
            "app": [{"name": "glassnode", "app_id": 2, "class_name": "Glassnode"}],
        }.get(table, [])

        with pytest.raises(LiveEvaluationError, match="no optimization result"):
            compute_latest_position(config_json, result_payload=None, caches=data_caches)

        mock_fetch.return_value = _sample_df()
        payload = {"best": {"window": 20, "signal": 1.0, "sharpe": 1.2}}
        position, _ = compute_latest_position(
            config_json, result_payload=payload, caches=data_caches
        )
        assert position in (-1.0, 0.0, 1.0)


class TestFetchResultPayload:
    def test_returns_payload_for_matching_vid(self):
        bt = BtQueueRepo("postgresql://test")
        qid = uuid4()
        with patch.object(bt, "sp_get_queue") as mock_queue, patch.object(
            bt, "sp_get_result"
        ) as mock_result:
            mock_queue.return_value = [
                {"queue_id": qid, "strategy_vid": 2},
                {"queue_id": uuid4(), "strategy_vid": 1},
            ]
            mock_result.return_value = {
                "payload_json": {"best": {"window": 20, "signal": 1.0}},
            }

            payload = bt.fetch_result_payload(uuid4(), 2)
            assert payload["best"]["window"] == 20
            mock_result.assert_called_once_with(qid)

    def test_returns_none_when_missing(self):
        bt = BtQueueRepo("postgresql://test")
        with patch.object(bt, "sp_get_queue", return_value=[]):
            assert bt.fetch_result_payload(uuid4(), 1) is None
