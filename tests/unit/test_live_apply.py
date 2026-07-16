"""Unit tests for :mod:`quant.trade.live_apply`."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.schemas.deployments import DeploymentRow
from quant.trade.errors import AdapterNotFoundError, TradeValidationError
from quant.trade.live_apply import run_live_apply
from quant.trade.models.order import IntendedAction, OrderResult, OrderSide


def _deployment(**overrides) -> DeploymentRow:
    base = {
        "deployment_id": uuid4(),
        "deployment_vid": 1,
        "app_user_id": uuid4(),
        "strategy_id": uuid4(),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 34,
        "internal_cusip": "btcusdt.crypto",
        "qty": Decimal("0.01"),
        "is_paper_ind": "Y",
        "is_enabled_ind": "Y",
        "deployment_status": "ACTIVE",
        "user_id": "alice",
        "created_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return DeploymentRow(**base)


@pytest.fixture
def deps():
    """Shared mock dependencies for run_live_apply."""
    bt = MagicMock()
    bt.sp_get_strategy.return_value = [
        {"config_json": {}, "strategy_nm": "test_strat", "user_id": "alice"}
    ]
    bt.fetch_result_payload.return_value = {"best": {"window": 20, "signal": 0.5}}
    return {
        "repo": MagicMock(),
        "bt": bt,
        "credential_service": MagicMock(),
        "credential_repo": MagicMock(),
        "adapter_registry": MagicMock(),
        "data_caches": MagicMock(),
        "user_id": "alice",
    }


class TestRunLiveApply:
    def test_no_adapter_raises(self, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = False

        with pytest.raises(AdapterNotFoundError):
            run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

    def test_no_credentials_raises(self, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = None

        with pytest.raises(TradeValidationError, match="credential"):
            run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

    def test_no_strategy_raises(self, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")
        deps["bt"].sp_get_strategy.return_value = []

        with pytest.raises(TradeValidationError, match="strategy"):
            run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_hold_returns_no_order(self, mock_signal, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")

        adapter = MagicMock()
        adapter.__enter__ = MagicMock(return_value=adapter)
        adapter.__exit__ = MagicMock(return_value=False)
        adapter.validate_for_dry_run.return_value = "BTCUSDT"
        adapter.get_position_qty.return_value = 0.01
        adapter.intended_side.return_value = IntendedAction.HOLD
        deps["adapter_registry"].create.return_value = adapter

        report = run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

        assert report.action == IntendedAction.HOLD
        assert report.order_success is None
        assert "HOLD" in report.message
        adapter.execute_action.assert_not_called()

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_buy_success(self, mock_signal, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")

        adapter = MagicMock()
        adapter.__enter__ = MagicMock(return_value=adapter)
        adapter.__exit__ = MagicMock(return_value=False)
        adapter.validate_for_dry_run.return_value = "BTCUSDT"
        adapter.get_position_qty.return_value = 0.0
        adapter.intended_side.return_value = IntendedAction.BUY
        adapter.execute_action.return_value = OrderResult(
            success=True, vendor_order_id="order-1", message="order filled",
            raw_status="closed", side=OrderSide.BUY, requested_qty=0.01,
            filled_qty=0.01, avg_price=64000.0, fee=0.256,
        )
        deps["adapter_registry"].create.return_value = adapter

        report = run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

        assert report.action == IntendedAction.BUY
        assert report.order_success is True
        assert report.vendor_order_id == "order-1"
        assert report.filled_qty == 0.01
        assert report.avg_price == 64000.0
        # single position fetch — the decided action and its position reading
        # are passed straight to execute_action, never re-derived
        adapter.get_position_qty.assert_called_once_with("BTCUSDT")
        adapter.execute_action.assert_called_once_with(
            "BTCUSDT", IntendedAction.BUY, 0.01, 0.0
        )
        deps["repo"].sp_ins_execution_event.assert_called_once()
        ee_kwargs = deps["repo"].sp_ins_execution_event.call_args.kwargs
        assert ee_kwargs["buy_sell_cd"] == "BUY"
        assert ee_kwargs["is_success_ind"] == "Y"

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(-1.0, "2026-07-01"))
    def test_open_short_success(self, mock_signal, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")

        adapter = MagicMock()
        adapter.__enter__ = MagicMock(return_value=adapter)
        adapter.__exit__ = MagicMock(return_value=False)
        adapter.validate_for_dry_run.return_value = "BTCUSDT"
        adapter.get_position_qty.return_value = 0.0
        adapter.intended_side.return_value = IntendedAction.OPEN_SHORT
        adapter.execute_action.return_value = OrderResult(
            success=True, vendor_order_id="order-2", message="order filled",
            side=OrderSide.SELL, requested_qty=0.01,
            filled_qty=0.01, avg_price=63000.0, fee=0.252,
        )
        deps["adapter_registry"].create.return_value = adapter

        report = run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

        assert report.action == IntendedAction.OPEN_SHORT
        assert report.order_success is True
        ee_kwargs = deps["repo"].sp_ins_execution_event.call_args.kwargs
        assert ee_kwargs["buy_sell_cd"] == "SELL"

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_order_failure_still_writes_audit(self, mock_signal, deps):
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")

        adapter = MagicMock()
        adapter.__enter__ = MagicMock(return_value=adapter)
        adapter.__exit__ = MagicMock(return_value=False)
        adapter.validate_for_dry_run.return_value = "BTCUSDT"
        adapter.get_position_qty.return_value = 0.0
        adapter.intended_side.return_value = IntendedAction.BUY
        adapter.execute_action.return_value = OrderResult(
            success=False, vendor_order_id="order-3",
            message="insufficient funds",
            side=OrderSide.BUY, requested_qty=0.01,
        )
        deps["adapter_registry"].create.return_value = adapter

        report = run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

        assert report.order_success is False
        assert "insufficient funds" in report.message
        ee_kwargs = deps["repo"].sp_ins_execution_event.call_args.kwargs
        assert ee_kwargs["is_success_ind"] == "N"

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_execute_action_none_returns_no_order(self, mock_signal, deps):
        """adapter.execute_action returns None when qty resolves to 0."""
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")

        adapter = MagicMock()
        adapter.__enter__ = MagicMock(return_value=adapter)
        adapter.__exit__ = MagicMock(return_value=False)
        adapter.validate_for_dry_run.return_value = "BTCUSDT"
        adapter.get_position_qty.return_value = 0.0
        adapter.intended_side.return_value = IntendedAction.BUY
        adapter.execute_action.return_value = None
        deps["adapter_registry"].create.return_value = adapter

        report = run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

        assert report.order_success is None
        assert "qty resolved to 0" in report.message
        deps["repo"].sp_ins_execution_event.assert_not_called()

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_audit_failure_does_not_crash(self, mock_signal, deps):
        """If the audit write fails, the order was already placed — log, don't re-raise."""
        dep = _deployment()
        deps["adapter_registry"].has_adapter.return_value = True
        deps["credential_service"].decrypt_credential.return_value = ("k", "s")

        adapter = MagicMock()
        adapter.__enter__ = MagicMock(return_value=adapter)
        adapter.__exit__ = MagicMock(return_value=False)
        adapter.validate_for_dry_run.return_value = "BTCUSDT"
        adapter.get_position_qty.return_value = 0.0
        adapter.intended_side.return_value = IntendedAction.BUY
        adapter.execute_action.return_value = OrderResult(
            success=True, vendor_order_id="order-4", message="filled",
            side=OrderSide.BUY, requested_qty=0.01, filled_qty=0.01,
        )
        deps["adapter_registry"].create.return_value = adapter
        deps["repo"].sp_ins_execution_event.side_effect = RuntimeError("DB down")

        report = run_live_apply(app_user_id=dep.app_user_id, deployment=dep, **deps)

        assert report.order_success is True
