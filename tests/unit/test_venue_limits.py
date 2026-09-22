"""Unit tests for :mod:`quant.trade.venue_limits` — fake Redis, fake exchange."""

import json
from unittest.mock import MagicMock, patch

import redis

from quant.trade.models.market import MarketLimits
from quant.trade.venue_limits import (
    VENUE_LIMITS_VERSION_KEY,
    RedisVenueLimits,
    VenueLimitsPublisher,
)


def _refdata(**ids: int) -> MagicMock:
    refdata = MagicMock()
    refdata.resolve_app_id.side_effect = lambda name: ids.get(name)
    return refdata


def _publisher(redis_client, refdata) -> VenueLimitsPublisher:
    with patch("quant.trade.venue_limits._redis", return_value=redis_client):
        return VenueLimitsPublisher("redis://stub", refdata=refdata)


def _reader(redis_client) -> RedisVenueLimits:
    with patch("quant.trade.venue_limits._redis", return_value=redis_client):
        return RedisVenueLimits("redis://stub")


class FakeRedis:
    """Enough of redis-py for a set/get/incr snapshot, with a pipeline."""

    def __init__(self, **values: str) -> None:
        self.store: dict[str, str] = dict(values)

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


class TestVenueLimitsPublisher:
    def test_one_snapshot_per_broker_app(self):
        fake = FakeRedis()
        limits = {"BTCUSDT": MarketLimits("BTCUSDT", min_qty=0.001, min_notional=5.0)}
        publisher = _publisher(fake, _refdata(bybit=34, binance=35))

        with patch.object(
            VenueLimitsPublisher, "_fetch", return_value=limits
        ) as mock_fetch:
            published = publisher.publish_all()

        assert published == 2
        assert mock_fetch.call_count == 2
        assert json.loads(fake.store["venue_limits:34"]) == {
            "BTCUSDT": {"min_qty": 0.001, "min_notional": 5.0}
        }
        # Readers drop their local copy off this stamp.
        assert fake.store[VENUE_LIMITS_VERSION_KEY] == "1"

    def test_one_unreachable_venue_does_not_cost_the_other_its_snapshot(self):
        fake = FakeRedis()
        publisher = _publisher(fake, _refdata(bybit=34, binance=35))

        def fetch(preset):
            if preset.exchange_id == "bybit":
                raise RuntimeError("venue down")
            return {"BTCUSDT": MarketLimits("BTCUSDT", min_qty=0.002)}

        with patch.object(VenueLimitsPublisher, "_fetch", side_effect=fetch):
            published = publisher.publish_all()

        assert published == 1
        assert "venue_limits:34" not in fake.store
        assert "venue_limits:35" in fake.store

    def test_nothing_is_written_when_every_venue_fails(self):
        """A total outage must leave the previous snapshot in place."""
        fake = FakeRedis(**{"venue_limits:34": json.dumps({"BTCUSDT": {}})})
        publisher = _publisher(fake, _refdata(bybit=34))

        with patch.object(
            VenueLimitsPublisher, "_fetch", side_effect=RuntimeError("down")
        ):
            assert publisher.publish_all() == 0

        assert VENUE_LIMITS_VERSION_KEY not in fake.store
        assert fake.store["venue_limits:34"] == json.dumps({"BTCUSDT": {}})


class TestRedisVenueLimits:
    def test_reads_the_rules_for_one_symbol(self):
        fake = FakeRedis(
            **{
                "venue_limits:34": json.dumps(
                    {"BTCUSDT": {"min_qty": 0.001, "min_notional": 5.0}}
                ),
                VENUE_LIMITS_VERSION_KEY: "7",
            }
        )

        limits = _reader(fake).get(34, "BTCUSDT")

        assert limits == MarketLimits("BTCUSDT", min_qty=0.001, min_notional=5.0)

    def test_an_unknown_symbol_enforces_nothing(self):
        fake = FakeRedis(**{"venue_limits:34": json.dumps({"BTCUSDT": {}})})
        assert _reader(fake).get(34, "ETHUSDT") == MarketLimits("ETHUSDT")

    def test_an_uncached_app_enforces_nothing(self):
        assert _reader(FakeRedis()).get(99, "BTCUSDT") == MarketLimits("BTCUSDT")

    def test_an_unreachable_cache_enforces_nothing(self):
        """An edit must not be blocked by a Redis outage."""
        fake = FakeRedis()
        fake.get = MagicMock(side_effect=redis.RedisError("down"))

        assert _reader(fake).get(34, "BTCUSDT") == MarketLimits("BTCUSDT")

    def test_a_version_bump_drops_the_local_copy(self):
        fake = FakeRedis(
            **{
                "venue_limits:34": json.dumps({"BTCUSDT": {"min_qty": 0.001}}),
                VENUE_LIMITS_VERSION_KEY: "1",
            }
        )
        reader = _reader(fake)
        assert reader.get(34, "BTCUSDT").min_qty == 0.001

        fake.store["venue_limits:34"] = json.dumps({"BTCUSDT": {"min_qty": 0.01}})
        fake.store[VENUE_LIMITS_VERSION_KEY] = "2"

        assert reader.get(34, "BTCUSDT").min_qty == 0.01

    def test_an_unreadable_snapshot_enforces_nothing(self):
        fake = FakeRedis(**{"venue_limits:34": "not json"})
        assert _reader(fake).get(34, "BTCUSDT") == MarketLimits("BTCUSDT")
