"""Unit tests for :mod:`quant.trade.service` — mocked TradeRepo, no DB."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.schemas.deployments import CreateDeploymentRequest, UpdateDeploymentRequest
from quant.trade.errors import DeploymentNotFound, TradeValidationError
from quant.trade.live_apply import LiveApplyOrchestrator
from quant.trade.service import TradeService


def _sp_row(**overrides):
    base = {
        "deployment_id": uuid4(),
        "deployment_vid": 1,
        "app_user_id": uuid4(),
        "strategy_id": uuid4(),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 10,
        "internal_cusip": "btcusdt.crypto",
        "qty": Decimal("0.01"),
        "is_paper_ind": "Y",
        "is_enabled_ind": "Y",
        "deployment_status": "CREATED",
        "transact_from_ts": datetime(2026, 5, 20, tzinfo=timezone.utc),
        "user_id": "alice",
    }
    base.update(overrides)
    return base


@pytest.fixture
def svc():
    return TradeService(
        repo=MagicMock(),
        bt=MagicMock(),
        credential_service=MagicMock(),
        credential_repo=MagicMock(),
        adapter_registry=MagicMock(),
        data_caches=MagicMock(),
    )


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
            internal_cusip="btcusdt.crypto",
            qty=Decimal("0.01"),
            paper=False,
            confirm_live=True,
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
        assert kwargs["confirm_live"] is True
        assert kwargs["strategy_id"] == strategy_id

    def test_schedule_interval_passed_through(self, svc):
        app_user_id = uuid4()
        svc._repo.sp_ins_deployment.return_value = _sp_row(
            app_user_id=app_user_id, schedule_tm_interval_id=2
        )

        req = CreateDeploymentRequest(
            strategy_id=uuid4(),
            strategy_vid=1,
            api_credential_id=1,
            app_id=10,
            internal_cusip="btcusdt.crypto",
            qty=Decimal("0.01"),
            schedule_tm_interval_id=2,
        )
        result = svc.create_deployment(app_user_id, "alice", req)

        assert result.schedule_tm_interval_id == 2
        kwargs = svc._repo.sp_ins_deployment.call_args.kwargs
        assert kwargs["schedule_tm_interval_id"] == 2

    def test_schedule_defaults_to_manual_only(self, svc):
        app_user_id = uuid4()
        svc._repo.sp_ins_deployment.return_value = _sp_row(app_user_id=app_user_id)

        req = CreateDeploymentRequest(
            strategy_id=uuid4(),
            strategy_vid=1,
            api_credential_id=1,
            app_id=10,
            internal_cusip="btcusdt.crypto",
            qty=Decimal("0.01"),
        )
        svc.create_deployment(app_user_id, "alice", req)

        kwargs = svc._repo.sp_ins_deployment.call_args.kwargs
        assert kwargs["schedule_tm_interval_id"] is None

    def test_generates_deployment_id_when_omitted(self, svc):
        app_user_id = uuid4()
        svc._repo.sp_ins_deployment.return_value = _sp_row(app_user_id=app_user_id)

        req = CreateDeploymentRequest(
            strategy_id=uuid4(),
            strategy_vid=1,
            api_credential_id=1,
            app_id=10,
            internal_cusip="btcusdt.crypto",
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


class TestUpdateDeployment:
    def test_disable_deployment(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(deployment_id=dep_id, app_user_id=app_user_id)
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row(
            deployment_id=dep_id, is_enabled_ind="N", deployment_vid=2
        )

        req = UpdateDeploymentRequest(enabled=False)
        result = svc.update_deployment(app_user_id, dep_id, req)

        assert result.is_enabled_ind == "N"
        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["is_enabled_ind"] == "N"
        assert kwargs["strategy_id"] == current["strategy_id"]

    def test_change_status(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(deployment_id=dep_id, app_user_id=app_user_id)
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row(
            deployment_id=dep_id, deployment_status="PAUSED"
        )

        req = UpdateDeploymentRequest(deployment_status="PAUSED")
        result = svc.update_deployment(app_user_id, dep_id, req)

        assert result.deployment_status == "PAUSED"
        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["deployment_status"] == "PAUSED"
        assert kwargs["is_enabled_ind"] == current["is_enabled_ind"]

    def test_schedule_preserved_when_not_in_body(self, svc):
        """Re-versioning on a kill-switch toggle must not silently unschedule."""
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(
            deployment_id=dep_id, app_user_id=app_user_id, schedule_tm_interval_id=2
        )
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row(schedule_tm_interval_id=2)

        svc.update_deployment(app_user_id, dep_id, UpdateDeploymentRequest(enabled=False))

        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["schedule_tm_interval_id"] == 2

    def test_schedule_changed(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(
            deployment_id=dep_id, app_user_id=app_user_id, schedule_tm_interval_id=1
        )
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row(schedule_tm_interval_id=2)

        svc.update_deployment(
            app_user_id, dep_id, UpdateDeploymentRequest(schedule_tm_interval_id=2)
        )

        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["schedule_tm_interval_id"] == 2

    def test_explicit_null_clears_schedule(self, svc):
        """An explicit null is how a deployment goes back to manual-only."""
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(
            deployment_id=dep_id, app_user_id=app_user_id, schedule_tm_interval_id=1
        )
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row()

        svc.update_deployment(
            app_user_id,
            dep_id,
            UpdateDeploymentRequest.model_validate({"schedule_tm_interval_id": None}),
        )

        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["schedule_tm_interval_id"] is None

    def test_enable_true_maps_to_Y(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(deployment_id=dep_id, app_user_id=app_user_id)
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row(is_enabled_ind="Y")

        svc.update_deployment(app_user_id, dep_id, UpdateDeploymentRequest(enabled=True))

        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["is_enabled_ind"] == "Y"


class TestStopDeployment:
    def test_stop_writes_stopped_and_disabled(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(deployment_id=dep_id, app_user_id=app_user_id)
        svc._repo.sp_get_deployment.return_value = [current]
        svc._repo.write_deployment.return_value = _sp_row(
            deployment_id=dep_id, deployment_status="STOPPED",
            is_enabled_ind="N", deployment_vid=2,
        )

        result = svc.stop_deployment(app_user_id, dep_id)

        assert result.deployment_status == "STOPPED"
        assert result.is_enabled_ind == "N"
        kwargs = svc._repo.write_deployment.call_args.kwargs
        assert kwargs["deployment_status"] == "STOPPED"
        assert kwargs["is_enabled_ind"] == "N"

    def test_stop_idempotent(self, svc):
        app_user_id = uuid4()
        dep_id = uuid4()
        current = _sp_row(
            deployment_id=dep_id, app_user_id=app_user_id,
            deployment_status="STOPPED", is_enabled_ind="N",
        )
        svc._repo.sp_get_deployment.return_value = [current]

        result = svc.stop_deployment(app_user_id, dep_id)

        assert result.deployment_status == "STOPPED"
        svc._repo.write_deployment.assert_not_called()

    def test_stop_not_found(self, svc):
        svc._repo.sp_get_deployment.return_value = []
        with pytest.raises(DeploymentNotFound):
            svc.stop_deployment(uuid4(), uuid4())


class TestApplyDeployment:
    @patch.object(LiveApplyOrchestrator, "run")
    def test_happy_path(self, mock_apply, svc):
        from quant.schemas.apply import ApplyReport
        from quant.trade.models.order import IntendedAction

        app_user_id = uuid4()
        dep_id = uuid4()
        dep_row = _sp_row(deployment_id=dep_id, app_user_id=app_user_id)
        svc._repo.sp_get_deployment.return_value = [dep_row]

        expected = ApplyReport(
            deployment_id=dep_id,
            deployment_vid=1,
            action=IntendedAction.BUY,
            vendor_symbol="BTCUSDT",
            signal=1.0,
            position_qty=0.0,
            order_success=True,
            vendor_order_id="order-1",
            message="filled",
        )
        mock_apply.return_value = expected

        result = svc.apply_deployment(app_user_id, dep_id)

        assert result.action == IntendedAction.BUY
        assert result.order_success is True
        svc._repo.sp_get_deployment.assert_called_once_with(
            app_user_id=app_user_id, deployment_id=dep_id
        )
        mock_apply.assert_called_once()

    def test_disabled_deployment_raises(self, svc):
        svc._repo.sp_get_deployment.return_value = [_sp_row(is_enabled_ind="N")]

        with pytest.raises(TradeValidationError, match="kill switch"):
            svc.apply_deployment(uuid4(), uuid4())

    def test_not_found_raises(self, svc):
        svc._repo.sp_get_deployment.return_value = []

        with pytest.raises(DeploymentNotFound):
            svc.apply_deployment(uuid4(), uuid4())


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
