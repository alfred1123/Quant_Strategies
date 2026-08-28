"""Unit tests for the scheduler tick endpoint — mocked sweeper, no app boot."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from quant.api.scheduler.router import _get_sweeper, run_schedule_tick
from quant.trade.scheduler.tick import TickOutcome, TickReport, TickResult


def _result(outcome=TickOutcome.APPLIED, error=None, position_qty=None):
    return TickResult(
        deployment_id=uuid4(),
        outcome=outcome,
        attempt=1,
        error=error,
        position_qty=position_qty,
    )


def _sweeper(*reports):
    sweeper = MagicMock()
    sweeper.sweep.return_value = list(reports)
    return sweeper


class TestResponse:
    def test_nothing_due_reports_zeros(self):
        body = run_schedule_tick(caller="service", sweeper=_sweeper())

        assert body["intervals"] == 0
        assert body["due"] == 0
        assert body["advanced"] == 0
        assert body["outcomes"] == {}

    def test_counts_across_every_interval(self):
        body = run_schedule_tick(
            caller="service",
            sweeper=_sweeper(
                TickReport(tm_interval_id=1, results=[_result()]),
                TickReport(
                    tm_interval_id=2,
                    results=[_result(), _result(TickOutcome.RETRYING)],
                ),
            ),
        )

        assert body["intervals"] == 2
        assert body["due"] == 3
        # RETRYING left the row due, so only the two applies advanced.
        assert body["advanced"] == 2
        assert body["outcomes"] == {TickOutcome.APPLIED: 2, TickOutcome.RETRYING: 1}

    def test_carries_the_failure_reason_per_deployment(self):
        """The Lambda logs this body; a silent failure would be invisible."""
        body = run_schedule_tick(
            caller="service",
            sweeper=_sweeper(
                TickReport(
                    tm_interval_id=1,
                    results=[_result(TickOutcome.RETRYING, error="bybit 403")],
                )
            ),
        )

        deployment = body["results"][0]["deployments"][0]
        assert deployment["error"] == "bybit 403"
        assert deployment["outcome"] == TickOutcome.RETRYING
        assert isinstance(deployment["deployment_id"], str)

    def test_a_failing_deployment_still_returns_a_body(self):
        """Reporting a pass as failed would mark the whole sweep broken."""
        body = run_schedule_tick(
            caller="service",
            sweeper=_sweeper(
                TickReport(
                    tm_interval_id=1,
                    results=[
                        _result(TickOutcome.ABANDONED, error="no credential"),
                        _result(),
                    ],
                )
            ),
        )

        assert body["due"] == 2
        assert body["outcomes"][TickOutcome.ABANDONED] == 1


class TestPositionInTheResponse:
    """The Lambda log is the only witness to an unattended tick's reasoning."""

    def test_reports_the_position_behind_the_decision(self):
        body = run_schedule_tick(
            caller="service",
            sweeper=_sweeper(
                TickReport(tm_interval_id=1, results=[_result(position_qty=-0.002)])
            ),
        )

        assert body["results"][0]["deployments"][0]["position_qty"] == -0.002

    def test_a_flat_book_is_reported_as_zero(self):
        """Distinguishes a HOLD on a flat book from a position never read."""
        body = run_schedule_tick(
            caller="service",
            sweeper=_sweeper(
                TickReport(tm_interval_id=1, results=[_result(position_qty=0.0)])
            ),
        )

        assert body["results"][0]["deployments"][0]["position_qty"] == 0.0

    def test_unknown_position_is_present_as_null(self):
        """The key is always there, so a reader never has to guess."""
        body = run_schedule_tick(
            caller="service",
            sweeper=_sweeper(TickReport(tm_interval_id=1, results=[_result()])),
        )

        deployment = body["results"][0]["deployments"][0]
        assert "position_qty" in deployment
        assert deployment["position_qty"] is None


class TestSweeperIsApplicationScoped:
    def test_uses_the_instance_built_at_startup(self):
        """Rebuilding per request would reset the tick's attempt budget."""
        sweeper = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(schedule_sweeper=sweeper))
        )

        assert _get_sweeper(request) is sweeper
