"""Unit tests for :mod:`quant.trade.db_repo` validation."""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from quant.queue.repo import BtQueueRepo
from quant.trade.db_repo import TradeRepo
from quant.trade.errors import TradeValidationError


@pytest.fixture
def repo():
    bt = BtQueueRepo("postgresql://test")
    return TradeRepo("postgresql://test", bt=bt)


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


def _owned_strategy(app_user_id):
    return {"user_id": str(app_user_id)}


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
    @patch.object(TradeRepo, "_fetch_strategy", return_value=None)
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
    @patch.object(TradeRepo, "_fetch_strategy")
    def test_strategy_owner_mismatch(self, mock_strat, mock_cred, repo):
        owner = uuid4()
        other = uuid4()
        mock_cred.return_value = {
            "app_user_id": owner,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        mock_strat.return_value = _owned_strategy(other)
        with pytest.raises(TradeValidationError, match="does not belong to user") as exc:
            repo.validate_create_deployment(**_deployment_kwargs(app_user_id=owner))
        assert exc.value.status_code == 403

    @patch.object(TradeRepo, "_fetch_credential")
    @patch.object(TradeRepo, "_fetch_strategy")
    @patch.object(TradeRepo, "_fetch_current_deployment")
    def test_deployment_owner_mismatch(self, mock_current, mock_strat, mock_cred, repo):
        owner = uuid4()
        other = uuid4()
        mock_cred.return_value = {
            "app_user_id": owner,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        mock_strat.return_value = _owned_strategy(owner)
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
    @patch.object(TradeRepo, "_fetch_strategy")
    @patch.object(TradeRepo, "_fetch_current_deployment", return_value=None)
    def test_live_with_confirm_accepted(self, _dep, mock_strat, mock_cred, repo):
        uid = uuid4()
        mock_cred.return_value = {
            "app_user_id": uid,
            "app_id": 10,
            "is_active_ind": "Y",
            "is_current_ind": "Y",
        }
        mock_strat.return_value = _owned_strategy(uid)
        repo.validate_create_deployment(
            **_deployment_kwargs(app_user_id=uid, is_paper_ind="N"),
            confirm_live=True,
        )


class TestValidateDryRun:
    def test_missing_strategy_vid(self, repo):
        with pytest.raises(TradeValidationError, match="strategy_vid"):
            repo.validate_dry_run(
                app_user_id=uuid4(),
                strategy_id=uuid4(),
                strategy_vid=None,
                api_credential_id=1,
                app_id=10,
                internal_cusip="btc-usd.crypto",
                qty=Decimal("0.01"),
            )

    @patch.object(TradeRepo, "_fetch_credential")
    @patch.object(TradeRepo, "_fetch_strategy")
    def test_returns_strategy_row(self, mock_strat, mock_cred, repo):
        uid = uuid4()
        sid = uuid4()
        mock_cred.return_value = {
            "is_active_ind": "Y",
            "app_user_id": str(uid),
            "app_id": 10,
        }
        mock_strat.return_value = {
            "user_id": str(uid),
            "strategy_nm": "s1",
            "config_json": {},
        }

        row = repo.validate_dry_run(
            app_user_id=uid,
            strategy_id=sid,
            strategy_vid=1,
            api_credential_id=1,
            app_id=10,
            internal_cusip="btc-usd.crypto",
            qty=Decimal("0.01"),
        )

        assert row["strategy_nm"] == "s1"
        mock_strat.assert_called_once_with(sid, 1)


class TestGetDeploymentForApply:
    @patch.object(TradeRepo, "sp_get_deployment")
    def test_returns_row_when_enabled(self, mock_get, repo):
        uid = uuid4()
        dep_id = uuid4()
        mock_get.return_value = [{"deployment_id": dep_id, "is_enabled_ind": "Y"}]

        result = repo.get_deployment_for_apply(dep_id, uid)

        assert result["deployment_id"] == dep_id
        mock_get.assert_called_once_with(app_user_id=uid, deployment_id=dep_id)

    @patch.object(TradeRepo, "sp_get_deployment", return_value=[])
    def test_not_found_raises_404(self, _get, repo):
        with pytest.raises(TradeValidationError, match="not found") as exc:
            repo.get_deployment_for_apply(uuid4(), uuid4())
        assert exc.value.status_code == 404

    @patch.object(TradeRepo, "sp_get_deployment")
    def test_disabled_raises_400(self, mock_get, repo):
        mock_get.return_value = [{"deployment_id": uuid4(), "is_enabled_ind": "N"}]

        with pytest.raises(TradeValidationError, match="kill switch") as exc:
            repo.get_deployment_for_apply(uuid4(), uuid4())
        assert exc.value.status_code == 400


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
