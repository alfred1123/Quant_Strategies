"""Unit tests for deployment dry-run orchestration."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.schemas.dry_run import DryRunRequest
from quant.trade.adapters.base import TradeAdapter
from quant.trade.dry_run import run_dry_run
from quant.trade.errors import TradeValidationError


def _dry_run_request(**overrides):
    base = {
        "strategy_id": uuid4(),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 34,
        "internal_cusip": "btc-usd.crypto",
        "qty": Decimal("0.01"),
        "paper": True,
    }
    base.update(overrides)
    return DryRunRequest(**base)


@pytest.fixture
def deps():
    app_user_id = uuid4()
    repo = MagicMock()
    repo.validate_dry_run.return_value = {
        "strategy_nm": "test-strategy",
        "config_json": {"internal_cusip": "btc-usd.crypto", "substrategies": []},
    }
    bt = MagicMock()
    credential_service = MagicMock()
    credential_service.decrypt_credential.return_value = ("key", "secret")
    credential_repo = MagicMock()
    adapter_registry = MagicMock()
    adapter = MagicMock()
    adapter.validate_for_dry_run.return_value = "BTCUSDT"
    adapter.get_position_qty.return_value = 0.0
    adapter.intended_side = TradeAdapter.intended_side
    adapter.__enter__ = MagicMock(return_value=adapter)
    adapter.__exit__ = MagicMock(return_value=False)
    adapter_registry.has_adapter.return_value = True
    adapter_registry.create.return_value = adapter
    data_caches = MagicMock()
    return {
        "app_user_id": app_user_id,
        "repo": repo,
        "bt": bt,
        "credential_service": credential_service,
        "credential_repo": credential_repo,
        "adapter_registry": adapter_registry,
        "data_caches": data_caches,
        "adapter": adapter,
    }


class TestRunDryRun:
    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_happy_path(self, _signal, deps):
        report = run_dry_run(
            app_user_id=deps["app_user_id"],
            req=_dry_run_request(),
            repo=deps["repo"],
            bt=deps["bt"],
            credential_service=deps["credential_service"],
            credential_repo=deps["credential_repo"],
            adapter_registry=deps["adapter_registry"],
            data_caches=deps["data_caches"],
        )

        assert report.vendor_symbol == "BTCUSDT"
        assert report.signal == 1.0
        assert report.intended_side == "BUY"
        assert report.position_qty == 0.0
        deps["adapter"].__enter__.assert_called_once()
        deps["adapter"].__exit__.assert_called_once()
        deps["bt"].fetch_result_payload.assert_called_once()

    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_disconnects_on_broker_error(self, _signal, deps):
        deps["adapter"].validate_for_dry_run.side_effect = ValueError(
            "vendor symbol 'X' not listed on Bybit"
        )

        with pytest.raises(TradeValidationError, match="not listed"):
            run_dry_run(
                app_user_id=deps["app_user_id"],
                req=_dry_run_request(),
                repo=deps["repo"],
                bt=deps["bt"],
                credential_service=deps["credential_service"],
                credential_repo=deps["credential_repo"],
                adapter_registry=deps["adapter_registry"],
                data_caches=deps["data_caches"],
            )

        deps["adapter"].__exit__.assert_called_once()

    def test_unknown_broker_app_id(self, deps):
        deps["adapter_registry"].has_adapter.return_value = False

        with pytest.raises(TradeValidationError, match="no broker adapter"):
            run_dry_run(
                app_user_id=deps["app_user_id"],
                req=_dry_run_request(app_id=999),
                repo=deps["repo"],
                bt=deps["bt"],
                credential_service=deps["credential_service"],
                credential_repo=deps["credential_repo"],
                adapter_registry=deps["adapter_registry"],
                data_caches=deps["data_caches"],
            )

    def test_missing_credential(self, deps):
        deps["credential_service"].decrypt_credential.return_value = None

        with pytest.raises(TradeValidationError, match="credential not found"):
            run_dry_run(
                app_user_id=deps["app_user_id"],
                req=_dry_run_request(),
                repo=deps["repo"],
                bt=deps["bt"],
                credential_service=deps["credential_service"],
                credential_repo=deps["credential_repo"],
                adapter_registry=deps["adapter_registry"],
                data_caches=deps["data_caches"],
            )
