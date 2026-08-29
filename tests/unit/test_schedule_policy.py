"""Unit tests for :mod:`quant.trade.schedule_policy`."""

from datetime import timedelta

import pytest

from quant.trade.errors import TradeValidationError
from quant.trade.schedule_policy import (
    FITTED_BAR_PERIOD,
    require_fitted_interval,
    schedulable_interval_ids,
)
from tests.conftest import TM_INTERVAL_ROWS, StubRefData


class TestSchedulableIntervalIds:
    def test_resolves_the_fitted_period_through_refdata(self, refdata_stub):
        assert schedulable_interval_ids(refdata_stub) == [1]

    def test_the_fitted_period_is_daily(self):
        assert FITTED_BAR_PERIOD == timedelta(days=1)

    def test_follows_refdata_rather_than_a_hardcoded_id(self):
        """Renumber DAILY in REFDATA and the guard follows it."""
        renumbered = StubRefData(
            [{**TM_INTERVAL_ROWS[0], "tm_interval_id": 7}, TM_INTERVAL_ROWS[1]]
        )
        assert schedulable_interval_ids(renumbered) == [7]


class TestRequireFittedInterval:
    def test_allows_the_fitted_cadence(self, refdata_stub):
        require_fitted_interval(1, refdata=refdata_stub)

    def test_allows_manual(self, refdata_stub):
        """Manual has no cadence to conflict with — it prices off daily bars."""
        require_fitted_interval(None, refdata=refdata_stub)

    def test_refuses_a_finer_cadence(self, refdata_stub):
        with pytest.raises(TradeValidationError) as exc:
            require_fitted_interval(2, refdata=refdata_stub)
        assert exc.value.status_code == 400

    def test_names_both_cadences_so_the_message_is_actionable(self, refdata_stub):
        with pytest.raises(TradeValidationError) as exc:
            require_fitted_interval(2, refdata=refdata_stub)
        assert "Hourly" in str(exc.value)
        assert "Daily" in str(exc.value)


class TestIntervalLabel:
    def test_prefers_display_name(self, refdata_stub):
        assert refdata_stub.interval_label(2) == "Hourly"

    def test_falls_back_to_name_when_the_database_predates_display_name(self):
        rows = [{**r, "display_name": None} for r in TM_INTERVAL_ROWS]
        assert StubRefData(rows).interval_label(2) == "1H"

    def test_falls_back_to_the_id_it_cannot_name(self, refdata_stub):
        """An unknown id must still produce a message, not a second failure."""
        assert refdata_stub.interval_label(99) == "99"
