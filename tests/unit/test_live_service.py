"""Unit tests for live strategy evaluation."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from quant.queue.repo import BtQueueRepo
from quant.strategy.live_service import (
    LiveEvaluationError,
    bars_loader,
    build_data_dict_for_signal,
    compute_latest_position,
    provider_loader,
)
from quant.strategy.performance import live_lookback_bars, live_lookback_days
from quant.strategy.signals import Strategy, StrategyConfig, config_from_json, strategy_to_json


def _sample_df(n: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    price = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    return pd.DataFrame({"price": price, "factor": price})


@pytest.fixture
def strategy_json_doc():
    cfg = StrategyConfig.single(
        "btcusdt.crypto",
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
        assert cfg.internal_cusip == "btcusdt.crypto"
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
            provider_loader(
                cfg,
                None,
                start="2024-01-01",
                end="2024-06-01",
                cache=cache,
                inst_cache=data_caches.instrument_cache,
                bt_cache=None,
            ),
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
            "symbol": "btcusdt.crypto",
            "start": "2020-01-01",
            "end": "2024-01-01",
            "trading_period": 365,
            "data_source": "glassnode",
            "tm_interval_id": 1,
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


class TestLiveLookbackBars:
    def test_scales_with_the_widest_indicator_window(self):
        assert live_lookback_bars(20) == 120
        assert live_lookback_bars((20, 50)) == 210

    def test_drops_the_calendar_floor_the_day_version_applies(self):
        """A 365 floor is weekends and holidays — meaningless in bar counts."""
        assert live_lookback_days(20, 365) == 365
        assert live_lookback_bars(20) == 120


class TestBuildDataDictFromBars:
    def _loader(self, calls):
        def loader(cusip, lookback):
            calls.append((cusip, lookback))
            return _sample_df()

        return loader

    def test_loads_every_symbol_the_strategy_reads(self, strategy_json_doc):
        calls = []
        cfg = config_from_json(strategy_json_doc)

        data = build_data_dict_for_signal(cfg, bars_loader(self._loader(calls), 120))

        assert calls == [("btcusdt.crypto", 120)]
        assert set(data) == {"btcusdt.crypto"}

    def test_empty_frame_is_refused(self, strategy_json_doc):
        cfg = config_from_json(strategy_json_doc)

        with pytest.raises(LiveEvaluationError, match="No data returned"):
            build_data_dict_for_signal(
                cfg, bars_loader(lambda *_: pd.DataFrame(), 120)
            )

    def test_loader_failures_propagate(self, strategy_json_doc):
        """Fail closed — a symbol the exchange can't serve stops the signal."""
        cfg = config_from_json(strategy_json_doc)

        def boom(*_):
            raise RuntimeError("exchange unreachable")

        with pytest.raises(RuntimeError, match="exchange unreachable"):
            build_data_dict_for_signal(cfg, bars_loader(boom, 120))


class TestCrossProductSymbols:
    """The symbol set comes from the config, so live matches backtest."""

    def _cross_product_req(self):
        return {
            "symbol": "btcusdt.crypto",
            "start": "2020-01-01",
            "end": "2024-01-01",
            "trading_period": 365,
            "data_source": "glassnode",
            "tm_interval_id": 1,
            "factors": [
                {
                    "indicator": "get_bollinger_band",
                    "strategy": "momentum",
                    "data_column": "price",
                    "vendor_symbol": "^VIX",
                    "data_source": "yahoo",
                    "window_range": {"min": 20, "max": 20, "step": 1},
                    "signal_range": {"min": 1.0, "max": 1.0, "step": 0.1},
                }
            ],
        }

    @patch("quant.strategy.live_service.fetch_df")
    def test_vendor_symbol_factor_is_loaded_under_the_key_performance_uses(
        self, mock_fetch, data_caches
    ):
        """`build_config` writes `vendor_symbol or symbol` onto the substrategy.

        Keying the data dict by `symbol` alone left `Performance` looking up a
        frame that was never loaded — a KeyError on any cross-product strategy.
        """
        mock_fetch.return_value = _sample_df()

        position, _ = compute_latest_position(
            self._cross_product_req(),
            result_payload={"best": {"window": 20, "signal": 1.0}},
            caches=data_caches,
        )

        loaded = {call.args[0] for call in mock_fetch.call_args_list}
        assert loaded == {"btcusdt.crypto", "^VIX"}
        assert position in (-1.0, 0.0, 1.0)

    @patch("quant.strategy.live_service.fetch_df")
    def test_per_factor_data_source_override_is_honoured(
        self, mock_fetch, data_caches
    ):
        mock_fetch.return_value = _sample_df()

        compute_latest_position(
            self._cross_product_req(),
            result_payload={"best": {"window": 20, "signal": 1.0}},
            caches=data_caches,
        )

        sources = {call.args[0]: call.args[3] for call in mock_fetch.call_args_list}
        assert sources == {"btcusdt.crypto": "glassnode", "^VIX": "yahoo"}

    def test_primary_symbol_is_loaded_first(self, data_caches):
        """An unavailable trade asset should fail before any factor work."""
        from quant.schemas.backtest import OptimizeRequest
        from quant.strategy.backtest_service import build_config

        cfg = build_config(
            OptimizeRequest.model_validate(self._cross_product_req()),
            {
                "indicator": data_caches.refdata.get("indicator"),
                "signal_type": data_caches.refdata.get("signal_type"),
            },
        )
        order = []
        build_data_dict_for_signal(
            cfg, lambda c: (order.append(c), _sample_df())[1]
        )

        assert order[0] == "btcusdt.crypto"


