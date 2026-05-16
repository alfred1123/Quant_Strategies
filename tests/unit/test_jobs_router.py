"""Tests for ``/api/v1/jobs/*`` — Phase B v6 router.

Auth is bypassed via ``app.dependency_overrides[require_user]`` and the
``JobsService`` is replaced with an in-memory fake to avoid touching DB
or Redis.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.schemas.jobs import EnqueueResponse


def _row(*, qid=None, status="QUEUED", status_id=1, vid=1, user="u1", priority=100, error=None):
    return {
        "queue_id": qid or uuid.uuid4(),
        "queue_vid": vid,
        "strategy_id": uuid.uuid4(),
        "strategy_vid": 1,
        "strategy_nm": "Strat A",
        "queue_status_id": status_id,
        "queue_status": status,
        "priority": priority,
        "user_id": user,
        "transact_from_ts": datetime(2026, 5, 16, tzinfo=timezone.utc),
        "error_text": error,
    }


@pytest.fixture
def client_and_svc():
    """TestClient + a MagicMock JobsService injected via dependency_overrides."""
    with patch("quant.shared.db.psycopg"):
        from api.auth.dependencies import require_user
        from api.auth.models import CurrentUser
        from api.main import app
        from api.routers.jobs import get_jobs_service

        app.state.db_conninfo = "postgresql://stub"
        app.state.data_caches = MagicMock()
        app.state.redis_client = MagicMock()

        svc = MagicMock()
        app.dependency_overrides[get_jobs_service] = lambda: svc
        user = CurrentUser(app_user_id=uuid.uuid4(), username="t", session_gen=1)
        app.dependency_overrides[require_user] = lambda: user

        try:
            yield TestClient(app), svc, user
        finally:
            app.dependency_overrides.clear()


# ── POST /api/v1/jobs ───────────────────────────────────────────────────


class TestEnqueue:
    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        qid = uuid.uuid4()
        svc.enqueue.return_value = EnqueueResponse(queue_id=qid, queue_pos=3)

        body = {"strategy_nm": "test", "config_json": {"foo": 1}, "priority": "high"}
        resp = client.post("/api/v1/jobs", json=body)

        assert resp.status_code == 202
        data = resp.json()
        assert data == {"queue_id": str(qid), "queue_pos": 3}
        svc.enqueue.assert_called_once()
        called_user_id, called_req = svc.enqueue.call_args.args
        assert called_user_id == str(user.app_user_id)
        assert called_req.priority == "high"
        assert called_req.strategy_nm == "test"
        assert called_req.config_json == {"foo": 1}

    def test_rate_limited_returns_429(self, client_and_svc):
        client, svc, _ = client_and_svc
        from api.services.jobs import RateLimitError
        svc.enqueue.side_effect = RateLimitError(30)

        resp = client.post(
            "/api/v1/jobs",
            json={"strategy_nm": "test", "config_json": {}},
        )
        assert resp.status_code == 429
        assert "rate_limited" in resp.json()["detail"]

    def test_validation_error_returns_422(self, client_and_svc):
        client, _, _ = client_and_svc
        resp = client.post(
            "/api/v1/jobs",
            json={"config_json": {}},  # missing strategy_nm
        )
        assert resp.status_code == 422


# ── GET /api/v1/jobs ────────────────────────────────────────────────────


class TestList:
    def test_returns_user_rows(self, client_and_svc):
        client, svc, user = client_and_svc
        svc.list_for_user.return_value = [_row(), _row(status="RUNNING", status_id=2)]

        resp = client.get("/api/v1/jobs")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        svc.list_for_user.assert_called_once_with(str(user.app_user_id))

    def test_empty(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.list_for_user.return_value = []

        resp = client.get("/api/v1/jobs")
        assert resp.status_code == 200
        assert resp.json() == []


# ── GET /api/v1/jobs/{id} ───────────────────────────────────────────────


class TestGet:
    def test_returns_detail(self, client_and_svc):
        client, svc, _ = client_and_svc
        qid = uuid.uuid4()
        svc.get.return_value = _row(qid=qid)

        resp = client.get(f"/api/v1/jobs/{qid}")
        assert resp.status_code == 200
        assert resp.json()["queue_id"] == str(qid)

    def test_not_found(self, client_and_svc):
        client, svc, _ = client_and_svc
        from api.services.jobs import JobNotFound
        svc.get.side_effect = JobNotFound("missing")

        resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
        assert resp.status_code == 404


# ── POST /api/v1/jobs/{id}/cancel ───────────────────────────────────────


class TestCancel:
    def test_cancel_queued(self, client_and_svc):
        client, svc, _ = client_and_svc
        qid = uuid.uuid4()
        svc.cancel.return_value = _row(qid=qid, status="CANCELLED", status_id=6, vid=2)

        resp = client.post(f"/api/v1/jobs/{qid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["queue_status"] == "CANCELLED"

    def test_cancel_running(self, client_and_svc):
        client, svc, _ = client_and_svc
        qid = uuid.uuid4()
        svc.cancel.return_value = _row(qid=qid, status="CANCEL_REQUESTED", status_id=3, vid=2)

        resp = client.post(f"/api/v1/jobs/{qid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["queue_status"] == "CANCEL_REQUESTED"

    def test_cancel_terminal_returns_409(self, client_and_svc):
        client, svc, _ = client_and_svc
        from api.services.jobs import CancelNotAllowed
        svc.cancel.side_effect = CancelNotAllowed("already done")

        resp = client.post(f"/api/v1/jobs/{uuid.uuid4()}/cancel")
        assert resp.status_code == 409

    def test_cancel_not_found_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        from api.services.jobs import JobNotFound
        svc.cancel.side_effect = JobNotFound("nope")

        resp = client.post(f"/api/v1/jobs/{uuid.uuid4()}/cancel")
        assert resp.status_code == 404


# ── GET /api/v1/jobs/{id}/events (SSE) ──────────────────────────────────


class TestEventsStream:
    def test_emits_status_then_terminates_on_completed(self, client_and_svc):
        client, svc, _ = client_and_svc
        qid = uuid.uuid4()
        svc.snapshot_status.side_effect = [
            {"queue_id": str(qid), "queue_vid": 1, "queue_status": "RUNNING",
             "queue_status_id": 2, "error_text": None},
            {"queue_id": str(qid), "queue_vid": 2, "queue_status": "COMPLETED",
             "queue_status_id": 4, "error_text": None},
        ]
        # Speed up the test — patch the sleep to a no-op.
        with patch("api.routers.jobs.asyncio.sleep") as mock_sleep:
            async def _noop(*_a, **_kw):
                return None
            mock_sleep.side_effect = _noop
            resp = client.get(f"/api/v1/jobs/{qid}/events")

        assert resp.status_code == 200
        body = resp.text
        # Two distinct status events emitted; stream closes after COMPLETED.
        assert body.count("event: status") == 2
        assert '"queue_status": "RUNNING"' in body
        assert '"queue_status": "COMPLETED"' in body

    def test_emits_error_when_job_missing(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.snapshot_status.return_value = None

        resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}/events")
        assert resp.status_code == 200
        assert "event: error" in resp.text
        assert "not_found" in resp.text


# ── auth gating (only checks the route is wired through require_user) ──


class TestAuthGating:
    def test_requires_login(self):
        """Without dependency_overrides the cookie is absent → 401."""
        with patch("quant.shared.db.psycopg"):
            from api.main import app
            app.state.db_conninfo = "postgresql://stub"
            app.state.data_caches = MagicMock()
            # Ensure auth state present so require_user runs.
            from api.auth.service import AuthService
            with patch.object(AuthService, "__init__", return_value=None):
                app.state.auth_service = AuthService.__new__(AuthService)
            client = TestClient(app)
            resp = client.get("/api/v1/jobs")
            assert resp.status_code == 401
