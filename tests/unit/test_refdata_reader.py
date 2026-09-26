"""Unit tests for :mod:`quant.refdata.reader` resolvers."""

from datetime import timedelta

import pytest

from quant.refdata.reader import RedisRefData


def _timing_reader(calendar_rows, timing_rows):
    instance = RedisRefData.__new__(RedisRefData)

    def get(table):
        if table == "market_calendar":
            return calendar_rows
        raise AssertionError(f"unexpected table {table!r}")

    def get_config(table):
        if table == "app_apply_timing":
            return timing_rows
        raise AssertionError(f"unexpected CONFIG table {table!r}")

    instance.get = get
    instance.get_config = get_config
    return instance


class TestGetMarketCalendar:
    def test_default_crypto_calendar(self):
        reader = _timing_reader(
            [
                {
                    "listing_exchange": "",
                    "bar_timezone": "UTC",
                    "market_open_time": None,
                    "market_close_time": None,
                }
            ],
            [],
        )
        cal = reader.get_market_calendar()
        assert cal["listing_exchange"] == ""
        assert cal["bar_timezone"] == "UTC"

    def test_listing_venue_calendar(self):
        reader = _timing_reader(
            [
                {
                    "listing_exchange": "HKEX",
                    "bar_timezone": "Asia/Hong_Kong",
                    "market_open_time": "09:30:00",
                    "market_close_time": "16:00:00",
                }
            ],
            [],
        )
        cal = reader.get_market_calendar(listing_exchange="HKEX")
        assert cal["bar_timezone"] == "Asia/Hong_Kong"

    def test_missing_row_raises(self):
        reader = _timing_reader([], [])
        with pytest.raises(RuntimeError, match="MARKET_CALENDAR missing LISTING_EXCHANGE='HKEX'"):
            reader.get_market_calendar(listing_exchange="HKEX")


class TestGetExecuteOffset:
    def test_resolves_offset_from_apply_timing(self):
        reader = _timing_reader(
            [],
            [{"app_id": 34, "tm_interval_id": 1, "execute_offset": "0:05:00"}],
        )
        assert reader.get_execute_offset(34, 1) == timedelta(minutes=5)

    def test_missing_row_raises(self):
        reader = _timing_reader([], [])
        with pytest.raises(RuntimeError, match="APP_APPLY_TIMING missing APP_ID=99"):
            reader.get_execute_offset(99, 1)


class TestGetApplyTiming:
    def test_merges_listing_calendar_and_broker_offset(self):
        reader = _timing_reader(
            [
                {
                    "listing_exchange": "",
                    "bar_timezone": "UTC",
                    "market_open_time": None,
                    "market_close_time": None,
                }
            ],
            [{"app_id": 34, "tm_interval_id": 1, "execute_offset": "0:05:00"}],
        )
        timing = reader.get_apply_timing(34, 1)
        assert timing["execute_offset"] == timedelta(minutes=5)
        assert timing["bar_timezone"] == "UTC"


def _reader(rows):
    instance = RedisRefData.__new__(RedisRefData)
    instance.get = lambda table: rows if table == "tm_interval" else []
    return instance


class TestGetIntervalPeriod:
    def test_parses_the_stringified_interval_from_redis(self):
        reader = _reader(
            [
                {"tm_interval_id": 1, "name": "DAILY", "period_length": "1 day, 0:00:00"},
                {"tm_interval_id": 2, "name": "1H", "period_length": "1:00:00"},
            ]
        )
        assert reader.get_interval_period(1) == timedelta(days=1)
        assert reader.get_interval_period(2) == timedelta(hours=1)

    def test_accepts_a_raw_timedelta(self):
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


class _FakeRedis:
    def __init__(self, **values: str) -> None:
        self.store: dict[str, str] = dict(values)
        self.deleted: list[str] = []

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def incr(self, key: str) -> None:
        self.store[key] = str(int(self.store.get(key, 0)) + 1)

    def pipeline(self, transaction: bool = True):
        return self

    def execute(self) -> None:
        return None

    def publish(self, channel: str, message: str) -> None:
        return None

    def scan_iter(self, match: str):
        prefix = match.removesuffix("*")
        return [key for key in self.store if key.startswith(prefix)]

    def delete(self, *keys: str) -> None:
        self.deleted.extend(keys)
        for key in keys:
            self.store.pop(key, None)


class TestSchemaCaches:
    def test_get_reads_the_schema_prefix(self):
        fake = _FakeRedis(**{
            "refdata:version": "3",
            "refdata:indicator": '[{"method_name": "sma"}]',
            "config:version": "1",
            "config:promotion_metric": '[{"name": "sharpe_gate"}]',
        })
        reader = RedisRefData.__new__(RedisRefData)
        reader._r = fake
        reader._store = {}
        reader._versions = {}
        assert reader.get("indicator") == [{"method_name": "sma"}]
        assert reader.get_config("promotion_metric") == [{"name": "sharpe_gate"}]

    def test_a_config_bump_does_not_drop_refdata_rows(self):
        fake = _FakeRedis(**{
            "refdata:version": "1",
            "refdata:indicator": '[{"method_name": "sma"}]',
            "config:version": "1",
            "config:promotion_metric": '[{"name": "sharpe_gate"}]',
        })
        reader = RedisRefData.__new__(RedisRefData)
        reader._r = fake
        reader._store = {}
        reader._versions = {}
        reader.get("indicator")
        reader.get_config("promotion_metric")
        fake.store["config:version"] = "2"
        fake.store["config:promotion_metric"] = '[{"name": "oos_sharpe_gate"}]'
        assert reader.get("indicator") == [{"method_name": "sma"}]
        assert reader.get_config("promotion_metric") == [{"name": "oos_sharpe_gate"}]

    def test_a_catalog_read_does_not_use_the_policy_snapshot(self):
        fake = _FakeRedis(**{
            "refdata:version": "1",
            "config:version": "1",
            "config:promotion_metric": '[{"name": "sharpe_gate"}]',
            "refdata:indicator": '[{"method_name": "sma"}]',
        })
        reader = RedisRefData.__new__(RedisRefData)
        reader._r = fake
        reader._store = {}
        reader._versions = {}
        with pytest.raises(ValueError, match="refdata.promotion_metric"):
            reader.get("promotion_metric")
        with pytest.raises(ValueError, match="config.indicator"):
            reader.get_config("indicator")

    def test_publish_keeps_each_prefix_to_its_own_tables(self):
        from quant.refdata.publisher import RefDataPublisher

        fake = _FakeRedis(**{
            "refdata:promotion_metric": "[]",
            "config:indicator": "[]",
        })
        publisher = RefDataPublisher.__new__(RefDataPublisher)
        publisher._redis = fake
        publisher._discover_tables = lambda schema: {
            "refdata": ["indicator"],
            "config": ["promotion_metric"],
        }[schema]
        calls: list[tuple[str, str]] = []

        def fetch(schema: str, table: str) -> list[dict]:
            calls.append((schema, table))
            return [{"name": table}]

        publisher._fetch_enum = fetch

        assert publisher.publish_all() == 2
        assert fake.store["refdata:indicator"] == '[{"name": "indicator"}]'
        assert fake.store["config:promotion_metric"] == '[{"name": "promotion_metric"}]'
        assert fake.store["refdata:version"] == "1"
        assert fake.store["config:version"] == "1"
        assert "refdata:promotion_metric" not in fake.store
        assert "config:indicator" not in fake.store
        assert calls == [
            ("refdata", "indicator"),
            ("config", "promotion_metric"),
        ]
