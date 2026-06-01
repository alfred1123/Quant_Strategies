"""Unit tests for :mod:`quant.trade.db_repo` validation."""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from quant.trade.db_repo import TradeRepo
from quant.trade.errors import TradeValidationError


@pytest.fixture
def repo():
    return TradeRepo("postgresql://test")


def _deployment_kwargs(**overrides):
    base = {
        "deployment_id": uuid4(),
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
    }
    base.update(overrides)
    return base


class TestValidateCreateDeployment:
    def test_missing_deployment_id(self, repo):
        with pytest.raises(TradeValidationError, match="deployment_id"):
            repo.validate_create_deployment(**_deployment_kwargs(deployment_id=None))

    @patch.object(TradeRepo, "_fetch_credential", return_value=None)
    def test_unknown_credential(self, mock_cred, repo):
        with pytest.raises(TradeValidationError, match="API credential") as exc:
            repo.validate_create_deployment(**_deployment_kwargs())
        assert exc.value.status_code == 404
        mock_cred.assert_called_once()

    @patch.object(TradeRepo, "_fetch_credential")
    @patch.object(TradeRepo, "_strategy_exists", return_value=False)
    def test_unknown_strategy(self, _strat, mock_cred, repo):
        uid = uuid4()
        mock_cred.return_value = {
            "app_user_id": uid,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        with pytest.raises(TradeValidationError, match="strategy_id") as exc:
            repo.validate_create_deployment(**_deployment_kwargs(app_user_id=uid))
        assert exc.value.status_code == 404

    @patch.object(TradeRepo, "_fetch_credential")
    @patch.object(TradeRepo, "_strategy_exists", return_value=True)
    @patch.object(TradeRepo, "_fetch_current_deployment")
    def test_deployment_owner_mismatch(self, mock_current, _strat, mock_cred, repo):
        owner = uuid4()
        other = uuid4()
        mock_cred.return_value = {
            "app_user_id": owner,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        mock_current.return_value = {"app_user_id": other}
        with pytest.raises(TradeValidationError, match="does not belong") as exc:
            repo.validate_create_deployment(**_deployment_kwargs(app_user_id=owner))
        assert exc.value.status_code == 403


    @patch.object(TradeRepo, "_fetch_credential")
    def test_live_without_confirm_rejected(self, mock_cred, repo):
        uid = uuid4()
        mock_cred.return_value = {
            "app_user_id": uid,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        with pytest.raises(TradeValidationError, match="confirm_live") as exc:
            repo.validate_create_deployment(
                **_deployment_kwargs(app_user_id=uid, is_paper_ind="N")
            )
        assert exc.value.status_code == 400

    @patch.object(TradeRepo, "_fetch_credential")
    @patch.object(TradeRepo, "_strategy_exists", return_value=True)
    @patch.object(TradeRepo, "_fetch_current_deployment", return_value=None)
    def test_live_with_confirm_accepted(self, _dep, _strat, mock_cred, repo):
        uid = uuid4()
        mock_cred.return_value = {
            "app_user_id": uid,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        repo.validate_create_deployment(
            **_deployment_kwargs(app_user_id=uid, is_paper_ind="N"),
            confirm_live=True,
        )


class TestValidateExecutionEvent:
    @patch.object(TradeRepo, "_fetch_deployment_version", return_value=None)
    def test_unknown_deployment(self, _fetch, repo):
        with pytest.raises(TradeValidationError, match="deployment not found") as exc:
            repo.validate_execution_event(
                app_user_id=uuid4(),
                deployment_id=uuid4(),
                deployment_vid=1,
                buy_sell_cd="BUY",
                is_success_ind="Y",
                user_id="alice",
            )
        assert exc.value.status_code == 404
