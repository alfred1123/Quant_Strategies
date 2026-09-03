"""Unit tests for :mod:`quant.shared.intervals`."""

from datetime import UTC, datetime, timedelta

import pytest

from quant.shared.intervals import (
    as_utc,
    bar_starts,
    ccxt_timeframe,
    floor_to_period,
    last_closed_bar,
    next_run_at,
    parse_period,
)

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


class TestParsePeriod:
    def test_timedelta_passes_through(self):
        assert parse_period(DAY) == DAY

    @pytest.mark.parametrize(
        "text,expected",
        [
            # str(timedelta) — what the REFDATA publisher's json.dumps(default=str)
            # leaves behind for a Postgres INTERVAL.
            ("1 day, 0:00:00", DAY),
            ("7 days, 0:00:00", timedelta(days=7)),
            ("1:00:00", HOUR),
            ("0:15:00", timedelta(minutes=15)),
            ("4:00:00", timedelta(hours=4)),
            ("0:00:30.500000", timedelta(seconds=30, microseconds=500000)),
        ],
    )
    def test_stringified_timedelta(self, text, expected):
        assert parse_period(text) == expected

    def test_rejects_unparseable_text(self):
        with pytest.raises(ValueError, match="unrecognised PERIOD_LENGTH"):
            parse_period("every hour")

    def test_rejects_non_positive(self):
        with pytest.raises(ValueError, match="must be positive"):
            parse_period(timedelta(0))

    def test_rejects_wrong_type(self):
        with pytest.raises(TypeError):
            parse_period(3600)


class TestBoundaries:
    def test_hourly_floors_to_top_of_hour(self):
        ts = datetime(2026, 8, 1, 10, 37, 12, tzinfo=UTC)
        assert floor_to_period(ts, HOUR) == datetime(2026, 8, 1, 10, 0, tzinfo=UTC)

    def test_daily_floors_to_midnight_utc(self):
        ts = datetime(2026, 8, 1, 10, 37, 12, tzinfo=UTC)
        assert floor_to_period(ts, DAY) == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)

    def test_exact_boundary_is_its_own_floor(self):
        ts = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        assert floor_to_period(ts, HOUR) == ts

    def test_naive_timestamp_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            floor_to_period(datetime(2026, 8, 1, 10, 0), HOUR)

    def test_as_utc_treats_naive_as_utc(self):
        naive = datetime(2020, 3, 25)
        assert as_utc(naive) == datetime(2020, 3, 25, tzinfo=UTC)

    def test_as_utc_converts_other_zones(self):
        from datetime import timezone
        eastern = datetime(2020, 3, 25, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
        assert as_utc(eastern) == datetime(2020, 3, 25, 4, 0, tzinfo=UTC)

    def test_last_closed_bar_excludes_the_forming_one(self):
        """The bar covering `now` is still open, so 10:00 is not usable at 10:37."""
        now = datetime(2026, 8, 1, 10, 37, tzinfo=UTC)
        assert last_closed_bar(now, HOUR) == datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

    def test_last_closed_bar_on_the_boundary(self):
        now = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
        assert last_closed_bar(now, HOUR) == datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

    def test_next_run_is_strictly_after(self):
        assert next_run_at(datetime(2026, 8, 1, 10, 0, tzinfo=UTC), HOUR) == datetime(
            2026, 8, 1, 11, 0, tzinfo=UTC
        )
        assert next_run_at(datetime(2026, 8, 1, 10, 37, tzinfo=UTC), HOUR) == datetime(
            2026, 8, 1, 11, 0, tzinfo=UTC
        )


class TestBarStarts:
    def test_lists_every_boundary_inclusive(self):
        start = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        end = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        assert bar_starts(start, end, HOUR) == [
            datetime(2026, 8, 1, h, 0, tzinfo=UTC) for h in (9, 10, 11, 12)
        ]

    def test_unaligned_start_advances_to_next_boundary(self):
        start = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
        end = datetime(2026, 8, 1, 11, 0, tzinfo=UTC)
        assert bar_starts(start, end, HOUR) == [
            datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 1, 11, 0, tzinfo=UTC),
        ]

    def test_empty_when_end_precedes_start(self):
        start = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        end = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        assert bar_starts(start, end, HOUR) == []


class TestCcxtTimeframe:
    @pytest.mark.parametrize(
        "period,expected",
        [
            (timedelta(minutes=1), "1m"),
            (timedelta(minutes=15), "15m"),
            (HOUR, "1h"),
            (timedelta(hours=4), "4h"),
            (DAY, "1d"),
            (timedelta(days=7), "1w"),
        ],
    )
    def test_renders_ccxt_string(self, period, expected):
        assert ccxt_timeframe(period) == expected

    def test_rejects_sub_minute(self):
        with pytest.raises(ValueError, match="no ccxt timeframe"):
            ccxt_timeframe(timedelta(seconds=30))
