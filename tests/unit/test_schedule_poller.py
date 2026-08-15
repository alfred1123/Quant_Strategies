"""Unit tests for :mod:`quant.trade.scheduler.poller` — mocked runner, no DB.

Coroutines are driven with ``asyncio.run`` rather than an async test plugin,
which the project does not depend on.
"""

import asyncio
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from quant.trade.scheduler.poller import SchedulePoller
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


def _poller(runner, refdata, **kwargs):
    kwargs.setdefault("poll_interval_s", 0.01)
    return SchedulePoller(runner, refdata, **kwargs)


class TestPollOnce:
    def test_sweeps_every_interval(self, runner, refdata):
        reports = asyncio.run(_poller(runner, refdata).poll_once())

        assert [c.args[0] for c in runner.run_interval.call_args_list] == [1, 2]
        assert len(reports) == 2

    def test_a_failing_interval_does_not_stop_the_others(self, runner, refdata):
        runner.run_interval.side_effect = [RuntimeError("db down"), _report(2)]

        reports = asyncio.run(_poller(runner, refdata).poll_once())

        assert len(reports) == 1
        assert reports[0].tm_interval_id == 2

    def test_no_intervals_is_not_an_error(self, runner, refdata):
        refdata.interval_ids.return_value = []

        assert asyncio.run(_poller(runner, refdata).poll_once()) == []


class TestDrain:
    def test_repeats_until_a_pass_moves_nothing(self, runner, refdata):
        """A three-interval backlog needs three passes — one slot each."""
        refdata.interval_ids.return_value = [1]
        runner.run_interval.side_effect = [
            _report(1, TickOutcome.APPLIED),
            _report(1, TickOutcome.APPLIED),
            _report(1, TickOutcome.APPLIED),
            _report(1),
        ]

        advanced = asyncio.run(_poller(runner, refdata).drain())

        assert advanced == 3
        assert runner.run_interval.call_count == 4

    def test_nothing_due_returns_immediately(self, runner, refdata):
        refdata.interval_ids.return_value = [1]
        runner.run_interval.return_value = _report(1)

        assert asyncio.run(_poller(runner, refdata).drain()) == 0
        assert runner.run_interval.call_count == 1

    def test_a_retrying_row_does_not_keep_the_drain_spinning(self, runner, refdata):
        """RETRYING leaves the row due; spending its budget here would burn all
        three attempts in a tight loop instead of across poll cycles."""
        refdata.interval_ids.return_value = [1]
        runner.run_interval.return_value = _report(1, TickOutcome.RETRYING)

        assert asyncio.run(_poller(runner, refdata).drain()) == 0
        assert runner.run_interval.call_count == 1

    def test_abandoned_counts_as_progress(self, runner, refdata):
        refdata.interval_ids.return_value = [1]
        runner.run_interval.side_effect = [
            _report(1, TickOutcome.ABANDONED),
            _report(1),
        ]

        assert asyncio.run(_poller(runner, refdata).drain()) == 1

    def test_stuck_aborts_the_drain_rather_than_re_trading(self, runner, refdata):
        """STUCK means the row applied but stayed due — another pass would place
        a second order seconds later."""
        refdata.interval_ids.return_value = [1]
        runner.run_interval.return_value = _report(
            1, TickOutcome.APPLIED, TickOutcome.STUCK
        )

        advanced = asyncio.run(_poller(runner, refdata).drain())

        assert advanced == 0
        assert runner.run_interval.call_count == 1

    def test_pass_ceiling_bounds_an_endless_backlog(self, runner, refdata):
        refdata.interval_ids.return_value = [1]
        runner.run_interval.return_value = _report(1, TickOutcome.APPLIED)

        advanced = asyncio.run(
            _poller(runner, refdata, max_drain_passes=5).drain()
        )

        assert advanced == 5
        assert runner.run_interval.call_count == 5


class TestRunLoop:
    def test_drains_before_the_first_timed_pass(self, runner, refdata):
        """Boot catch-up must not wait out a poll interval."""
        refdata.interval_ids.return_value = [1]
        poller = _poller(runner, refdata, poll_interval_s=30)
        runner.run_interval.side_effect = [
            _report(1, TickOutcome.APPLIED),
            _report(1),
        ]

        async def drive():
            task = asyncio.create_task(poller.run())
            await asyncio.sleep(0.05)  # far shorter than poll_interval_s
            poller.stop()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(drive())
        assert runner.run_interval.call_count == 2

    def test_keeps_ticking_after_the_drain(self, runner, refdata):
        refdata.interval_ids.return_value = [1]
        runner.run_interval.return_value = _report(1)
        poller = _poller(runner, refdata, poll_interval_s=0.01)

        async def drive():
            task = asyncio.create_task(poller.run())
            await asyncio.sleep(0.08)
            poller.stop()
            await asyncio.wait_for(task, timeout=1)

        asyncio.run(drive())
        assert runner.run_interval.call_count > 1

    def test_stop_ends_the_loop(self, runner, refdata):
        refdata.interval_ids.return_value = [1]
        runner.run_interval.return_value = _report(1)
        poller = _poller(runner, refdata, poll_interval_s=0.01)

        async def drive():
            task = asyncio.create_task(poller.run())
            await asyncio.sleep(0.03)
            poller.stop()
            await asyncio.wait_for(task, timeout=1)
            return task.done()

        assert asyncio.run(drive()) is True
