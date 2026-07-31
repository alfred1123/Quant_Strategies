"""Unit tests for :mod:`quant.trade.live_apply`."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.schemas.deployments import DeploymentRow
from quant.trade.errors import AdapterNotFoundError, TradeValidationError
from quant.trade.live_apply import LiveApplyOrchestrator
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
        "transact_from_ts": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "user_id": "alice",
    }
    base.update(overrides)
    return DeploymentRow(**base)


@pytest.fixture
def orchestrator():
    """LiveApplyOrchestrator with all dependencies mocked."""
    bt = MagicMock()
    bt.sp_get_strategy.return_value = [
        {"config_json": {}, "strategy_nm": "test_strat", "user_id": "alice"}
    ]
    bt.fetch_result_payload.return_value = {"best": {"window": 20, "signal": 0.5}}
    data_caches = MagicMock()
    data_caches.instrument_cache.get_product_by_cusip.return_value = {
        "product_id": 1,
        "internal_cusip": "btcusdt.crypto",
        "ccy": "USDT",
    }
    return LiveApplyOrchestrator(
        repo=MagicMock(),
        bt=bt,
        credential_service=MagicMock(),
        credential_repo=MagicMock(),
        adapter_registry=MagicMock(),
        data_caches=data_caches,
        notifier=MagicMock(),
    ), bt


def _adapter_mock(**overrides) -> MagicMock:
    adapter = MagicMock()
    adapter.__enter__ = MagicMock(return_value=adapter)
    adapter.__exit__ = MagicMock(return_value=False)
    adapter.validate_for_dry_run.return_value = "BTCUSDT"
    adapter.get_position_qty.return_value = 0.0
    adapter.intended_side.return_value = IntendedAction.BUY
    for key, val in overrides.items():
        setattr(adapter, key, val)
    return adapter


class TestLiveApplyOrchestrator:
    def test_no_adapter_raises(self, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = False

        with pytest.raises(AdapterNotFoundError):
            orch.run(dep.app_user_id, dep, "alice")

    def test_no_credentials_raises(self, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = None

        with pytest.raises(TradeValidationError, match="credential"):
            orch.run(dep.app_user_id, dep, "alice")

    def test_no_strategy_raises(self, orchestrator):
        orch, bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")
        bt.sp_get_strategy.return_value = []

        with pytest.raises(TradeValidationError, match="strategy"):
            orch.run(dep.app_user_id, dep, "alice")

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_hold_returns_no_order(self, mock_signal, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")

        adapter = _adapter_mock(
            get_position_qty=MagicMock(return_value=0.01),
            intended_side=MagicMock(return_value=IntendedAction.HOLD),
        )
        orch._adapter_registry.create.return_value = adapter

        report = orch.run(dep.app_user_id, dep, "alice")

        assert report.action == IntendedAction.HOLD
        assert report.order_success is None
        assert "HOLD" in report.message
        adapter.apply_signal.assert_not_called()
        orch._repo.sp_ins_execution_event.assert_called_once()
        orch._notifier.send.assert_not_called()

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_buy_success(self, mock_signal, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")

        adapter = _adapter_mock(
            apply_signal=MagicMock(
                return_value=OrderResult(
                    success=True,
                    vendor_order_id="order-1",
                    message="order filled",
                    raw_status="closed",
                    side=OrderSide.BUY,
                    requested_qty=0.01,
                    filled_qty=0.01,
                    avg_price=64000.0,
                    fee=0.256,
                )
            ),
        )
        orch._adapter_registry.create.return_value = adapter

        report = orch.run(dep.app_user_id, dep, "alice")

        assert report.action == IntendedAction.BUY
        assert report.order_success is True
        adapter.apply_signal.assert_called_once_with("BTCUSDT", 1.0, 0.01)
        orch._repo.sp_ins_transaction.assert_called_once()
        tx_kwargs = orch._repo.sp_ins_transaction.call_args.kwargs
        assert tx_kwargs["trans_ccy_cd"] == "USDT"
        orch._notifier.send.assert_not_called()

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_settlement_ccy_from_instrument_master(self, mock_signal, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment(internal_cusip="0700.hk")
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")
        orch._data_caches.instrument_cache.get_product_by_cusip.return_value = {
            "product_id": 2,
            "internal_cusip": "0700.hk",
            "ccy": "HKD",
        }

        adapter = _adapter_mock(
            apply_signal=MagicMock(
                return_value=OrderResult(
                    success=True,
                    vendor_order_id="order-2",
                    message="order filled",
                    side=OrderSide.BUY,
                    requested_qty=100.0,
                    filled_qty=100.0,
                    avg_price=350.0,
                )
            ),
        )
        orch._adapter_registry.create.return_value = adapter

        orch.run(dep.app_user_id, dep, "alice")

        tx_kwargs = orch._repo.sp_ins_transaction.call_args.kwargs
        assert tx_kwargs["trans_ccy_cd"] == "HKD"

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_order_failure_alerts_and_writes_audit(self, mock_signal, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")

        adapter = _adapter_mock(
            apply_signal=MagicMock(
                return_value=OrderResult(
                    success=False,
                    vendor_order_id="order-3",
                    message="insufficient funds",
                    side=OrderSide.BUY,
                    requested_qty=0.01,
                )
            ),
        )
        orch._adapter_registry.create.return_value = adapter

        report = orch.run(dep.app_user_id, dep, "alice")

        assert report.order_success is False
        ee_kwargs = orch._repo.sp_ins_execution_event.call_args.kwargs
        assert ee_kwargs["is_success_ind"] == "N"
        orch._notifier.send.assert_called_once()
        alert_text = orch._notifier.send.call_args.args[0]
        assert "insufficient funds" in alert_text
        assert "permanent" in alert_text.lower()

    @patch("quant.trade.order_policy.time.sleep")
    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_unconfirmed_retries_then_alerts(self, mock_signal, mock_sleep, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")

        unconfirmed = OrderResult(
            success=False,
            vendor_order_id="order-u",
            message="fill unconfirmed after 8.0s — vendor_order_id=order-u requires manual reconciliation",
            side=OrderSide.BUY,
            requested_qty=0.01,
        )
        adapter = _adapter_mock(
            apply_signal=MagicMock(return_value=unconfirmed),
            cancel_order=MagicMock(
                return_value=OrderResult(
                    success=True,
                    vendor_order_id="order-u",
                    message="order canceled",
                )
            ),
        )
        orch._adapter_registry.create.return_value = adapter

        report = orch.run(dep.app_user_id, dep, "alice")

        assert report.order_success is False
        assert adapter.apply_signal.call_count == 5
        assert adapter.cancel_order.call_count == 5
        assert orch._repo.sp_ins_execution_event.call_count == 5
        orch._notifier.send.assert_called_once()
        alert_text = orch._notifier.send.call_args.args[0]
        assert "manual reconciliation" in alert_text.lower()

    @patch("quant.trade.order_policy.time.sleep")
    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_all_attempts_share_one_tick_time(
        self, mock_signal, mock_sleep, orchestrator
    ):
        """TRANSACT_AT anchors the cycle, so retries must not each get their own."""
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")

        adapter = _adapter_mock(
            apply_signal=MagicMock(
                return_value=OrderResult(
                    success=False,
                    vendor_order_id="order-t",
                    message="fill unconfirmed after 8.0s — requires manual reconciliation",
                    side=OrderSide.BUY,
                    requested_qty=0.01,
                )
            ),
            cancel_order=MagicMock(
                return_value=OrderResult(
                    success=True,
                    vendor_order_id="order-t",
                    message="order canceled",
                )
            ),
        )
        orch._adapter_registry.create.return_value = adapter

        orch.run(dep.app_user_id, dep, "alice")

        ticks = {
            call.kwargs["transact_at"]
            for call in orch._repo.sp_ins_execution_event.call_args_list
        }
        assert orch._repo.sp_ins_execution_event.call_count == 5
        assert len(ticks) == 1
        assert ticks.pop().tzinfo is not None

    @patch("quant.trade.live_apply.compute_latest_position", return_value=(1.0, "2026-07-01"))
    def test_audit_failure_does_not_crash(self, mock_signal, orchestrator):
        orch, _bt = orchestrator
        dep = _deployment()
        orch._adapter_registry.has_adapter.return_value = True
        orch._credential_service.decrypt_credential.return_value = ("k", "s")

        adapter = _adapter_mock(
            apply_signal=MagicMock(
                return_value=OrderResult(
                    success=True,
                    vendor_order_id="order-4",
                    message="filled",
                    side=OrderSide.BUY,
                    requested_qty=0.01,
                    filled_qty=0.01,
                )
            ),
        )
        orch._adapter_registry.create.return_value = adapter
        orch._repo.sp_ins_execution_event.side_effect = RuntimeError("DB down")

        report = orch.run(dep.app_user_id, dep, "alice")

        assert report.order_success is True
