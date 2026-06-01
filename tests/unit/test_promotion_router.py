"""Tests for ``/api/v1/backtest/promotions`` — promotion log router.

Auth is bypassed via ``app.dependency_overrides[require_user]`` and the
``PromotionService`` is replaced with a MagicMock to avoid touching DB.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _prow(*, outcome="PROMOTED", compared_vid=None, gates=None, nm="Strat A"):
    return {
        "promotion_id": uuid.uuid4(),
        "queue_id": uuid.uuid4(),
        "strategy_id": uuid.uuid4(),
        "strategy_vid": 2,
        "strategy_nm": nm,
        "is_best_ind": "Y",
        "outcome": outcome,
        "compared_vid": compared_vid,
        "gate_results": gates,
        "sharpe_ratio": 1.5,
        "calmar_ratio": 0.8,
        "max_drawdown": -0.1,
        "total_return": 0.25,
        "annualized_return": 0.18,
        "user_id": "u1",
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }


@pytest.fixture
def client_and_svc():
    with patch("quant.shared.db.psycopg"):
        from quant.api.auth.dependencies import require_user
        from quant.api.auth.models import CurrentUser
        from quant.api.main import app
        from quant.api.routers.promotion import get_promotion_service

        app.state.db_conninfo = "postgresql://stub"
        app.state.data_caches = MagicMock()

        svc = MagicMock()
        app.dependency_overrides[get_promotion_service] = lambda: svc
        user = CurrentUser(app_user_id=uuid.uuid4(), username="t", session_gen=1)
        app.dependency_overrides[require_user] = lambda: user

        try:
            yield TestClient(app), svc
        finally:
            app.dependency_overrides.clear()


class TestList:
    def test_returns_rows(self, client_and_svc):
        client, svc = client_and_svc
        svc.list_promotions.return_value = [
            _prow(),
            _prow(outcome="REJECTED", gates=[
                {"name": "Sharpe", "passed": False, "value": -1.0, "threshold": 0.0},
            ]),
        ]

        resp = client.get("/api/v1/backtest/promotions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["outcome"] == "PROMOTED"
        assert data[1]["gate_results"][0]["passed"] is False
        svc.list_promotions.assert_called_once_with(None, limit=200)

    def test_empty(self, client_and_svc):
        client, svc = client_and_svc
        svc.list_promotions.return_value = []

        resp = client.get("/api/v1/backtest/promotions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_strategy_filter_and_limit_passed_through(self, client_and_svc):
        client, svc = client_and_svc
        svc.list_promotions.return_value = []
        sid = uuid.uuid4()

        resp = client.get(
            f"/api/v1/backtest/promotions?strategy_id={sid}&limit=50"
        )
        assert resp.status_code == 200
        svc.list_promotions.assert_called_once_with(sid, limit=50)

    def test_limit_out_of_range_returns_422(self, client_and_svc):
        client, _ = client_and_svc
        resp = client.get("/api/v1/backtest/promotions?limit=5000")
        assert resp.status_code == 422


class TestAuthGating:
    def test_requires_login(self):
        with patch("quant.shared.db.psycopg"):
            from quant.api.main import app
            app.state.db_conninfo = "postgresql://stub"
            app.state.data_caches = MagicMock()
            from quant.api.auth.service import AuthService
            with patch.object(AuthService, "__init__", return_value=None):
                app.state.auth_service = AuthService.__new__(AuthService)
            client = TestClient(app)
            resp = client.get("/api/v1/backtest/promotions")
            assert resp.status_code == 401
