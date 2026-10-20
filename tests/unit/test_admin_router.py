"""Tests for ``/api/v1/admin/*`` — the maintenance repos audit the real caller."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("quant.shared.db.open_pool"):
        from quant.api.auth.dependencies import require_user_or_service
        from quant.api.main import app

        app.state.db_conninfo = "postgresql://stub"
        app.state.data_caches = MagicMock()
        app.dependency_overrides[require_user_or_service] = lambda: "scheduler"
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()


class TestTheRepoIsBuiltForTheCaller:
    """``IN_USER_ID`` on each maintenance procedure comes from the repo, so the
    repo must carry whoever got in — not a fixed ``"system"``."""

    def test_log_proc_summary_audits_the_caller(self, client):
        with patch(
            "quant.api.admin.router.LogProcRepo.summarize", autospec=True, return_value=3
        ) as summarize:
            resp = client.post("/api/v1/admin/log-proc-summary/summarize", json={})
        assert resp.status_code == 200, resp.text
        assert summarize.call_args.args[0].user_id == "scheduler"

    def test_stale_connection_sweep_audits_the_caller(self, client):
        from quant.api.admin.models import StaleConnectionSweep

        with patch(
            "quant.api.admin.router.ConnectionMaintenanceRepo.terminate_stale_connections",
            autospec=True,
            return_value=StaleConnectionSweep(stale=0, terminated=0),
        ) as sweep:
            resp = client.post("/api/v1/admin/db/terminate-stale-connections", json={})
        assert resp.status_code == 200, resp.text
        assert sweep.call_args.args[0].user_id == "scheduler"
