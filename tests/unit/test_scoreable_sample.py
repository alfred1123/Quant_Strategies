"""A grid the loaded series cannot score fails before the search."""

from unittest.mock import MagicMock
from uuid import uuid4

import pandas as pd
import pytest

from quant.schemas.backtest import FactorConfig, OptimizeRequest, RangeParam
from quant.strategy.backtest_service import BacktestError, require_scoreable_sample
from quant.strategy.performance import Performance


def _req(*windows: int) -> OptimizeRequest:
    factors = [
        FactorConfig(
            indicator="get_sma",
            strategy="momentum",
            window_range=RangeParam(min=5, max=w, step=5),
            signal_range=RangeParam(min=0.5, max=0.5, step=0.5),
        )
        for w in windows
    ]
    return OptimizeRequest(
        symbol="btcusdt.crypto",
        start="2024-01-01",
        end="2024-12-31",
        data_source="bybit",
        tm_interval_id=1,
        trading_period=365,
        factors=factors,
    )


def _frame(n: int) -> dict[str, pd.DataFrame]:
    return {
        "btcusdt.crypto": pd.DataFrame(
            {"price": range(n)},
            index=pd.date_range("2024-01-01", periods=n, freq="D"),
        )
    }


def _cache() -> MagicMock:
    cache = MagicMock()
    cache.interval_name.return_value = "DAILY"
    return cache


class TestRequireScoreableSample:
    def test_exact_floor_is_accepted(self):
        w = 20
        n = w + Performance.MIN_METRIC_OBS
        require_scoreable_sample(_frame(n), _req(w), _cache())

    def test_one_bar_short_names_the_count_window_and_interval(self):
        w = 20
        n = w + Performance.MIN_METRIC_OBS - 1
        with pytest.raises(BacktestError, match=rf"series has {n} DAILY bars") as exc:
            require_scoreable_sample(_frame(n), _req(w), _cache())
        assert f"window {w}" in exc.value.detail
        assert str(Performance.MIN_METRIC_OBS) in exc.value.detail

    def test_longest_factor_window_sets_the_floor(self):
        w = 40
        n = w + Performance.MIN_METRIC_OBS - 1
        with pytest.raises(BacktestError, match=rf"window {w}"):
            require_scoreable_sample(_frame(n), _req(10, w), _cache())


class TestWorkerStoresTheSentence:
    def test_backtest_error_is_the_queue_error_text(self, monkeypatch):
        from quant.queue.worker import BacktestWorker

        detail = "series has 79 DAILY bars; the grid needs at least 80 (window 20 + 60 finite pnl bars)"
        caches = MagicMock()
        caches.refdata.resolve_queue_status_id.return_value = 4
        repo = MagicMock()
        repo.fetch_job.return_value = {
            "config_json": _req(20).model_dump(),
            "strategy_id": str(uuid4()),
            "strategy_vid": 1,
            "priority": 1,
            "user_id": str(uuid4()),
        }
        monkeypatch.setattr("quant.queue.worker.DataCaches", lambda *a, **k: caches)
        monkeypatch.setattr("quant.queue.worker.get_redis_url", lambda: "redis://localhost")
        monkeypatch.setattr("quant.queue.worker.WorkerRepo", lambda url: repo)
        monkeypatch.setattr("quant.queue.worker.PriceBarServiceFactory", lambda *a, **k: MagicMock())
        monkeypatch.setattr(
            "quant.queue.worker.run_optimize",
            lambda *a, **k: (_ for _ in ()).throw(BacktestError(detail)),
        )

        code = BacktestWorker("postgresql://stub").run(uuid4())

        assert code == 0
        assert repo.sp_ins_queue.call_args.kwargs["error_text"] == detail
        assert repo.sp_ins_queue.call_args.kwargs["status_id"] == 4
