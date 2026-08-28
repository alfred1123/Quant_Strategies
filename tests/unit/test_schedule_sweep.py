"""Unit tests for :mod:`quant.trade.scheduler.sweep` — mocked runner, no DB."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.trade.scheduler.sweep import DEFAULT_SETTLE_S, ScheduleSweeper
from quant.trade.scheduler.tick import TickOutcome, TickReport, TickResult


def _result(outcome=TickOutcome.APPLIED):
    return TickResult(deployment_id=uuid4(), outcome=outcome, attempt=1)


def _report(interval_id=1, *outcomes):
    return TickReport(
        tm_interval_id=interval_id,
        results=[_result(o) for o in outcomes],
    )


@pytest.fixture
def refdata():
    cache = MagicMock()
    cache.interval_ids.return_value = [1, 2]
    return cache


@pytest.fixture
def runner():
    instance = MagicMock()
    instance.run_interval.return_value = _report()
    return instance


class TestSweep:
    def test_ticks_every_interval(self, runner, refdata):
        reports = ScheduleSweeper(runner, refdata).sweep()

        assert [c.args[0] for c in runner.run_interval.call_args_list] == [1, 2]
        assert len(reports) == 2

    def test_a_failing_interval_does_not_stop_the_others(self, runner, refdata):
        """One broken interval must not stop the rest from trading."""
        runner.run_interval.side_effect = [RuntimeError("db down"), _report(2)]

        reports = ScheduleSweeper(runner, refdata).sweep()

        assert len(reports) == 1
        assert reports[0].tm_interval_id == 2

    def test_no_intervals_is_not_an_error(self, runner, refdata):
        refdata.interval_ids.return_value = []

        assert ScheduleSweeper(runner, refdata).sweep() == []

    def test_reads_the_interval_list_every_pass(self, runner, refdata):
        """A new interval in REFDATA must not need a restart to be swept."""
        sweeper = ScheduleSweeper(runner, refdata)
        sweeper.sweep()
        refdata.interval_ids.return_value = [1, 2, 3]
        sweeper.sweep()

        assert [c.args[0] for c in runner.run_interval.call_args_list] == [1, 2, 1, 2, 3]


class TestSettle:
    def test_waits_before_reading_what_is_due(self, runner, refdata):
        """Fired on the boundary, a tick must not ask "is it time?" too early."""
        with patch("quant.trade.scheduler.sweep.time.sleep") as mock_sleep:
            ScheduleSweeper(runner, refdata, settle_s=10.0).sweep()

        mock_sleep.assert_called_once_with(10.0)

    def test_settles_before_the_first_tick_not_between_them(self, runner, refdata):
        calls = []
        with patch(
            "quant.trade.scheduler.sweep.time.sleep",
            side_effect=lambda s: calls.append(("sleep", s)),
        ):
            runner.run_interval.side_effect = lambda i: (
                calls.append(("tick", i)) or _report(i)
            )
            ScheduleSweeper(runner, refdata, settle_s=10.0).sweep()

        assert calls == [("sleep", 10.0), ("tick", 1), ("tick", 2)]

    def test_no_wait_by_default(self, runner, refdata):
        """The dev poller wakes on its own cadence — no boundary to clear."""
        with patch("quant.trade.scheduler.sweep.time.sleep") as mock_sleep:
            ScheduleSweeper(runner, refdata).sweep()

        mock_sleep.assert_not_called()

    def test_the_declared_default_clears_the_boundary(self):
        assert DEFAULT_SETTLE_S == 10.0


class TestHasStuck:
    def test_true_when_a_deployment_applied_without_advancing(self):
        reports = [_report(1, TickOutcome.APPLIED, TickOutcome.STUCK)]
        assert ScheduleSweeper.has_stuck(reports) is True

    def test_false_for_ordinary_outcomes(self):
        reports = [
            _report(1, TickOutcome.APPLIED),
            _report(2, TickOutcome.RETRYING, TickOutcome.ABANDONED),
        ]
        assert ScheduleSweeper.has_stuck(reports) is False

    def test_false_when_nothing_was_due(self):
        assert ScheduleSweeper.has_stuck([_report(1)]) is False
