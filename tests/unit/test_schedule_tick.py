"""Unit tests for :mod:`quant.trade.scheduler.tick` — mocked repo, no DB."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

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


@pytest.fixture
def repo():
    return MagicMock()


def _runner(repo, apply_fn=None, **kwargs):
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


class TestFailureKeepsTheRowDue:
    def test_first_failure_does_not_advance(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=RuntimeError("stale bars"))

        report = _runner(repo, apply_fn).run_interval(1)

        repo.sp_ins_deployment_schedule_status.assert_not_called()
        assert report.results[0].outcome is TickOutcome.RETRYING
        assert report.advanced == 0

    def test_failure_records_the_error(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=RuntimeError("stale bars"))

        report = _runner(repo, apply_fn).run_interval(1)

        assert report.results[0].error == "stale bars"

    def test_a_failing_row_does_not_stop_the_others(self, repo):
        good, bad = _due_row(), _due_row()
        repo.sp_get_missed_due_deployments.return_value = [bad, good]
        apply_fn = MagicMock(side_effect=[RuntimeError("boom"), None])

        report = _runner(repo, apply_fn).run_interval(1)

        assert report.results[0].outcome is TickOutcome.RETRYING
        assert report.results[1].outcome is TickOutcome.APPLIED


class TestAttemptBudget:
    def test_budget_is_spent_across_passes_then_the_interval_is_skipped(self, repo):
        row = _due_row()
        repo.sp_get_missed_due_deployments.return_value = [row]
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))
        runner = _runner(repo, apply_fn, max_attempts=3)

        outcomes = [runner.run_interval(1).results[0].outcome for _ in range(3)]

        assert outcomes == [
            TickOutcome.RETRYING,
            TickOutcome.RETRYING,
            TickOutcome.ABANDONED,
        ]
        repo.sp_ins_deployment_schedule_status.assert_called_once()

    def test_abandoning_still_advances_so_the_schedule_is_not_wedged(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))
        runner = _runner(repo, apply_fn, max_attempts=1)

        report = runner.run_interval(1)

        assert report.results[0].outcome is TickOutcome.ABANDONED
        kwargs = repo.sp_ins_deployment_schedule_status.call_args.kwargs
        assert kwargs["scheduled_ts"] == NEXT_DUE_AT

    def test_a_new_due_time_starts_the_budget_over(self, repo):
        """Yesterday's failures must not spend today's attempts."""
        row = _due_row()
        apply_fn = MagicMock(side_effect=RuntimeError("boom"))
        runner = _runner(repo, apply_fn, max_attempts=2)

        repo.sp_get_missed_due_deployments.return_value = [row]
        runner.run_interval(1)

        later = _due_row(
            deployment_id=row["deployment_id"],
            scheduled_ts=NEXT_DUE_AT,
            next_scheduled_ts=NEXT_DUE_AT + timedelta(days=1),
        )
        repo.sp_get_missed_due_deployments.return_value = [later]
        report = runner.run_interval(1)

        assert report.results[0].outcome is TickOutcome.RETRYING
        assert report.results[0].attempt == 1

    def test_success_clears_the_budget(self, repo):
        row = _due_row()
        repo.sp_get_missed_due_deployments.return_value = [row]
        apply_fn = MagicMock(side_effect=[RuntimeError("boom"), None, RuntimeError("boom")])
        runner = _runner(repo, apply_fn, max_attempts=2)

        runner.run_interval(1)
        runner.run_interval(1)
        report = runner.run_interval(1)

        assert report.results[0].attempt == 1
        assert report.results[0].outcome is TickOutcome.RETRYING


class TestAdvanceFailure:
    def test_applied_but_not_advanced_is_reported_as_stuck(self, repo):
        repo.sp_get_missed_due_deployments.return_value = [_due_row()]
        repo.sp_ins_deployment_schedule_status.side_effect = RuntimeError("db down")

        report = _runner(repo).run_interval(1)

        assert report.results[0].outcome is TickOutcome.STUCK
        assert report.advanced == 0
