"""Tests for ``/api/v1/trade/deployments/*`` — Phase 1.2.

Auth is bypassed via ``app.dependency_overrides[require_user]`` and
``TradeService`` is replaced with a mock to avoid touching DB.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from quant.schemas.account import AccountSnapshot, BalanceRow, PositionRow
from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import DeploymentRow, ScheduleOptions
from quant.schemas.dry_run import DryRunReport
from quant.schemas.execution import ExecutionEventRow, TransactionRow
from quant.trade.errors import BrokerAuthError, BrokerConnectionError
from quant.trade.errors import TradeValidationError
from quant.trade.errors import DeploymentNotFound
from quant.trade.models.order import IntendedAction


def _deployment_row(**overrides) -> DeploymentRow:
    base = {
        "deployment_id": uuid.uuid4(),
        "deployment_vid": 1,
        "app_user_id": uuid.uuid4(),
        "strategy_id": uuid.uuid4(),
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
    return DeploymentRow(**base)


def _create_body(**overrides):
    base = {
        "strategy_id": str(uuid.uuid4()),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 10,
        "internal_cusip": "btcusdt.crypto",
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


class TestUpdateDeployment:
    def test_disable_deployment(self, client_and_svc):
        client, svc, user = client_and_svc
        dep_id = uuid.uuid4()
        row = _deployment_row(deployment_id=dep_id, is_enabled_ind="N", deployment_vid=2)
        svc.update_deployment.return_value = row

        resp = client.patch(
            f"/api/v1/trade/deployments/{dep_id}",
            json={"enabled": False},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_enabled_ind"] == "N"
        assert data["deployment_vid"] == 2
        svc.update_deployment.assert_called_once()

    def test_not_found_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        svc.update_deployment.side_effect = DeploymentNotFound(str(dep_id))

        resp = client.patch(
            f"/api/v1/trade/deployments/{dep_id}",
            json={"enabled": True},
        )
        assert resp.status_code == 404


class TestScheduleOptions:
    def test_lists_the_cadences_a_deployment_may_use(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.schedule_options.return_value = ScheduleOptions(tm_interval_ids=[1])

        resp = client.get("/api/v1/trade/schedule-options")

        assert resp.status_code == 200
        assert resp.json() == {"tm_interval_ids": [1]}

    def test_is_not_read_as_a_deployment_id(self, client_and_svc):
        """The literal segment must win over ``/deployments/{deployment_id}``."""
        client, svc, _ = client_and_svc
        svc.schedule_options.return_value = ScheduleOptions(tm_interval_ids=[1])

        assert client.get("/api/v1/trade/schedule-options").status_code == 200
        svc.get_deployment.assert_not_called()


class TestStopDeployment:
    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        dep_id = uuid.uuid4()
        row = _deployment_row(
            deployment_id=dep_id, deployment_status="STOPPED", is_enabled_ind="N",
        )
        svc.stop_deployment.return_value = row

        resp = client.post(f"/api/v1/trade/deployments/{dep_id}/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["deployment_status"] == "STOPPED"
        assert data["is_enabled_ind"] == "N"
        svc.stop_deployment.assert_called_once_with(user.app_user_id, dep_id)

    def test_not_found_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        svc.stop_deployment.side_effect = DeploymentNotFound(str(dep_id))

        resp = client.post(f"/api/v1/trade/deployments/{dep_id}/stop")
        assert resp.status_code == 404


class TestApplyDeployment:
    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        dep_id = uuid.uuid4()
        report = ApplyReport(
            deployment_id=dep_id,
            deployment_vid=1,
            action=IntendedAction.BUY,
            vendor_symbol="BTCUSDT",
            signal=1.0,
            position_qty=0.0,
            order_success=True,
            vendor_order_id="order-1",
            filled_qty=0.01,
            avg_price=64000.0,
            fee=0.256,
            message="order filled",
        )
        svc.apply_deployment.return_value = report

        resp = client.post(f"/api/v1/trade/deployments/{dep_id}/apply")

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "BUY"
        assert data["order_success"] is True
        assert data["filled_qty"] == 0.01
        svc.apply_deployment.assert_called_once_with(user.app_user_id, dep_id)

    def test_hold_returns_no_order(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        report = ApplyReport(
            deployment_id=dep_id,
            deployment_vid=1,
            action=IntendedAction.HOLD,
            vendor_symbol="BTCUSDT",
            signal=1.0,
            position_qty=0.01,
            message="no order needed (HOLD)",
        )
        svc.apply_deployment.return_value = report

        resp = client.post(f"/api/v1/trade/deployments/{dep_id}/apply")

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "HOLD"
        assert data["order_success"] is None

    def test_disabled_deployment_returns_400(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        svc.apply_deployment.side_effect = TradeValidationError(
            "deployment is disabled (kill switch)", status_code=400
        )

        resp = client.post(f"/api/v1/trade/deployments/{dep_id}/apply")
        assert resp.status_code == 400
        assert "kill switch" in resp.json()["detail"]

    def test_not_found_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        svc.apply_deployment.side_effect = DeploymentNotFound(str(dep_id))

        resp = client.post(f"/api/v1/trade/deployments/{dep_id}/apply")
        assert resp.status_code == 404


class TestDryRunDeployment:
    def _dry_run_body(self, **overrides):
        base = {
            "strategy_id": str(uuid.uuid4()),
            "strategy_vid": 1,
            "api_credential_id": 1,
            "app_id": 34,
            "internal_cusip": "btcusdt.crypto",
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
            internal_cusip="btcusdt.crypto",
            vendor_symbol="BTCUSDT",
            app_id=34,
            paper=True,
            qty=Decimal("0.01"),
            signal=1.0,
            intended_side="BUY",
            position_qty=0.0,
            data_as_of="2024-06-01",
            notional=600.0,
            bar_source="price_bar:bybit",
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
        assert data["notional"] == 600.0
        svc.dry_run.assert_called_once()
        assert svc.dry_run.call_args.args[0] == user.app_user_id

    def test_validation_error_returns_400(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.dry_run.side_effect = TradeValidationError(
            "no INST.PRODUCT_XREF for 'btcusdt.crypto' app_id=34"
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

    def test_rejected_credentials_return_400_with_the_broker_hint(
        self, client_and_svc
    ):
        """The hint names the fix, so it must survive as a client error.

        Reported as a 5xx it read as a platform outage and the sentence that
        says which keys to use never reached the operator.
        """
        client, svc, _ = client_and_svc
        svc.dry_run.side_effect = BrokerAuthError(
            "authentication failed during fetch_balance: bybit api_key invalid."
            " Paper/testnet mode uses https://testnet.bybit.com/ — mainnet and"
            " Demo Trading keys will not work."
        )

        resp = client.post(
            "/api/v1/trade/deployments/dry-run",
            json=self._dry_run_body(),
        )
        assert resp.status_code == 400
        assert "testnet.bybit.com" in resp.json()["detail"]

    def test_unreachable_broker_returns_503(self, client_and_svc):
        """Distinct from a rejected key: coming back later is the right move."""
        client, svc, _ = client_and_svc
        svc.dry_run.side_effect = BrokerConnectionError(
            "broker unreachable: connection timed out"
        )

        resp = client.post(
            "/api/v1/trade/deployments/dry-run",
            json=self._dry_run_body(),
        )
        assert resp.status_code == 503

    def test_failure_is_logged_server_side(self, client_and_svc, caplog):
        """A handled error leaves a trace, or prod failures need a forensic dig."""
        client, svc, _ = client_and_svc
        svc.dry_run.side_effect = BrokerAuthError("authentication failed: bad key")

        with caplog.at_level(logging.WARNING, logger="quant.api.exception_handlers"):
            client.post(
                "/api/v1/trade/deployments/dry-run",
                json=self._dry_run_body(),
            )

        assert any(
            "/api/v1/trade/deployments/dry-run" in r.getMessage()
            and "authentication failed" in r.getMessage()
            for r in caplog.records
        )


class TestAccountSnapshot:
    def _snapshot(self, paper=True):
        return AccountSnapshot(
            api_credential_id=7,
            app_id=34,
            paper=paper,
            balances=[BalanceRow(code="USDT", free=900.0, used=100.0, total=1000.0)],
            positions=[
                PositionRow(
                    symbol="BTCUSDT",
                    unified_symbol="BTC/USDT:USDT",
                    qty=0.003,
                    side="long",
                    entry_price=60000.0,
                    unrealized_pnl=3.0,
                )
            ],
        )

    def test_happy_path(self, client_and_svc):
        client, svc, user = client_and_svc
        svc.account_snapshot.return_value = self._snapshot()

        resp = client.get("/api/v1/trade/accounts/7/snapshot?paper=true")

        assert resp.status_code == 200
        data = resp.json()
        assert data["balances"][0]["total"] == 1000.0
        assert data["positions"][0]["symbol"] == "BTCUSDT"
        assert svc.account_snapshot.call_args.args[0] == user.app_user_id

    def test_paper_defaults_to_the_safe_environment(self, client_and_svc):
        """Omitting the flag must never reach a real-money account."""
        client, svc, _ = client_and_svc
        svc.account_snapshot.return_value = self._snapshot()

        client.get("/api/v1/trade/accounts/7/snapshot")

        assert svc.account_snapshot.call_args.kwargs["paper"] is True

    def test_live_is_explicit(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.account_snapshot.return_value = self._snapshot(paper=False)

        resp = client.get("/api/v1/trade/accounts/7/snapshot?paper=false")

        assert svc.account_snapshot.call_args.kwargs["paper"] is False
        assert resp.json()["paper"] is False

    def test_unowned_credential_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        svc.account_snapshot.side_effect = TradeValidationError(
            "API credential not found or not owned", status_code=404
        )

        resp = client.get("/api/v1/trade/accounts/7/snapshot")
        assert resp.status_code == 404

    def test_an_empty_account_is_200_not_404(self, client_and_svc):
        """No cash and no positions is a valid answer, not a missing resource."""
        client, svc, _ = client_and_svc
        svc.account_snapshot.return_value = AccountSnapshot(
            api_credential_id=7, app_id=34, paper=True, balances=[], positions=[]
        )

        resp = client.get("/api/v1/trade/accounts/7/snapshot")

        assert resp.status_code == 200
        assert resp.json()["positions"] == []


class TestExecutionLog:
    def _event_row(self, user_id) -> ExecutionEventRow:
        return ExecutionEventRow(
            execution_event_id=uuid.uuid4(),
            deployment_id=uuid.uuid4(),
            deployment_vid=1,
            internal_cusip="btcusdt.crypto",
            api_credential_id=1,
            app_id=10,
            is_paper_ind="Y",
            signal_value=Decimal("1.25"),
            position_qty=Decimal("0"),
            buy_sell_cd="BUY",
            quantity=Decimal("0.01"),
            vendor_order_id="ord-123",
            is_success_ind="Y",
            transact_at=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        )

    def test_list_execution_events(self, client_and_svc):
        client, svc, user = client_and_svc
        row = self._event_row(user.app_user_id)
        svc.list_execution_events.return_value = [row]

        resp = client.get("/api/v1/trade/execution-events?limit=20")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["buy_sell_cd"] == "BUY"
        svc.list_execution_events.assert_called_once_with(
            user.app_user_id,
            deployment_id=None,
            limit=20,
        )

    def test_list_deployment_events(self, client_and_svc):
        client, svc, user = client_and_svc
        dep_id = uuid.uuid4()
        svc.list_execution_events.return_value = []

        resp = client.get(f"/api/v1/trade/deployments/{dep_id}/events?limit=5")

        assert resp.status_code == 200
        svc.list_execution_events.assert_called_once_with(
            user.app_user_id,
            deployment_id=dep_id,
            limit=5,
        )

    def test_list_transactions(self, client_and_svc):
        client, svc, user = client_and_svc
        row = TransactionRow(
            transaction_id=uuid.uuid4(),
            deployment_id=uuid.uuid4(),
            deployment_vid=1,
            internal_cusip="btcusdt.crypto",
            api_credential_id=1,
            app_id=10,
            is_paper_ind="Y",
            vendor_symbol="BTCUSDT",
            buy_sell_cd="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("60000"),
            notional_amt=Decimal("600"),
            fee_amt=Decimal("0.1"),
            vendor_order_id="ord-456",
            trans_ccy_cd="USDT",
            filled_at=datetime(2026, 8, 29, 10, 1, tzinfo=timezone.utc),
        )
        svc.list_transactions.return_value = [row]

        resp = client.get("/api/v1/trade/transactions")

        assert resp.status_code == 200
        assert resp.json()[0]["vendor_symbol"] == "BTCUSDT"
        svc.list_transactions.assert_called_once()

    def test_deployment_not_found_returns_404(self, client_and_svc):
        client, svc, _ = client_and_svc
        dep_id = uuid.uuid4()
        svc.list_execution_events.side_effect = DeploymentNotFound(str(dep_id))

        resp = client.get(f"/api/v1/trade/deployments/{dep_id}/events")
        assert resp.status_code == 404
