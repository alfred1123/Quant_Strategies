"""Unit tests for :mod:`quant.trade.schedule_align`."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from quant.schemas.deployments import DeploymentRow, DeploymentStatus, UpdateDeploymentRequest
from quant.trade.schedule_align import should_realign_schedule


def _row(**kwargs) -> DeploymentRow:
    base = dict(
        deployment_id=uuid4(),
        deployment_vid=1,
        app_user_id=uuid4(),
        strategy_id=uuid4(),
        strategy_vid=1,
        api_credential_id=1,
        app_id=2,
        internal_cusip="btcusdt.crypto",
        qty=Decimal("1"),
        is_paper_ind="N",
        is_enabled_ind="Y",
        deployment_status=DeploymentStatus.ACTIVE,
        schedule_tm_interval_id=1,
        transact_from_ts=datetime.now(UTC),
        user_id="alice",
    )
    base.update(kwargs)
    return DeploymentRow.model_validate(base)


class TestShouldRealignSchedule:
    def test_schedule_cadence_change(self):
        current = _row(schedule_tm_interval_id=1)
        req = UpdateDeploymentRequest(schedule_tm_interval_id=2)
        assert should_realign_schedule(current, req) is True

    def test_qty_only_patch_does_not_realign(self):
        current = _row()
        req = UpdateDeploymentRequest()
        assert should_realign_schedule(current, req) is False

    def test_unpause_realigns(self):
        current = _row(
            deployment_status=DeploymentStatus.PAUSED,
            is_enabled_ind="N",
        )
        req = UpdateDeploymentRequest(
            deployment_status=DeploymentStatus.ACTIVE,
            enabled=True,
        )
        assert should_realign_schedule(current, req) is True