class TestComputeLatestPositionFromBars:
    @patch("quant.strategy.live_service.fetch_df")
    def test_bar_loader_replaces_the_provider(
        self, mock_fetch, strategy_json_doc, data_caches
    ):
        calls = []

        def loader(cusip, lookback):
            calls.append((cusip, lookback))
            return _sample_df()

        position, as_of = compute_latest_position(
            strategy_json_doc,
            result_payload=None,
            caches=data_caches,
            bar_loader=loader,
        )

        mock_fetch.assert_not_called()
        assert calls == [("btcusdt.crypto", live_lookback_bars(20))]
        assert position in (-1.0, 0.0, 1.0)
        assert as_of

    @patch("quant.strategy.live_service.fetch_df")
    def test_without_a_loader_the_provider_path_is_unchanged(
        self, mock_fetch, strategy_json_doc, data_caches
    ):
        mock_fetch.return_value = _sample_df()

        compute_latest_position(
            strategy_json_doc, result_payload=None, caches=data_caches
        )

        mock_fetch.assert_called()


class TestFetchResultPayload:
    def test_returns_payload_for_the_requested_vid(self):
        bt = BtQueueRepo("postgresql://test")
        sid = uuid4()
        with patch.object(bt, "sp_get_result_by_strategy") as mock_result:
            mock_result.return_value = {
                "payload_json": {"best": {"window": 20, "signal": 1.0}},
            }

            payload = bt.fetch_result_payload(sid, 2)
            assert payload["best"]["window"] == 20
            mock_result.assert_called_once_with(sid, 2)

    def test_returns_none_when_missing(self):
        bt = BtQueueRepo("postgresql://test")
        with patch.object(bt, "sp_get_result_by_strategy", return_value=None):
            assert bt.fetch_result_payload(uuid4(), 1) is None

    def test_returns_none_when_the_row_carries_no_payload(self):
        bt = BtQueueRepo("postgresql://test")
        with patch.object(
            bt, "sp_get_result_by_strategy", return_value={"payload_json": None}
        ):
            assert bt.fetch_result_payload(uuid4(), 1) is None

    def test_parses_a_payload_returned_as_json_text(self):
        bt = BtQueueRepo("postgresql://test")
        with patch.object(
            bt,
            "sp_get_result_by_strategy",
            return_value={"payload_json": '{"best": {"window": 40}}'},
        ):
            assert bt.fetch_result_payload(uuid4(), 5)["best"]["window"] == 40

    def test_survives_a_purged_queue(self):
        """Regression: the live path must not depend on BT.QUEUE.

        Purging the queue orphaned every BT.RESULT row from its QUEUE_ID, and
        the old queue-walking lookup then reported "no optimization result
        found" for strategies whose payloads were entirely intact.
        """
        bt = BtQueueRepo("postgresql://test")
        with patch.object(bt, "sp_get_queue", return_value=[]) as mock_queue, patch.object(
            bt,
            "sp_get_result_by_strategy",
            return_value={"payload_json": {"best": {"window": 40, "signal": 1.75}}},
        ):
            payload = bt.fetch_result_payload(uuid4(), 5)

        assert payload["best"]["signal"] == 1.75
        mock_queue.assert_not_called()

    def test_calls_the_proc_with_the_arity_the_ddl_declares(self):
        bt = BtQueueRepo("postgresql://test")
        sid = uuid4()
        with patch.object(bt, "_call_get_one", return_value=None) as mock_call:
            bt.sp_get_result_by_strategy(sid, 5)

        sql, params = mock_call.call_args[0]
        assert "bt.sp_get_result_by_strategy" in sql
        # Two INs plus the refcursor and status triplet the OUT list declares.
        assert sql.count("%s") == 2
        assert sql.count("NULL::") == 4
        assert params == (str(sid), 5)
