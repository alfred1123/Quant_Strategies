"""Tests for the FastAPI backtest endpoints.

Mocks the src/ pipeline modules so no real data fetching happens.
Auth is bypassed via ``app.dependency_overrides[require_user]`` — every
test runs as a synthetic CurrentUser without needing JWT cookies.
"""

import pytest
import pandas as pd
import numpy as np
from uuid import uuid4
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client with REFDATA, instrument cache, AND auth stubbed.

    Three things must be in place for protected routes to be reachable:
      * ``app.state.data_caches`` (``DataCaches`` bundle — routes use ``Depends``)
      * legacy ``refdata_cache`` / ``instrument_cache`` aliases (same objects)
      * ``app.state.auth_service`` (read by ``get_auth_service`` even when
        ``require_user`` itself is overridden, because other deps may pick
        it up)
      * ``app.dependency_overrides[require_user]`` returning a synthetic
        ``CurrentUser`` so the JWT cookie path is bypassed.
    """
    with patch("quant.shared.db.open_pool"):
        from quant.api.main import app
        from quant.api.auth.dependencies import require_user
        from quant.api.auth.models import CurrentUser

        ref = MagicMock()
        inst = MagicMock()
        inst.get_product_by_cusip.return_value = None
        bt = MagicMock()
        caches = MagicMock()
        caches.refdata = ref
        caches.instrument_cache = inst
        caches.backtest_cache = bt
        app.state.data_caches = caches
        app.state.refdata_cache = ref
        app.state.instrument_cache = inst
        app.state.backtest_cache = bt
        app.state.db_conninfo = "postgresql://stub"
        # Backtests may name an exchange as their data source, in which case
        # bars come from MARKET_DATA.PRICE_BAR rather than a vendor client.
        app.state.price_bars = MagicMock()

        ref.get.side_effect = lambda table: {
            "indicator": [
                {"display_name": "SMA", "method_name": "get_sma", "is_bounded_ind": "N"},
                {"display_name": "Bollinger Band", "method_name": "get_bollinger_band", "is_bounded_ind": "N"},
                {"display_name": "RSI", "method_name": "get_rsi", "is_bounded_ind": "Y"},
            ],
            "signal_type": [
                {"name": "momentum", "display_name": "Momentum", "func_name_band": "momentum_band_signal", "func_name_bounded": "momentum_bounded_signal"},
                {"name": "reversion", "display_name": "Reversion", "func_name_band": "reversion_band_signal", "func_name_bounded": "reversion_bounded_signal"},
            ],
            "app": [
                {"name": "yahoo", "display_name": "Yahoo Finance", "class_name": "YahooFinance"},
            ],
        }.get(table, [])

        ref.get_config.side_effect = lambda table: {
            "promotion_metric": [
                {"name": "sharpe_gate", "display_name": "Sharpe GT 1"},
            ],
        }.get(table, [])

        fake_user = CurrentUser(app_user_id=uuid4(), username="test", session_gen=1)
        app.dependency_overrides[require_user] = lambda: fake_user
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()


# ── /health ─────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── /api/v1/backtest/data ───────────────────────────────────────────

class TestDataEndpoint:
    # /backtest/data endpoint is disabled — tests skipped
    @pytest.mark.skip(reason="/backtest/data endpoint is disabled")
    @patch("quant.strategy.backtest_service.YahooFinance")
    def test_data_returns_rows(self, mock_yf_cls, client):
        mock_yf = MagicMock()
        mock_yf_cls.return_value = mock_yf
        mock_get = MagicMock(return_value=pd.DataFrame({
            "t": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "v": [100.0, 101.0, 102.0],
        }))
        mock_get.cache_clear = MagicMock()
        mock_yf.get_historical_price = mock_get

        resp = client.post("/api/v1/backtest/data", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-01-03",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["rows"] == 3
        assert len(body["data"]) == 3
        assert body["data"][0]["price"] == 100.0

    @pytest.mark.skip(reason="/backtest/data endpoint is disabled")
    def test_data_missing_fields(self, client):
        resp = client.post("/api/v1/backtest/data", json={"symbol": "btc-usd"})
        assert resp.status_code == 422


# ── /api/v1/backtest/optimize ───────────────────────────────────────

class TestOptimizeEndpoint:
    @patch("quant.strategy.backtest_service.ParametersOptimization")
    @patch("quant.strategy.backtest_service.fetch_df")
    def test_optimize_single(self, mock_fetch, mock_opt_cls, client):
        mock_fetch.return_value = pd.DataFrame({
            "price": np.linspace(100, 200, 100),
            "factor": np.linspace(100, 200, 100),
        }, index=pd.date_range("2024-01-01", periods=100, freq="D", name="datetime"))
        mock_opt = MagicMock()
        from quant.strategy.optimizer import OptimizeResult
        _df = pd.DataFrame({"window": [10, 20], "signal": [0.01, 0.02], "sharpe": [1.5, 1.8]})
        mock_opt.run.return_value = OptimizeResult(
            grid_df=_df,
            best={"window": 20, "signal": 0.02, "sharpe": 1.8},
            top10=[{"window": 20, "signal": 0.02, "sharpe": 1.8}, {"window": 10, "signal": 0.01, "sharpe": 1.5}],
            grid=[{"window": 20, "signal": 0.02, "sharpe": 1.8}, {"window": 10, "signal": 0.01, "sharpe": 1.5}],
            n_valid=2,
            study=None,
        )
        mock_opt_cls.return_value = mock_opt

        resp = client.post("/api/v1/backtest/optimize", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "data_source": "yahoo",
            "tm_interval_id": 1,
            "trading_period": 365,
            "factors": [
                {
                    "indicator": "get_bollinger_band",
                    "strategy": "momentum",
                    "data_column": "price",
                    "window_range": {"min": 10, "max": 20, "step": 10},
                    "signal_range": {"min": 0.01, "max": 0.02, "step": 0.01},
                },
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] == 2
        assert body["best"]["sharpe"] == 1.8

    @patch("quant.strategy.backtest_service.fetch_df")
    def test_a_grid_the_series_cannot_score_is_refused(self, mock_fetch, client):
        client.app.state.data_caches.refdata.interval_name.return_value = "DAILY"
        mock_fetch.return_value = pd.DataFrame({
            "price": np.linspace(100, 200, 70),
            "factor": np.linspace(100, 200, 70),
        }, index=pd.date_range("2024-01-01", periods=70, freq="D", name="datetime"))

        resp = client.post("/api/v1/backtest/optimize", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "data_source": "yahoo",
            "tm_interval_id": 1,
            "trading_period": 365,
            "factors": [
                {
                    "indicator": "get_bollinger_band",
                    "strategy": "momentum",
                    "data_column": "price",
                    "window_range": {"min": 10, "max": 20, "step": 10},
                    "signal_range": {"min": 0.01, "max": 0.02, "step": 0.01},
                },
            ],
        })
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "70 DAILY bars" in detail
        assert "window 20" in detail

    def test_optimize_invalid_strategy(self, client):
        resp = client.post("/api/v1/backtest/optimize", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "data_source": "yahoo",
            "tm_interval_id": 1,
            "trading_period": 365,
            "factors": [
                {
                    "indicator": "get_sma",
                    "strategy": "nonexistent_signal",
                    "data_column": "price",
                    "window_range": {"min": 10, "max": 20, "step": 10},
                    "signal_range": {"min": 0.01, "max": 0.02, "step": 0.01},
                },
            ],
        })
        assert resp.status_code == 400

    def test_a_run_without_a_source_is_refused_not_assumed(self, client):
        """No data_source must 422, never quietly become Yahoo.

        A default here fitted runs on provider prints while the venue the
        user had picked sat on a factor, and nothing surfaced it.
        """
        resp = client.post("/api/v1/backtest/optimize", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "trading_period": 365,
            "factors": [
                {
                    "indicator": "get_sma",
                    "strategy": "momentum",
                    "data_column": "price",
                    "window_range": {"min": 10, "max": 20, "step": 10},
                    "signal_range": {"min": 0.01, "max": 0.02, "step": 0.01},
                },
            ],
        })
        assert resp.status_code == 422
        assert any(
            err["loc"][-1] == "data_source" for err in resp.json()["detail"]
        )


# ── /api/v1/backtest/performance ────────────────────────────────────

class TestPerformanceEndpoint:
    @patch("quant.strategy.backtest_service.Performance")
    @patch("quant.strategy.backtest_service.fetch_df")
    def test_performance_single(self, mock_fetch, mock_perf_cls, client):
        mock_fetch.return_value = pd.DataFrame({
            "price": np.linspace(100, 200, 100),
            "factor": np.linspace(100, 200, 100),
        }, index=pd.date_range("2024-01-01", periods=100, freq="D", name="datetime"))
        mock_perf = MagicMock()
        mock_perf.enrich_performance.return_value = mock_perf
        mock_perf.get_strategy_performance.return_value = pd.Series({
            "Total Return": 0.5,
            "Annualized Return": 0.3,
            "Sharpe Ratio": 1.2,
            "Max Drawdown": 0.1,
            "Calmar Ratio": 3.0,
        })
        mock_perf.get_buy_hold_performance.return_value = pd.Series({
            "Total Return": 0.4,
            "Annualized Return": 0.25,
            "Sharpe Ratio": 0.9,
            "Max Drawdown": 0.15,
            "Calmar Ratio": 1.7,
        })
        mock_perf.data = pd.DataFrame({
            "cumu": [0.01, 0.02, 0.03],
            "buy_hold_cumu": [0.01, 0.015, 0.02],
            "dd": [0.0, 0.0, 0.0],
            "buy_hold_dd": [0.0, 0.0, 0.0],
        }, index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
        mock_perf.data.index.name = "datetime"
        mock_perf_cls.return_value = mock_perf

        resp = client.post("/api/v1/backtest/performance", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "data_source": "yahoo",
            "tm_interval_id": 1,
            "trading_period": 365,
            "factors": [
                {
                    "indicator": "get_bollinger_band",
                    "strategy": "momentum",
                    "data_column": "price",
                    "window_range": {"min": 20, "max": 20, "step": 1},
                    "signal_range": {"min": 1.0, "max": 1.0, "step": 1},
                },
            ],
            "windows": [20],
            "signals": [1.0],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_metrics"]["Sharpe Ratio"] == pytest.approx(1.2)
        assert len(body["equity_curve"]) == 3


# ── /api/v1/backtest/walk-forward ───────────────────────────────────

class TestWalkForwardEndpoint:
    @patch("quant.strategy.backtest_service.WalkForward")
    @patch("quant.strategy.backtest_service.fetch_df")
    def test_walk_forward_single(self, mock_fetch, mock_wf_cls, client):
        mock_fetch.return_value = pd.DataFrame({
            "price": np.linspace(100, 200, 100),
            "factor": np.linspace(100, 200, 100),
        }, index=pd.date_range("2024-01-01", periods=100, freq="D", name="datetime"))

        # Mock WalkForward.run()
        mock_wf = MagicMock()
        mock_wf.split_idx = 50
        result = MagicMock()
        result.best_window = 20
        result.best_signal = 1.0
        result.is_metrics = pd.Series({
            "Total Return": 0.3, "Annualized Return": 0.2,
            "Sharpe Ratio": 1.5, "Max Drawdown": 0.05, "Calmar Ratio": 4.0,
        })
        result.oos_metrics = pd.Series({
            "Total Return": 0.15, "Annualized Return": 0.1,
            "Sharpe Ratio": 0.8, "Max Drawdown": 0.1, "Calmar Ratio": 1.0,
        })
        result.overfitting_ratio = 0.47
        result.full_equity_df = pd.DataFrame({
            "cumu": np.linspace(0, 0.5, 100),
            "buy_hold_cumu": np.linspace(0, 0.4, 100),
            "dd": np.zeros(100),
            "buy_hold_dd": np.zeros(100),
        }, index=pd.date_range("2024-01-01", periods=100, freq="D", name="datetime"))
        mock_wf.run.return_value = result
        mock_wf_cls.return_value = mock_wf

        resp = client.post("/api/v1/backtest/walk-forward", json={
            "symbol": "btc-usd",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "data_source": "yahoo",
            "tm_interval_id": 1,
            "trading_period": 365,
            "split_ratio": 0.5,
            "factors": [
                {
                    "indicator": "get_bollinger_band",
                    "strategy": "momentum",
                    "data_column": "price",
                    "window_range": {"min": 10, "max": 30, "step": 10},
                    "signal_range": {"min": 0.5, "max": 1.5, "step": 0.5},
                },
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["best_window"] == 20
        assert body["best_signal"] == pytest.approx(1.0)
        assert body["overfitting_ratio"] == pytest.approx(0.47)
        assert len(body["equity_curve"]) == 100


# ── /api/v1/refdata ─────────────────────────────────────────────────

class TestRefDataEndpoint:
    def test_get_refdata_indicator(self, client):
        resp = client.get("/api/v1/refdata/indicator")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_get_refdata_unknown_table(self, client):
        client.app.state.data_caches.refdata.get.side_effect = ValueError("Unknown REFDATA table: foo")
        resp = client.get("/api/v1/refdata/foo")
        assert resp.status_code == 404

    def test_post_refdata_refresh_ok(self, client):
        with patch("quant.api.routers.refdata.RefDataPublisher") as pub_cls:
            pub_cls.return_value.publish.return_value = 5
            resp = client.post("/api/v1/refdata/refresh")
        assert resp.status_code == 200
        assert resp.json() == {"tables": 5}
        pub_cls.return_value.publish.assert_called_once_with("refdata")

    def test_post_refdata_refresh_failure_503(self, client):
        with patch("quant.api.routers.refdata.RefDataPublisher") as pub_cls:
            pub_cls.return_value.publish.side_effect = RuntimeError("redis down")
            resp = client.post("/api/v1/refdata/refresh")
        assert resp.status_code == 503
        assert "redis down" in resp.json()["detail"]


class TestConfigEndpoint:
    def test_get_config_promotion_metric(self, client):
        resp = client.get("/api/v1/config/promotion_metric")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "sharpe_gate"

    def test_get_config_unknown_table(self, client):
        client.app.state.data_caches.refdata.get_config.side_effect = ValueError(
            "config.foo not in Redis"
        )
        resp = client.get("/api/v1/config/foo")
        assert resp.status_code == 404

    def test_post_config_refresh_ok(self, client):
        with patch("quant.api.routers.config.RefDataPublisher") as pub_cls:
            pub_cls.return_value.publish.return_value = 4
            resp = client.post("/api/v1/config/refresh")
        assert resp.status_code == 200
        assert resp.json() == {"tables": 4}
        pub_cls.return_value.publish.assert_called_once_with("config")

    def test_post_config_refresh_failure_503(self, client):
        with patch("quant.api.routers.config.RefDataPublisher") as pub_cls:
            pub_cls.return_value.publish.side_effect = RuntimeError("redis down")
            resp = client.post("/api/v1/config/refresh")
        assert resp.status_code == 503
        assert "redis down" in resp.json()["detail"]
