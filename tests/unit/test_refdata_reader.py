"""Unit tests for :mod:`quant.refdata.reader` resolvers."""

from datetime import timedelta

import pytest

from quant.refdata.reader import RedisRefData


def _reader(rows):
    """A reader with its Redis-backed ``get`` stubbed out."""
    instance = RedisRefData.__new__(RedisRefData)
    instance.get = lambda table: rows if table == "tm_interval" else []
    return instance


class TestGetIntervalPeriod:
    def test_parses_the_stringified_interval_from_redis(self):
        """The publisher's json.dumps(default=str) leaves PERIOD_LENGTH as text."""
        reader = _reader(
            [
                {"tm_interval_id": 1, "name": "DAILY", "period_length": "1 day, 0:00:00"},
                {"tm_interval_id": 2, "name": "1H", "period_length": "1:00:00"},
            ]
        )
        assert reader.get_interval_period(1) == timedelta(days=1)
        assert reader.get_interval_period(2) == timedelta(hours=1)

    def test_accepts_a_raw_timedelta(self):
        """A row read straight from psycopg carries a timedelta, not text."""
        reader = _reader([{"tm_interval_id": 2, "period_length": timedelta(hours=1)}])
        assert reader.get_interval_period(2) == timedelta(hours=1)

    def test_string_ids_still_match(self):
        reader = _reader([{"tm_interval_id": "2", "period_length": "1:00:00"}])
        assert reader.get_interval_period(2) == timedelta(hours=1)

    def test_unknown_interval_raises(self):
        reader = _reader([{"tm_interval_id": 1, "period_length": "1 day, 0:00:00"}])
        with pytest.raises(RuntimeError, match="TM_INTERVAL_ID=99"):
            reader.get_interval_period(99)


class TestResolveIntervalId:
    """The inverse lookup — period → id, ids never hardcoded."""

    def test_resolves_the_id_for_a_period(self):
        reader = _reader(
            [
                {"tm_interval_id": 1, "name": "DAILY", "period_length": "1 day, 0:00:00"},
                {"tm_interval_id": 2, "name": "1H", "period_length": "1:00:00"},
            ]
        )
        assert reader.resolve_interval_id(timedelta(days=1)) == 1
        assert reader.resolve_interval_id(timedelta(hours=1)) == 2

    def test_unknown_period_raises(self):
        reader = _reader([{"tm_interval_id": 1, "period_length": "1 day, 0:00:00"}])
        with pytest.raises(RuntimeError, match="no row with PERIOD_LENGTH"):
            reader.resolve_interval_id(timedelta(minutes=5))


class TestIntervalIds:
    """The set the scheduler sweeps."""

    def test_ordered_shortest_period_first(self):
        reader = _reader(
            [
                {"tm_interval_id": 1, "period_length": "1 day, 0:00:00"},
                {"tm_interval_id": 3, "period_length": "0:05:00"},
                {"tm_interval_id": 2, "period_length": "1:00:00"},
            ]
        )
        assert reader.interval_ids() == [3, 2, 1]

    def test_ids_come_back_as_ints(self):
        reader = _reader([{"tm_interval_id": "7", "period_length": "1:00:00"}])
        assert reader.interval_ids() == [7]
