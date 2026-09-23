"""Unit tests for :mod:`quant.trade.scheduler.tick` — mocked repo, no DB."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from quant.schemas.apply import ApplyReport
from quant.trade.errors import BrokerAuthError, BrokerConnectionError
from quant.trade.models.order import IntendedAction, OrderRejectReason
from quant.trade.scheduler.tick import ScheduleTickRunner, TickOutcome

DUE_AT = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
NEXT_DUE_AT = DUE_AT + timedelta(days=1)


def _due_row(**overrides):
    base = {
        "deployment_id": uuid4(),
        "deployment_vid": 3,
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
        "schedule_tm_interval_id": 1,
        "user_id": "alice",
        "scheduled_ts": DUE_AT,
        "next_scheduled_ts": NEXT_DUE_AT,
    }
    base.update(overrides)
    return base


def _apply_report(
    *,
    position_qty: float,
    order_success: bool | None = None,
    reject_reason: OrderRejectReason | None = None,
) -> ApplyReport:
    """A real ApplyReport, so renaming ``position_qty`` fails here."""
    return ApplyReport(
        deployment_id=uuid4(),
        deployment_vid=3,
        action=IntendedAction.HOLD,
        vendor_symbol="BTCUSDT",
        signal=1.0,
        position_qty=position_qty,
        order_success=order_success,
        reject_reason=reject_reason,
        message=(
            "insufficient funds" if order_success is False else "no order needed (HOLD)"
        ),
    )


@pytest.fixture
def repo():
    return MagicMock()


def _runner(repo, apply_fn=None, **kwargs):
    kwargs.setdefault("retry_backoff_s", 0)
    return ScheduleTickRunner(repo, apply_fn or MagicMock(), **kwargs)


class TestNothingDue:
    def test_empty_report_when_no_rows(self, repo):
        repo.sp_get_missed_due_deployments.return_value = []
        report = _runner(repo).run_interval(1)

        assert report.due == 0
        assert report.advanced == 0
        repo.sp_ins_deployment_schedule_status.assert_not_called()

    def test_reads_the_requested_interval(self, repo):
        repo.sp_get_missed_due_deployments.return_value = []
        _runner(repo).run_interval(2)

        assert repo.sp_get_missed_due_deployments.call_args.kwargs == {
            "tm_interval_id": 2
        }


class TestApplied:
    def test_applies_then_advances(self, repo):
        row = _due_row()
        repo.sp_get_missed_due_deployments.return_value = [row]
        apply_fn = MagicMock()

        report = _runner(repo, apply_fn).run_interval(1)

        apply_fn.assert_called_once_with(row["app_user_id"], row["deployment_id"])
        assert report.results[0].outcome is TickOutcome.APPLIED
        assert report.advanced == 1

    def test_cursor_moves_to_the_next_due_time_from_the_row(self, repo):
        """Advancing off the row's NEXT_SCHEDULED_TS, not off now(), is what
        keeps a late tick on its original phase."""
        row = _due_row()
        repo.sp_get_missed_due_deployments.return_value = [row]

        _runner(repo).run_interval(1)

        kwargs = repo.sp_ins_deployment_schedule_status.call_args.kwargs
        assert kwargs["scheduled_ts"] == NEXT_DUE_AT
        assert kwargs["status"] == "PENDING"

    def test_schedule_id_is_the_deployment_id(self, repo):
        row = _due_row()
        repo.sp_get_missed_due_deployments.return_value = [row]

        _runner(repo).run_interval(1)

        kwargs = repo.sp_ins_deployment_schedule_status.call_args.kwargs
        assert kwargs["deployment_schedule_id"] == row["deployment_id"]
        assert kwargs["deployment_id"] == row["deployment_id"]
        assert kwargs["deployment_vid"] == row["deployment_vid"]

    def test_every_due_row_is_applied(self, repo):
        rows = [_due_row(), _due_row(), _due_row()]
        repo.sp_get_missed_due_deployments.return_value = rows
        apply_fn = MagicMock()

        report = _runner(repo, apply_fn).run_interval(1)

        assert apply_fn.call_count == 3
        assert report.advanced == 3


class TestPositionIsCarriedUp:
    """An unattended tick is the only witness to what it decided against."""

    def test_position_travels_from_the_apply_report(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(return_value=_apply_report(position_qty=-0.002))

        report = _runner(repo, apply_fn).run_interval(1)

        assert report.results[0].position_qty == -0.002

    def test_a_flat_book_reports_zero_not_none(self, repo):
        """0.0 and None mean different things: flat, versus never read."""
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(return_value=_apply_report(position_qty=0.0))

        report = _runner(repo, apply_fn).run_interval(1)

        assert report.results[0].position_qty == 0.0

    def test_no_position_when_the_apply_raised(self, repo):
        """It may never have reached the broker read at all."""
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=RuntimeError("bybit 403"))

        report = _runner(repo, apply_fn).run_interval(1)

        assert report.results[0].position_qty is None

    @pytest.mark.parametrize("returned", [None, object(), "0.01"])
    def test_an_unusable_report_yields_none_rather_than_garbage(self, repo, returned):
        """apply_deployment is injected, so its shape cannot be assumed —
        a wrong position would be worse than a missing one."""
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]

        report = _runner(repo, MagicMock(return_value=returned)).run_interval(1)

        assert report.results[0].position_qty is None
        assert report.results[0].outcome is TickOutcome.APPLIED


class TestRetriesWithinThePass:
    """The next pass is an hour away; the signal would be stale by then."""

    def test_a_transient_failure_is_retried_in_the_same_pass(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=[RuntimeError("venue blip"), None])

        report = _runner(repo, apply_fn, max_attempts=3).run_interval(1)

        assert apply_fn.call_count == 2
        assert report.results[0].outcome is TickOutcome.APPLIED
        assert report.results[0].attempt == 2
        repo.write_deployment.assert_not_called()
        repo.sp_ins_deployment_schedule_status.assert_called_once()

    def test_the_budget_is_spent_in_one_pass_then_it_pauses(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))

        report = _runner(repo, apply_fn, max_attempts=3).run_interval(1)

        assert apply_fn.call_count == 3
        assert report.results[0].outcome is TickOutcome.PAUSED
        assert report.results[0].attempt == 3
        assert report.results[0].error == "boom"
        repo.write_deployment.assert_called_once()
        repo.sp_ins_deployment_schedule_status.assert_not_called()

    def test_attempts_are_spaced_by_the_backoff(self, repo, monkeypatch):
        sleeps = []
        monkeypatch.setattr("quant.trade.scheduler.tick.time.sleep", sleeps.append)
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))

        _runner(repo, apply_fn, max_attempts=3, retry_backoff_s=5.0).run_interval(1)

        # Between attempts only: no wait after the last one, before the pause.
        assert sleeps == [5.0, 5.0]

    def test_a_failing_row_does_not_stop_the_others(self, repo):
        good, bad = _due_row(), _due_row()
        repo.sp_get_missed_due_deployments.return_value = [bad, good]
        apply_fn = MagicMock(side_effect=[RuntimeError("boom"), None])

        report = _runner(repo, apply_fn, max_attempts=1).run_interval(1)

        assert report.results[0].outcome is TickOutcome.PAUSED
        assert report.results[1].outcome is TickOutcome.APPLIED


class TestAttemptBudget:

    def test_exhausted_retries_disable_and_pause(self, repo):
        row = _due_row()
        repo.sp_get_missed_due_deployments.return_value = [row]
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))
        runner = _runner(repo, apply_fn, max_attempts=1)

        report = runner.run_interval(1)

        assert report.results[0].outcome is TickOutcome.PAUSED
        assert report.advanced == 0
        kwargs = repo.write_deployment.call_args.kwargs
        assert kwargs["deployment_id"] == row["deployment_id"]
        assert kwargs["is_enabled_ind"] == "N"
        assert kwargs["deployment_status"] == "PAUSED"
        assert kwargs["schedule_tm_interval_id"] == row["schedule_tm_interval_id"]
        repo.sp_ins_deployment_schedule_status.assert_not_called()

    def test_rejected_order_counts_as_a_failure(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(
            return_value=_apply_report(position_qty=0.0, order_success=False)
        )
        runner = _runner(repo, apply_fn, max_attempts=1)

        report = runner.run_interval(1)

        assert report.results[0].outcome is TickOutcome.PAUSED
        repo.write_deployment.assert_called_once()

    def test_an_unclassified_reject_spends_its_remaining_attempts(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(
            return_value=_apply_report(position_qty=0.0, order_success=False)
        )
        runner = _runner(repo, apply_fn, max_attempts=3)

        report = runner.run_interval(1)

        assert apply_fn.call_count == 3
        assert report.results[0].outcome is TickOutcome.PAUSED
        assert report.results[0].error == "insufficient funds"

    def test_a_size_reject_pauses_without_spending_the_budget(self, repo):
        """Every remaining tick would place the same doomed order."""
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(
            return_value=_apply_report(
                position_qty=0.0,
                order_success=False,
                reject_reason=OrderRejectReason.SIZE_BELOW_MINIMUM,
            )
        )
        runner = _runner(repo, apply_fn, max_attempts=3)

        report = runner.run_interval(1)

        apply_fn.assert_called_once()
        assert report.results[0].outcome is TickOutcome.PAUSED
        assert report.results[0].attempt == 1
        kwargs = repo.write_deployment.call_args.kwargs
        assert kwargs["is_enabled_ind"] == "N"
        assert kwargs["deployment_status"] == "PAUSED"

    def test_a_typed_broker_error_at_connect_pauses_without_spending_the_budget(self, repo):
        """A key that admits none of our egress IPs fails before any order exists."""
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(
            side_effect=BrokerAuthError(
                "Bybit refused this key's source IP on every egress route",
                reason=OrderRejectReason.IP_NOT_ALLOWED,
            )
        )
        runner = _runner(repo, apply_fn, max_attempts=3)

        report = runner.run_interval(1)

        assert report.results[0].outcome is TickOutcome.PAUSED
        assert report.results[0].attempt == 1
        assert repo.write_deployment.call_args.kwargs["deployment_status"] == "PAUSED"

    def test_an_untyped_broker_error_at_connect_is_retried(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=[BrokerConnectionError("proxy down"), None])
        runner = _runner(repo, apply_fn, max_attempts=3)

        report = runner.run_interval(1)

        assert apply_fn.call_count == 2
        assert report.results[0].outcome is TickOutcome.APPLIED

    def test_pause_write_failure_still_advances(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        repo.write_deployment.side_effect = RuntimeError("db down")
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))
        runner = _runner(repo, apply_fn, max_attempts=1)

        report = runner.run_interval(1)

        assert report.results[0].outcome is TickOutcome.ABANDONED
        kwargs = repo.sp_ins_deployment_schedule_status.call_args.kwargs
        assert kwargs["scheduled_ts"] == NEXT_DUE_AT
        assert "pause failed" in report.results[0].error

    def test_each_pass_starts_a_fresh_budget(self, repo):
        """Nothing carries between passes, so a restart cannot change the count."""
        apply_fn = MagicMock(side_effect=[RuntimeError("boom"), None, None])
        runner = _runner(repo, apply_fn, max_attempts=2)
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]

        first = runner.run_interval(1)
        second = runner.run_interval(1)

        assert first.results[0].attempt == 2
        assert second.results[0].attempt == 1


class TestAdvanceFailure:
    def test_applied_but_not_advanced_is_reported_as_stuck(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        repo.sp_ins_deployment_schedule_status.side_effect = RuntimeError("db down")

        report = _runner(repo).run_interval(1)

        assert report.results[0].outcome is TickOutcome.STUCK
        assert report.advanced == 0
