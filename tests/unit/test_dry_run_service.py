"""Unit tests for deployment dry-run orchestration."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.schemas.dry_run import DryRunReport, DryRunRequest
from quant.trade.adapters.base import TradeAdapter
from quant.trade.dry_run import run_dry_run
from quant.trade.errors import SymbolMappingError, TradeValidationError


def _dry_run_request(**overrides):
    base = {
        "strategy_id": uuid4(),
        "strategy_vid": 1,
        "api_credential_id": 1,
        "app_id": 34,
        "internal_cusip": "btcusdt.crypto",
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
        "config_json": {"internal_cusip": "btcusdt.crypto", "substrategies": []},
    }
    bt = MagicMock()
    credential_service = MagicMock()
    credential_service.decrypt_credential.return_value = ("key", "secret")
    credential_repo = MagicMock()
    adapter_registry = MagicMock()
    adapter = MagicMock()
    adapter.validate_for_dry_run.return_value = "BTCUSDT"
    adapter.get_position_qty.return_value = 0.0
    adapter.get_last_price.return_value = 60000.0
    adapter.intended_side = TradeAdapter.intended_side
    adapter.__enter__ = MagicMock(return_value=adapter)
    adapter.__exit__ = MagicMock(return_value=False)
    adapter_registry.has_adapter.return_value = True
    adapter_registry.create.return_value = adapter
    data_caches = MagicMock()
    data_caches.refdata.resolve_interval_id.return_value = 1
    price_bars = MagicMock()
    return {
        "app_user_id": app_user_id,
        "repo": repo,
        "bt": bt,
        "credential_service": credential_service,
        "credential_repo": credential_repo,
        "adapter_registry": adapter_registry,
        "data_caches": data_caches,
        "price_bars": price_bars,
        "adapter": adapter,
    }


@pytest.fixture(autouse=True)
def _venue():
    """Every dry run in this module prices off a venue that serves bars."""
    with patch("quant.trade.bar_source.exchange_id_for_app", return_value="bybit"):
        yield


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
            price_bars=deps["price_bars"],
        )

        assert report.vendor_symbol == "BTCUSDT"
        assert report.signal == 1.0
        assert report.intended_side == "BUY"
        assert report.position_qty == 0.0
        assert report.notional == 600.0  # 0.01 * 60000
        deps["adapter"].__enter__.assert_called_once()
        deps["adapter"].__exit__.assert_called_once()
        deps["bt"].fetch_result_payload.assert_called_once()

    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_disconnects_on_broker_error(self, _signal, deps):
        deps["adapter"].validate_for_dry_run.side_effect = SymbolMappingError(
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
                price_bars=deps["price_bars"],
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
                price_bars=deps["price_bars"],
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
                price_bars=deps["price_bars"],
            )

    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_notional_none_when_mark_unavailable(self, _signal, deps):
        deps["adapter"].get_last_price.return_value = None
        report = run_dry_run(
            app_user_id=deps["app_user_id"],
            req=_dry_run_request(),
            repo=deps["repo"],
            bt=deps["bt"],
            credential_service=deps["credential_service"],
            credential_repo=deps["credential_repo"],
            adapter_registry=deps["adapter_registry"],
            data_caches=deps["data_caches"],
            price_bars=deps["price_bars"],
        )
        assert report.notional is None


class TestPreviewReadsWhatTheApplyWillRead:
    """A dry run is only a preview if it prices off the live series.

    It used to price off the provider unconditionally while the apply that
    followed priced off the exchange, so the two could disagree on the signal
    with neither being wrong — the failure this class exists to catch.
    """

    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_signal_comes_from_the_venue_the_order_would_hit(self, mock_signal, deps):
        report = run_dry_run(
            app_user_id=deps["app_user_id"],
            req=_dry_run_request(app_id=34),
            repo=deps["repo"],
            bt=deps["bt"],
            credential_service=deps["credential_service"],
            credential_repo=deps["credential_repo"],
            adapter_registry=deps["adapter_registry"],
            data_caches=deps["data_caches"],
            price_bars=deps["price_bars"],
        )

        assert report.bar_source == "price_bar:bybit"
        loader = mock_signal.call_args.kwargs["bar_loader"]
        assert loader is not None
        loader("btcusdt.crypto", 120)
        deps["price_bars"].for_app.return_value.load_window.assert_called_once_with(
            "btcusdt.crypto", 120, tm_interval_id=1, source_app_id=34
        )

    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_no_schedule_yet_means_daily(self, _signal, deps):
        """A dry run predates the schedule, and daily is the only cadence a
        deployment may run on."""
        run_dry_run(
            app_user_id=deps["app_user_id"],
            req=_dry_run_request(),
            repo=deps["repo"],
            bt=deps["bt"],
            credential_service=deps["credential_service"],
            credential_repo=deps["credential_repo"],
            adapter_registry=deps["adapter_registry"],
            data_caches=deps["data_caches"],
            price_bars=deps["price_bars"],
        )

        deps["data_caches"].refdata.resolve_interval_id.assert_called_once_with(
            timedelta(days=1)
        )

    @patch("quant.trade.dry_run.compute_latest_position", return_value=(1.0, "2024-06-01"))
    def test_venue_less_broker_still_previews_off_the_provider(self, mock_signal, deps):
        """Futu equities have no market-data venue, so the provider series is
        the only one either side can read — and both still agree."""
        with patch("quant.trade.bar_source.exchange_id_for_app", return_value=None):
            report = run_dry_run(
                app_user_id=deps["app_user_id"],
                req=_dry_run_request(app_id=99),
                repo=deps["repo"],
                bt=deps["bt"],
                credential_service=deps["credential_service"],
                credential_repo=deps["credential_repo"],
                adapter_registry=deps["adapter_registry"],
                data_caches=deps["data_caches"],
                price_bars=deps["price_bars"],
            )

        assert report.bar_source == "provider"
        assert mock_signal.call_args.kwargs["bar_loader"] is None


class TestDryRunReportNotional:
    """Notional field on the pydantic schema — computed by the orchestrator."""

    def _report(self, *, notional=None):
        return DryRunReport(
            strategy_id=uuid4(),
            strategy_vid=1,
            strategy_nm="x",
            internal_cusip="btcusdt.crypto",
            vendor_symbol="BTCUSDT",
            app_id=34,
            paper=True,
            qty=Decimal("0.05"),
            signal=1.0,
            intended_side="BUY",
            position_qty=0.0,
            data_as_of="2024-06-01",
            notional=notional,
            bar_source="price_bar:bybit",
        )

    def test_notional_present(self):
        r = self._report(notional=20000.0)
        assert r.notional == 20000.0

    def test_notional_none(self):
        r = self._report()
        assert r.notional is None

    def test_notional_in_json(self):
        r = self._report(notional=1000.0)
        data = r.model_dump()
        assert data["notional"] == 1000.0
