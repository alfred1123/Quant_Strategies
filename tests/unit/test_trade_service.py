"""Unit tests for :mod:`quant.trade.service` — mocked TradeRepo, no DB."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from quant.schemas.deployments import CreateDeploymentRequest
from quant.trade.service import DeploymentNotFound, TradeService


def _sp_row(**overrides):
    base = {
        "deployment_id": uuid4(),
        "deployment_vid": 1,
        "app_user_id": uuid4(),
        "strategy_id": uuid4(),
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
    return base


@pytest.fixture
def svc():
    return TradeService(repo=MagicMock())


class TestCreateDeployment:
    def test_happy_path(self, svc):
        app_user_id = uuid4()
        strategy_id = uuid4()
        row = _sp_row(
            app_user_id=app_user_id,
            strategy_id=strategy_id,
            is_paper_ind="N",
        )
        svc._repo.sp_ins_deployment.return_value = row

        req = CreateDeploymentRequest(
            strategy_id=strategy_id,
            strategy_vid=1,
            api_credential_id=1,
            app_id=10,
            internal_cusip="btc-usd.crypto",
            qty=Decimal("0.01"),
            paper=False,
            enabled=True,
        )
        result = svc.create_deployment(app_user_id, "alice", req)

        assert result.strategy_id == strategy_id
        assert result.is_paper_ind == "N"
        assert result.is_enabled_ind == "Y"
        svc._repo.sp_ins_deployment.assert_called_once()
        kwargs = svc._repo.sp_ins_deployment.call_args.kwargs
        assert kwargs["app_user_id"] == app_user_id
        assert kwargs["user_id"] == "alice"
        assert kwargs["is_paper_ind"] == "N"
        assert kwargs["strategy_id"] == strategy_id

    def test_generates_deployment_id_when_omitted(self, svc):
        app_user_id = uuid4()
        svc._repo.sp_ins_deployment.return_value = _sp_row(app_user_id=app_user_id)

        req = CreateDeploymentRequest(
            strategy_id=uuid4(),
            strategy_vid=1,
            api_credential_id=1,
            app_id=10,
            internal_cusip="btc-usd.crypto",
            qty=Decimal("0.01"),
        )
        svc.create_deployment(app_user_id, "alice", req)

        dep_id = svc._repo.sp_ins_deployment.call_args.kwargs["deployment_id"]
        assert dep_id is not None


class TestGetDeployment:
    def test_happy_path(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        svc._repo.sp_get_deployment.return_value = [_sp_row(deployment_id=dep_id)]

        result = svc.get_deployment(app_user_id, dep_id)

        assert result.deployment_id == dep_id
        svc._repo.sp_get_deployment.assert_called_once_with(
            app_user_id=app_user_id,
            deployment_id=dep_id,
        )

    def test_not_found(self, svc):
        svc._repo.sp_get_deployment.return_value = []
        with pytest.raises(DeploymentNotFound):
            svc.get_deployment(uuid4(), uuid4())


class TestListDeployments:
    def test_happy_path(self, svc):
        app_user_id = uuid4()
        svc._repo.sp_get_deployment.return_value = [
            _sp_row(app_user_id=app_user_id),
            _sp_row(app_user_id=app_user_id, deployment_vid=2),
        ]

        rows = svc.list_deployments(app_user_id)

        assert len(rows) == 2
        svc._repo.sp_get_deployment.assert_called_once_with(app_user_id=app_user_id)
