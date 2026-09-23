"""Unit tests for :mod:`quant.trade.schedule_policy`."""

import pytest

from quant.trade.errors import TradeValidationError
from quant.trade.schedule_policy import (
    fitted_interval_id,
    require_fitted_interval,
)
from tests.conftest import TM_INTERVAL_ROWS, StubRefData


class TestFittedIntervalId:
    def test_reads_the_interval_from_the_strategy_config(self):
        assert fitted_interval_id({"tm_interval_id": 2}) == 2

    def test_a_daily_strategy_resolves_to_daily(self):
        assert fitted_interval_id({"tm_interval_id": 1}) == 1

    def test_a_config_without_the_field_is_refused(self):
        """No fallback: a strategy that names no interval is a data error."""
        with pytest.raises(TradeValidationError, match="tm_interval_id"):
            fitted_interval_id({})

    def test_a_missing_config_is_refused(self):
        with pytest.raises(TradeValidationError, match="tm_interval_id"):
            fitted_interval_id(None)


class TestRequireFittedInterval:
    def test_allows_the_fitted_cadence(self, refdata_stub):
        require_fitted_interval(2, fitted_interval_id=2, refdata=refdata_stub)

    def test_allows_manual(self, refdata_stub):
        """Manual has no cadence to conflict with — it prices off the fitted bars."""
        require_fitted_interval(None, fitted_interval_id=2, refdata=refdata_stub)

    def test_refuses_any_other_cadence(self, refdata_stub):
        with pytest.raises(TradeValidationError) as exc:
            require_fitted_interval(2, fitted_interval_id=1, refdata=refdata_stub)
        assert exc.value.status_code == 400

    def test_refuses_daily_for_an_hourly_strategy(self, refdata_stub):
        """The bug this fixes: an hourly strategy must not be forced onto daily."""
        with pytest.raises(TradeValidationError):
            require_fitted_interval(1, fitted_interval_id=2, refdata=refdata_stub)

    def test_names_both_cadences_so_the_message_is_actionable(self, refdata_stub):
        with pytest.raises(TradeValidationError) as exc:
            require_fitted_interval(2, fitted_interval_id=1, refdata=refdata_stub)
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
