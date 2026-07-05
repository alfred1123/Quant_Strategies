"""Tests for ``/api/v1/trade/deployments/*`` — Phase 1.2.

Auth is bypassed via ``app.dependency_overrides[require_user]`` and
``TradeService`` is replaced with a mock to avoid touching DB.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from quant.schemas.deployments import DeploymentRow
from quant.schemas.dry_run import DryRunReport
from quant.trade.errors import TradeValidationError
from quant.trade.errors import DeploymentNotFound


def _deployment_row(**overrides) -> DeploymentRow:
    base = {
        "deployment_id": uuid.uuid4(),
        "deployment_vid": 1,
        "app_user_id": uuid.uuid4(),
        "strategy_id": uuid.uuid4(),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 10,
        "internal_cusip": "btc-usd.crypto",
        "qty": Decimal("0.01"),
        "is_paper_ind": "Y",
        "is_enabled_ind": "Y",
        "deployment_status": "CREATED",
        "user_id": "alice",
        "created_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return DeploymentRow(**base)


def _create_body(**overrides):
    base = {
        "strategy_id": str(uuid.uuid4()),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 10,
        "internal_cusip": "btc-usd.crypto",
        "qty": "0.01",
    }
    base.update(overrides)
    return base


@pytest.fixture
def client_and_svc():
    """TestClient + a MagicMock TradeService injected via dependency_overrides."""
    with patch("quant.shared.db.psycopg"):
        from quant.api.auth.dependencies import require_user
        from quant.api.auth.models import CurrentUser
        from quant.api.main import app
        from quant.api.routers.deployments import get_trade_service

        app.state.db_conninfo = "postgresql://stub"
        app.state.data_caches = MagicMock()
        app.state.credential_service = MagicMock()
        app.state.adapter_registry = MagicMock()

        svc = MagicMock()
        app.dependency_overrides[get_trade_service] = lambda: svc
        user = CurrentUser(app_user_id=uuid.uuid4(), username="alice", session_gen=1)
        app.dependency_overrides[require_user] = lambda: user

        try:
            yield TestClient(app), svc, user
        finally:
            app.dependency_overrides.clear()


class TestCreateDeployment:
    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        row = _deployment_row(app_user_id=user.app_user_id)
        svc.create_deployment.return_value = row

        resp = client.post("/api/v1/trade/deployments", json=_create_body())

        assert resp.status_code == 201
        data = resp.json()
        assert data["deployment_id"] == str(row.deployment_id)
        assert data["is_paper_ind"] == "Y"
        svc.create_deployment.assert_called_once()
        app_user_id, user_id, req = svc.create_deployment.call_args.args
        assert app_user_id == user.app_user_id
        assert user_id == str(user.app_user_id)
        assert req.paper is True

    def test_validation_error_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.create_deployment.side_effect = TradeValidationError(
            "API credential not found", status_code=404
        )

        resp = client.post("/api/v1/trade/deployments", json=_create_body())
        assert resp.status_code == 404
        assert "API credential" in resp.json()["detail"]

    def test_sp_failure_returns_502_with_detail(self, client_and_svc):
        client, svc, _ = client_and_svc
        from quant.shared.db import ProcedureError

        svc.create_deployment.side_effect = ProcedureError(
            proc="trade.sp_ins_deployment",
            sqlstate="23505",
            message="duplicate deployment",
        )

        resp = client.post("/api/v1/trade/deployments", json=_create_body())
        assert resp.status_code == 409
        assert resp.json()["detail"]["proc"] == "trade.sp_ins_deployment"

    def test_live_without_confirm_returns_400(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.create_deployment.side_effect = TradeValidationError(
            "Live trading requires explicit confirmation — set confirm_live=true",
            status_code=400,
        )

        resp = client.post(
            "/api/v1/trade/deployments",
            json=_create_body(paper=False),
        )
        assert resp.status_code == 400
        assert "confirm_live" in resp.json()["detail"]

    def test_missing_strategy_id_returns_422(self, client_and_svc):
        client, _, _ = client_and_svc
        body = _create_body()
        del body["strategy_id"]
        resp = client.post("/api/v1/trade/deployments", json=body)
        assert resp.status_code == 422


class TestListDeployments:
    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        rows = [_deployment_row(app_user_id=user.app_user_id)]
        svc.list_deployments.return_value = rows

        resp = client.get("/api/v1/trade/deployments")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["deployment_id"] == str(rows[0].deployment_id)
        svc.list_deployments.assert_called_once_with(user.app_user_id)

    def test_sp_failure_returns_502_with_detail(self, client_and_svc):
        client, svc, _ = client_and_svc
        from quant.shared.db import ProcedureError

        svc.list_deployments.side_effect = ProcedureError(
            proc="trade.sp_get_deployment",
            sqlstate="57000",
            message="db down",
        )

        resp = client.get("/api/v1/trade/deployments")
        assert resp.status_code == 502
        assert resp.json()["detail"]["proc"] == "trade.sp_get_deployment"


class TestGetDeployment:
    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        dep_id = uuid.uuid4()
        row = _deployment_row(deployment_id=dep_id, app_user_id=user.app_user_id)
        svc.get_deployment.return_value = row

        resp = client.get(f"/api/v1/trade/deployments/{dep_id}")

        assert resp.status_code == 200
        assert resp.json()["deployment_id"] == str(dep_id)
        svc.get_deployment.assert_called_once_with(user.app_user_id, dep_id)

    def test_not_found_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        svc.get_deployment.side_effect = DeploymentNotFound(str(dep_id))

        resp = client.get(f"/api/v1/trade/deployments/{dep_id}")
        assert resp.status_code == 404

    def test_sp_failure_returns_502_with_detail(self, client_and_svc):
        client, svc, _ = client_and_svc
        from quant.shared.db import ProcedureError

        svc.get_deployment.side_effect = ProcedureError(
            proc="trade.sp_get_deployment",
            sqlstate="57000",
            message="db down",
        )

        resp = client.get(f"/api/v1/trade/deployments/{uuid.uuid4()}")
        assert resp.status_code == 502
        assert resp.json()["detail"]["proc"] == "trade.sp_get_deployment"


class TestDryRunDeployment:
    def _dry_run_body(self, **overrides):
        base = {
            "strategy_id": str(uuid.uuid4()),
            "strategy_vid": 1,
            "api_credential_id": 1,
            "app_id": 34,
            "internal_cusip": "btc-usd.crypto",
            "qty": "0.01",
            "paper": True,
        }
        base.update(overrides)
        return base

    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        sid = uuid.uuid4()
        report = DryRunReport(
            strategy_id=sid,
            strategy_vid=1,
            strategy_nm="btc strat",
            internal_cusip="btc-usd.crypto",
            vendor_symbol="BTCUSDT",
            app_id=34,
            paper=True,
            qty=Decimal("0.01"),
            signal=1.0,
            intended_side="BUY",
            position_qty=0.0,
            data_as_of="2024-06-01",
        )
        svc.dry_run.return_value = report

        resp = client.post(
            "/api/v1/trade/deployments/dry-run",
            json=self._dry_run_body(strategy_id=str(sid)),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["vendor_symbol"] == "BTCUSDT"
        assert data["intended_side"] == "BUY"
        svc.dry_run.assert_called_once()
        assert svc.dry_run.call_args.args[0] == user.app_user_id

    def test_validation_error_returns_400(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.dry_run.side_effect = TradeValidationError(
            "no INST.PRODUCT_XREF for 'btc-usd.crypto' app_id=34"
        )

        resp = client.post(
            "/api/v1/trade/deployments/dry-run",
            json=self._dry_run_body(),
        )
        assert resp.status_code == 400
        assert "PRODUCT_XREF" in resp.json()["detail"]

    def test_missing_qty_returns_422(self, client_and_svc):
        client, _, _ = client_and_svc
        body = self._dry_run_body()
        del body["qty"]
        resp = client.post("/api/v1/trade/deployments/dry-run", json=body)
        assert resp.status_code == 422
