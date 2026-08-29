"""Tests for ``/api/v1/market-data/*``.

Auth is bypassed via ``app.dependency_overrides`` and the services are replaced
with mocks so nothing touches a database or an exchange.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from quant.market_data.service import BackfillResult
from quant.market_data.subscriptions import SubscriptionError

DAILY = 1
BYBIT = 34
CUSIP = "btcusdt.crypto"
FIRST_BAR = datetime(2026, 1, 1, tzinfo=UTC)
LAST_BAR = datetime(2026, 8, 1, tzinfo=UTC)


def _subscription_row(**overrides) -> dict:
    base = {
        "bar_subscription_id": str(uuid.uuid4()),
        "bar_subscription_vid": 1,
        "internal_cusip": CUSIP,
        "tm_interval_id": DAILY,
        "source_app_id": BYBIT,
        "is_enabled_ind": "Y",
        "backfill_from_ts": None,
        "transact_from_ts": datetime(2026, 8, 1, tzinfo=UTC),
        # A table column the procedure does not currently SELECT. Present here
        # to prove the response is a projection, so adding one to the cursor
        # cannot quietly widen the public API.
        "created_at": datetime(2026, 8, 1, tzinfo=UTC),
        "coverage": {
            "first_bar": FIRST_BAR,
            "last_bar": LAST_BAR,
            "gaps": 0,
            "error": None,
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def client_and_svc():
    """TestClient + a mock subscription service and warmer."""
    with patch("quant.shared.db.psycopg"):
        from quant.api.auth.dependencies import require_user, require_user_or_service
        from quant.api.auth.models import CurrentUser
        from quant.api.main import app
        from quant.api.market_data.router import _get_bar_warmer, _get_subscriptions

        app.state.db_conninfo = "postgresql://stub"
        app.state.data_caches = MagicMock()
        app.state.price_bars = MagicMock()

        svc = MagicMock()
        warmer = MagicMock()
        app.dependency_overrides[_get_subscriptions] = lambda: svc
        app.dependency_overrides[_get_bar_warmer] = lambda: warmer
        user = CurrentUser(app_user_id=uuid.uuid4(), username="alice", session_gen=1)
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[require_user_or_service] = lambda: "alice"

        try:
            yield TestClient(app), svc, warmer
        finally:
            app.dependency_overrides.clear()


class TestListSubscriptions:
    def test_returns_rows_with_coverage(self, client_and_svc):
        client, svc, _warmer = client_and_svc
        svc.list_subscriptions.return_value = [_subscription_row()]

        resp = client.get("/api/v1/market-data/subscriptions")

        assert resp.status_code == 200
        row = resp.json()[0]
        assert row["internal_cusip"] == CUSIP
        assert row["coverage"]["gaps"] == 0

    def test_is_not_scoped_to_the_caller(self, client_and_svc):
        """Bars are shared facts — everyone sees the same capture list."""
        client, svc, _warmer = client_and_svc
        svc.list_subscriptions.return_value = []

        client.get("/api/v1/market-data/subscriptions")

        svc.list_subscriptions.assert_called_once_with()

    def test_columns_the_schema_does_not_model_are_dropped(self, client_and_svc):
        client, svc, _warmer = client_and_svc
        svc.list_subscriptions.return_value = [_subscription_row()]

        row = client.get("/api/v1/market-data/subscriptions").json()[0]

        assert "created_at" not in row


class TestSubscribe:
    def test_creates_and_returns_coverage(self, client_and_svc):
        client, svc, _warmer = client_and_svc
        row = _subscription_row()
        svc.subscribe.return_value = {
            k: v for k, v in row.items() if k != "coverage"
        }
        svc.coverage.return_value = row["coverage"]

        resp = client.post(
            "/api/v1/market-data/subscriptions",
            json={
                "internal_cusip": CUSIP,
                "tm_interval_id": DAILY,
                "source_app_id": BYBIT,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["is_enabled_ind"] == "Y"

    def test_an_unwarmable_series_is_a_400_naming_the_reason(self, client_and_svc):
        """The whole point of validating on write is that the caller can act."""
        client, svc, _warmer = client_and_svc
        svc.subscribe.side_effect = SubscriptionError(
            "no INST.PRODUCT_XREF row maps 'wat.crypto' to a symbol on app 34"
        )

        resp = client.post(
            "/api/v1/market-data/subscriptions",
            json={
                "internal_cusip": "wat.crypto",
                "tm_interval_id": DAILY,
                "source_app_id": BYBIT,
            },
        )

        assert resp.status_code == 400
        assert "PRODUCT_XREF" in resp.json()["detail"]

    def test_failure_is_logged_server_side(self, client_and_svc, caplog):
        client, svc, _warmer = client_and_svc
        svc.subscribe.side_effect = SubscriptionError("venue is not an exchange")

        with caplog.at_level("WARNING"):
            client.post(
                "/api/v1/market-data/subscriptions",
                json={
                    "internal_cusip": CUSIP,
                    "tm_interval_id": DAILY,
                    "source_app_id": 99,
                },
            )

        assert "venue is not an exchange" in caplog.text


class TestCoverage:
    def test_answers_for_a_series_nobody_subscribed_to(self, client_and_svc):
        client, svc, _warmer = client_and_svc
        svc.coverage.return_value = {
            "first_bar": FIRST_BAR,
            "last_bar": LAST_BAR,
            "gaps": 3,
            "error": None,
        }

        resp = client.get(
            "/api/v1/market-data/price-bars/coverage",
            params={
                "internal_cusip": CUSIP,
                "tm_interval_id": DAILY,
                "source_app_id": BYBIT,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["gaps"] == 3


class TestBackfill:
    def test_reports_what_was_filled(self, client_and_svc):
        client, svc, _warmer = client_and_svc
        svc.backfill.return_value = BackfillResult(
            start=FIRST_BAR,
            end=LAST_BAR,
            expected=100,
            missing=10,
            inserted=10,
            unfilled=(),
        )

        resp = client.post(
            "/api/v1/market-data/price-bars/backfill",
            json={
                "internal_cusip": CUSIP,
                "tm_interval_id": DAILY,
                "source_app_id": BYBIT,
                "start": FIRST_BAR.isoformat(),
            },
        )

        assert resp.status_code == 200
        assert resp.json()["is_continuous"] is True

    def test_a_hole_is_reported_not_raised(self, client_and_svc):
        """Inverting the live path's fail-closed rule is the point of backfill."""
        client, svc, _warmer = client_and_svc
        hole = datetime(2026, 3, 1, tzinfo=UTC)
        svc.backfill.return_value = BackfillResult(
            start=FIRST_BAR,
            end=LAST_BAR,
            expected=100,
            missing=10,
            inserted=9,
            unfilled=(hole,),
        )

        resp = client.post(
            "/api/v1/market-data/price-bars/backfill",
            json={
                "internal_cusip": CUSIP,
                "tm_interval_id": DAILY,
                "source_app_id": BYBIT,
                "start": FIRST_BAR.isoformat(),
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_continuous"] is False
        assert [datetime.fromisoformat(ts) for ts in body["unfilled"]] == [hole]


class TestSync:
    def test_still_reports_a_partial_pass_as_success(self, client_and_svc):
        client, _svc, warmer = client_and_svc
        report = MagicMock()
        report.instruments, report.inserted, report.failed = 3, 2, 1
        report.results = []
        warmer.run.return_value = report

        resp = client.post("/api/v1/market-data/price-bars/sync")

        assert resp.status_code == 200
        assert resp.json()["failed"] == 1
