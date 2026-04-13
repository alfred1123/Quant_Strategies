"""Tests for the FastAPI backtest endpoints.

Mocks the src/ pipeline modules so no real data fetching happens.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client with REFDATA cache stubbed."""
    with patch("api.services.refdata_cache.psycopg"):
        from api.main import app
        app.state.refdata_cache = MagicMock()
        app.state.refdata_cache.get.side_effect = lambda table: {
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
        yield TestClient(app)


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
    @patch("api.services.backtest.YahooFinance")
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
            "symbol": "BTC-USD",
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
        resp = client.post("/api/v1/backtest/data", json={"symbol": "BTC-USD"})
        assert resp.status_code == 422


# ── /api/v1/backtest/optimize ───────────────────────────────────────

class TestOptimizeEndpoint:
    @patch("api.services.backtest.ParametersOptimization")
    @patch("api.services.backtest._fetch_df")
    def test_optimize_single(self, mock_fetch, mock_opt_cls, client):
        mock_fetch.return_value = pd.DataFrame({
            "datetime": ["2024-01-01"] * 100,
            "price": np.linspace(100, 200, 100),
            "factor": np.linspace(100, 200, 100),
        })
        mock_opt = MagicMock()
        from param_opt import OptimizeResult
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
            "symbol": "BTC-USD",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "mode": "single",
            "trading_period": 365,
            "indicator": "get_bollinger_band",
            "strategy": "momentum",
            "window_range": {"min": 10, "max": 20, "step": 10},
            "signal_range": {"min": 0.01, "max": 0.02, "step": 0.01},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] == 2
        assert body["best"]["sharpe"] == 1.8

    def test_optimize_invalid_strategy(self, client):
        resp = client.post("/api/v1/backtest/optimize", json={
            "symbol": "BTC-USD",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "mode": "single",
            "trading_period": 365,
            "indicator": "get_sma",
            "strategy": "nonexistent_signal",
            "window_range": {"min": 10, "max": 20, "step": 10},
            "signal_range": {"min": 0.01, "max": 0.02, "step": 0.01},
        })
        assert resp.status_code == 400


# ── /api/v1/backtest/performance ────────────────────────────────────

class TestPerformanceEndpoint:
    @patch("api.services.backtest.Performance")
    @patch("api.services.backtest._fetch_df")
    def test_performance_single(self, mock_fetch, mock_perf_cls, client):
        mock_fetch.return_value = pd.DataFrame({
            "datetime": ["2024-01-01"] * 100,
            "price": np.linspace(100, 200, 100),
            "factor": np.linspace(100, 200, 100),
        })
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
            "datetime": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "cumu": [0.01, 0.02, 0.03],
            "buy_hold_cumu": [0.01, 0.015, 0.02],
            "dd": [0.0, 0.0, 0.0],
            "buy_hold_dd": [0.0, 0.0, 0.0],
        })
        mock_perf_cls.return_value = mock_perf

        resp = client.post("/api/v1/backtest/performance", json={
            "symbol": "BTC-USD",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "mode": "single",
            "trading_period": 365,
            "indicator": "get_bollinger_band",
            "strategy": "momentum",
            "window": 20,
            "signal": 1.0,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_metrics"]["Sharpe Ratio"] == pytest.approx(1.2)
        assert len(body["equity_curve"]) == 3


# ── /api/v1/backtest/walk-forward ───────────────────────────────────

class TestWalkForwardEndpoint:
    @patch("api.services.backtest.WalkForward")
    @patch("api.services.backtest._fetch_df")
    def test_walk_forward_single(self, mock_fetch, mock_wf_cls, client):
        mock_fetch.return_value = pd.DataFrame({
            "datetime": [f"2024-01-{i+1:02d}" for i in range(100)],
            "price": np.linspace(100, 200, 100),
            "factor": np.linspace(100, 200, 100),
        })

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
            "datetime": [f"2024-01-{i+1:02d}" for i in range(100)],
            "cumu": np.linspace(0, 0.5, 100),
            "buy_hold_cumu": np.linspace(0, 0.4, 100),
            "dd": np.zeros(100),
            "buy_hold_dd": np.zeros(100),
        })
        mock_wf.run.return_value = result
        mock_wf_cls.return_value = mock_wf

        resp = client.post("/api/v1/backtest/walk-forward", json={
            "symbol": "BTC-USD",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "mode": "single",
            "trading_period": 365,
            "split_ratio": 0.5,
            "indicator": "get_bollinger_band",
            "strategy": "momentum",
            "window_range": {"min": 10, "max": 30, "step": 10},
            "signal_range": {"min": 0.5, "max": 1.5, "step": 0.5},
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
        client.app.state.refdata_cache.get.side_effect = ValueError("Unknown REFDATA table: foo")
        resp = client.get("/api/v1/refdata/foo")
        assert resp.status_code == 404
