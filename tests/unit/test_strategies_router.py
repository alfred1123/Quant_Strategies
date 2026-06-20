"""Tests for ``GET /api/v1/strategies`` — Phase 1.6."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _strategy_row(**overrides):
    base = {
        "strategy_id": uuid.uuid4(),
        "strategy_vid": 1,
        "strategy_nm": "btcusdt.crypto · momentum",
        "is_best_ind": "Y",
        "created_at": datetime(2026, 6, 20, tzinfo=timezone.utc),
        "sharpe_ratio": 1.25,
        "calmar_ratio": 0.8,
        "max_drawdown": -0.12,
        "total_return": 0.45,
        "annualized_return": 0.22,
    }
    base.update(overrides)
    return base


@pytest.fixture
def client_and_svc():
    with patch("quant.shared.db.psycopg"):
        from quant.api.auth.dependencies import require_user
        from quant.api.auth.models import CurrentUser
        from quant.api.main import app
        from quant.api.routers.strategies import get_strategies_service

        app.state.db_conninfo = "postgresql://stub"
        app.state.data_caches = MagicMock()

        svc = MagicMock()
        app.dependency_overrides[get_strategies_service] = lambda: svc
        user = CurrentUser(app_user_id=uuid.uuid4(), username="t", session_gen=1)
        app.dependency_overrides[require_user] = lambda: user

        try:
            yield TestClient(app), svc, user
        finally:
            app.dependency_overrides.clear()


class TestListStrategies:
    def test_lists_caller_owned_strategies(self, client_and_svc):
        client, svc, user = client_and_svc
        row = _strategy_row()
        svc.list_strategies.return_value = [row]

        resp = client.get("/api/v1/strategies")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["strategy_nm"] == row["strategy_nm"]
        assert data[0]["sharpe_ratio"] == row["sharpe_ratio"]
        svc.list_strategies.assert_called_once_with(
            user_id=str(user.app_user_id),
            limit=200,
            versions="best",
        )

    def test_limit_param(self, client_and_svc):
        client, svc, user = client_and_svc
        svc.list_strategies.return_value = []

        resp = client.get("/api/v1/strategies", params={"limit": 50})

        assert resp.status_code == 200
        svc.list_strategies.assert_called_once_with(
            user_id=str(user.app_user_id),
            limit=50,
            versions="best",
        )

    def test_versions_best(self, client_and_svc):
        client, svc, user = client_and_svc
        svc.list_strategies.return_value = []

        resp = client.get("/api/v1/strategies", params={"versions": "best"})

        assert resp.status_code == 200
        svc.list_strategies.assert_called_once_with(
            user_id=str(user.app_user_id),
            limit=200,
            versions="best",
        )

    def test_versions_all(self, client_and_svc):
        client, svc, user = client_and_svc
        svc.list_strategies.return_value = []

        resp = client.get("/api/v1/strategies", params={"versions": "all"})

        assert resp.status_code == 200
        svc.list_strategies.assert_called_once_with(
            user_id=str(user.app_user_id),
            limit=200,
            versions="all",
        )
