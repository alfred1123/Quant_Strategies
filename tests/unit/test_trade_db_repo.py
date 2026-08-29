"""Unit tests for :mod:`quant.trade.db_repo` validation."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from quant.queue.repo import BtQueueRepo
from quant.trade.db_repo import TradeRepo
from quant.trade.errors import TradeValidationError

PROC_DIR = (
    Path(__file__).resolve().parents[2] / "db" / "liquidbase" / "trade" / "procedures"
)


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
        "internal_cusip": "btcusdt.crypto",
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
                internal_cusip="btcusdt.crypto",
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
            internal_cusip="btcusdt.crypto",
            qty=Decimal("0.01"),
        )

        assert row["strategy_nm"] == "s1"
        mock_strat.assert_called_once_with(sid, 1)


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


class TestValidateScheduleStatus:
    def _kwargs(self, **overrides):
        base = {
            "deployment_schedule_id": uuid4(),
            "deployment_id": uuid4(),
            "deployment_vid": 1,
            "status": "PENDING",
            "scheduled_ts": datetime(2026, 8, 1, tzinfo=UTC),
            "user_id": "alice",
        }
        base.update(overrides)
        return base

    @patch.object(TradeRepo, "_fetch_deployment_version", return_value={"x": 1})
    def test_unknown_status_rejected(self, _fetch, repo):
        with pytest.raises(TradeValidationError, match="status must be one of"):
            repo.validate_schedule_status(**self._kwargs(status="RUNNING"))

    @patch.object(TradeRepo, "_fetch_deployment_version", return_value={"x": 1})
    def test_pending_requires_scheduled_ts(self, _fetch, repo):
        with pytest.raises(TradeValidationError, match="scheduled_ts is required"):
            repo.validate_schedule_status(**self._kwargs(scheduled_ts=None))

    @patch.object(TradeRepo, "_fetch_deployment_version", return_value={"x": 1})
    def test_terminal_status_needs_no_scheduled_ts(self, _fetch, repo):
        repo.validate_schedule_status(
            **self._kwargs(status="FAILED", scheduled_ts=None)
        )

    @patch.object(TradeRepo, "_fetch_deployment_version", return_value=None)
    def test_unknown_deployment(self, _fetch, repo):
        with pytest.raises(TradeValidationError, match="deployment not found") as exc:
            repo.validate_schedule_status(**self._kwargs())
        assert exc.value.status_code == 404


def _ddl_param_count(proc_file: str) -> int:
    """Number of IN/OUT parameters declared by a procedure's DDL."""
    txt = (PROC_DIR / proc_file).read_text()
    sig = re.search(
        r"CREATE OR REPLACE PROCEDURE\s+[\w.]+\s*\((.*?)\)\s*LANGUAGE",
        txt,
        re.S | re.I,
    )
    assert sig, f"could not parse a signature out of {proc_file}"
    return len(
        [ln for ln in sig.group(1).splitlines() if re.match(r"\s*(IN|OUT)\s+\w+", ln)]
    )


def _call_arg_count(sql: str) -> int:
    return sql.count("%s") + sql.count("NULL::")


class TestCallMatchesProcedureDdl:
    """CALL argument count must track the procedure DDL.

    Postgres treats a changed parameter list as a new overload instead of an
    error, so a stale CALL keeps resolving to the old signature and the
    mismatch surfaces as missing data rather than a failure.
    """

    @patch.object(TradeRepo, "sp_get_deployment", return_value=[{"deployment_id": 1}])
    @patch.object(TradeRepo, "_call_write")
    def test_ins_deployment(self, mock_write, _get, repo):
        repo.write_deployment(**_deployment_kwargs())
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_INS_DEPLOYMENT.sql")

    @patch.object(TradeRepo, "validate_execution_event")
    @patch.object(TradeRepo, "_call_write")
    def test_ins_execution_event(self, mock_write, _validate, repo):
        repo.sp_ins_execution_event(
            execution_event_id=uuid4(),
            app_user_id=uuid4(),
            deployment_id=uuid4(),
            deployment_vid=1,
            buy_sell_cd="BUY",
            is_success_ind="Y",
            user_id="alice",
        )
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_INS_EXECUTION_EVENT.sql")

    @patch.object(TradeRepo, "validate_execution_event")
    @patch.object(TradeRepo, "_call_write")
    def test_execution_event_transact_at_is_never_null(
        self, mock_write, _validate, repo
    ):
        """TRANSACT_AT is NOT NULL with no default — the repo must always send one.

        Found by type rather than by position: this used to check the last
        parameter, which quietly became POSITION_QTY when that was appended.
        """
        repo.sp_ins_execution_event(
            execution_event_id=uuid4(),
            app_user_id=uuid4(),
            deployment_id=uuid4(),
            deployment_vid=1,
            buy_sell_cd="BUY",
            is_success_ind="Y",
            user_id="alice",
        )
        params = mock_write.call_args.args[1]
        assert len([p for p in params if isinstance(p, datetime)]) == 1

    @patch.object(TradeRepo, "validate_execution_event")
    @patch.object(TradeRepo, "_call_write")
    def test_execution_event_records_the_position(self, mock_write, _validate, repo):
        """The position the decision was made against has to reach the row."""
        repo.sp_ins_execution_event(
            execution_event_id=uuid4(),
            app_user_id=uuid4(),
            deployment_id=uuid4(),
            deployment_vid=1,
            buy_sell_cd="SELL",
            is_success_ind="Y",
            user_id="alice",
            position_qty=-0.003,
        )
        assert -0.003 in mock_write.call_args.args[1]

    @patch.object(TradeRepo, "validate_execution_event")
    @patch.object(TradeRepo, "_call_write")
    def test_execution_event_keeps_flat_distinct_from_unknown(
        self, mock_write, _validate, repo
    ):
        """0.0 means a flat book; None means the position was never read."""
        common = {
            "app_user_id": uuid4(),
            "deployment_id": uuid4(),
            "deployment_vid": 1,
            "buy_sell_cd": "BUY",
            "is_success_ind": "Y",
            "user_id": "alice",
        }
        repo.sp_ins_execution_event(
            execution_event_id=uuid4(), position_qty=0.0, **common
        )
        flat = mock_write.call_args.args[1]
        repo.sp_ins_execution_event(execution_event_id=uuid4(), **common)
        unknown = mock_write.call_args.args[1]

        assert 0.0 in flat
        assert unknown[-1] is None

    @patch.object(TradeRepo, "validate_schedule_status")
    @patch.object(TradeRepo, "_call_write")
    def test_ins_deployment_schedule_status(self, mock_write, _validate, repo):
        repo.sp_ins_deployment_schedule_status(
            deployment_schedule_id=uuid4(),
            deployment_id=uuid4(),
            deployment_vid=1,
            status="PENDING",
            scheduled_ts=datetime(2026, 8, 1, tzinfo=UTC),
            user_id="alice",
        )
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count(
            "SP_INS_DEPLOYMENT_SCHEDULE_STATUS.sql"
        )

    @patch.object(TradeRepo, "_call_get", return_value=[])
    def test_get_missed_due_deployments(self, mock_get, repo):
        repo.sp_get_missed_due_deployments(tm_interval_id=1)
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count(
            "SP_GET_MISSED_DUE_DEPLOYMENTS.sql"
        )

    @patch.object(TradeRepo, "_call_get", return_value=[])
    def test_get_next_due_deployments(self, mock_get, repo):
        repo.sp_get_next_due_deployments()
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count(
            "SP_GET_NEXT_DUE_DEPLOYMENTS.sql"
        )

    @patch.object(TradeRepo, "_call_get", return_value=[])
    def test_get_scheduled_instruments(self, mock_get, repo):
        repo.sp_get_scheduled_instruments()
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count(
            "SP_GET_SCHEDULED_INSTRUMENTS.sql"
        )

    @patch.object(TradeRepo, "_call_get", return_value=[])
    def test_get_execution_event(self, mock_get, repo):
        uid = uuid4()
        repo.sp_get_execution_event(app_user_id=uid, limit=25)
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count(
            "SP_GET_EXECUTION_EVENT.sql"
        )
        assert mock_get.call_args.args[1][2] == 25

    @patch.object(TradeRepo, "_call_get", return_value=[])
    def test_get_execution_event_clamps_limit(self, mock_get, repo):
        repo.sp_get_execution_event(app_user_id=uuid4(), limit=999)
        assert mock_get.call_args.args[1][2] == 200

    @patch.object(TradeRepo, "_call_get", return_value=[])
    def test_get_transaction(self, mock_get, repo):
        repo.sp_get_transaction(app_user_id=uuid4(), deployment_id=uuid4(), limit=10)
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_GET_TRANSACTION.sql")
