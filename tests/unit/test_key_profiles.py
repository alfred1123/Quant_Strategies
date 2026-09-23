"""Unit tests for per-key egress routing (brokers.ccxt.routing) and the key profile cache."""

from unittest.mock import MagicMock, patch

import pytest
import redis

from quant.trade.brokers.ccxt.config import CCXT_PRESETS
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import BrokerAuthError, BrokerConnectionError
from quant.trade.brokers.ccxt.routing import KeyRouter, profile_key
from quant.trade.key_profiles import KEY_PROFILE_TTL_S, RedisKeyProfiles
from quant.trade.models.key_profile import ApiKeyInfo, KeyProfile
from quant.trade.models.order import OrderRejectReason

PROXY = "http://13.43.55.53:3128"


def _session(**overrides) -> CcxtSessionConfig:
    fields = dict(api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=False)
    fields.update(overrides)
    return CcxtSessionConfig(**fields)


class _MemoryStore:
    def __init__(self, entries=None):
        self.entries = dict(entries or {})

    def get(self, key):
        return self.entries.get(key)

    def put(self, key, profile):
        self.entries[key] = profile


def _ip_refused():
    return BrokerAuthError("unmatched IP", reason=OrderRejectReason.IP_NOT_ALLOWED)


@pytest.fixture
def uk_route(monkeypatch):
    monkeypatch.setenv("CCXT_EGRESS_BYBIT", f"uk={PROXY}")


class TestKeyProfile:
    def test_json_round_trip(self):
        profile = KeyProfile(
            route="uk",
            info=ApiKeyInfo(
                ips=("13.43.55.53",), kyc_region="GBR", read_only=False,
                expires_at="2027-01-01",
            ),
            restricted_market_types=frozenset({"linear"}),
        )
        assert KeyProfile.from_json(profile.to_json()) == profile

    def test_clean_key_is_not_refused(self):
        assert KeyProfile(route="direct").refusal("linear") is None

    def test_read_only_is_refused_for_any_market(self):
        reason, _ = KeyProfile(route="direct", info=ApiKeyInfo(read_only=True)).refusal("spot")
        assert reason is OrderRejectReason.KEY_READ_ONLY

    def test_accepted_carries_restrictions_but_takes_the_new_route_and_info(self):
        old = KeyProfile(
            route="direct", info=ApiKeyInfo(kyc_region="HKG"),
            restricted_market_types=frozenset({"linear"}),
        )
        new = KeyProfile.accepted("uk", ApiKeyInfo(kyc_region="GBR"), carrying=old)
        assert new == KeyProfile(
            route="uk", info=ApiKeyInfo(kyc_region="GBR"),
            restricted_market_types=frozenset({"linear"}),
        )
        assert KeyProfile.accepted("uk", None, carrying=None) == KeyProfile(route="uk")

    def test_restriction_applies_only_to_its_market_type(self):
        profile = KeyProfile(route="uk").restricting("linear")
        assert profile.refusal("linear")[0] is OrderRejectReason.REGION_RESTRICTED
        assert profile.refusal("spot") is None


class TestErrorReason:
    def test_plain_connection_error_has_no_reason(self):
        assert BrokerConnectionError("down").reason is None

    def test_auth_error_keeps_its_reason_and_status(self):
        exc = BrokerAuthError("nope", reason=OrderRejectReason.IP_NOT_ALLOWED)
        assert exc.reason is OrderRejectReason.IP_NOT_ALLOWED
        assert exc.status_code == 400


class TestProfileKey:
    def test_never_contains_the_api_key(self):
        key = profile_key(_session(api_key="super-secret-key"))
        assert "super-secret-key" not in key
        assert key.startswith("key_profile:bybit:live:")

    def test_environments_do_not_share_an_entry(self):
        assert profile_key(_session(paper=True)) != profile_key(_session(paper=False))
        assert profile_key(_session(demo=True)).split(":")[2] == "demo"


class TestKeyRouter:
    @staticmethod
    def _gateway(*answers, session=None):
        """A gateway whose key-information call answers (or raises) in turn."""
        gateway = MagicMock(spec=CcxtTradeGateway)
        gateway.session = session or _session()
        gateway.fetch_api_key_info.side_effect = list(answers)
        return gateway

    @staticmethod
    def _routes_tried(gateway):
        return [c.args[0].name for c in gateway.connect.call_args_list]

    def test_first_accepting_route_wins_and_is_cached(self, uk_route):
        gateway = self._gateway(_ip_refused(), ApiKeyInfo(kyc_region="GBR"))
        store = _MemoryStore()

        profile = KeyRouter(store).connect(gateway)

        assert profile.route == "uk"
        assert profile.info.kyc_region == "GBR"
        assert store.get(profile_key(_session())) == profile
        assert self._routes_tried(gateway) == ["direct", "uk"]
        assert gateway.connect.call_args.args[0].proxy_url == PROXY
        gateway.disconnect.assert_called_once()

    def test_cached_route_is_tried_first(self, uk_route):
        gateway = self._gateway(ApiKeyInfo())
        store = _MemoryStore({profile_key(_session()): KeyProfile(route="uk")})
        assert KeyRouter(store).connect(gateway).route == "uk"
        assert self._routes_tried(gateway) == ["uk"]
        gateway.disconnect.assert_not_called()

    def test_key_moved_off_cached_route(self, uk_route):
        gateway = self._gateway(_ip_refused(), ApiKeyInfo())
        store = _MemoryStore({profile_key(_session()): KeyProfile(route="uk")})
        assert KeyRouter(store).connect(gateway).route == "direct"
        assert self._routes_tried(gateway) == ["uk", "direct"]
        assert store.get(profile_key(_session())).route == "direct"

    def test_every_route_refused_is_an_ip_refusal(self, uk_route):
        gateway = self._gateway(_ip_refused(), _ip_refused())
        with pytest.raises(BrokerAuthError) as info:
            KeyRouter(_MemoryStore()).connect(gateway)
        assert info.value.reason is OrderRejectReason.IP_NOT_ALLOWED
        assert "direct, uk" in str(info.value)

    def test_outage_does_not_fall_through_to_another_route(self, uk_route):
        gateway = self._gateway()
        gateway.connect.side_effect = BrokerConnectionError("proxy down")
        store = _MemoryStore({profile_key(_session()): KeyProfile(route="uk")})
        with pytest.raises(BrokerConnectionError):
            KeyRouter(store).connect(gateway)
        assert self._routes_tried(gateway) == ["uk"]

    def test_other_auth_errors_stop_at_the_first_route(self, uk_route):
        gateway = self._gateway(BrokerAuthError("bad key"))
        with pytest.raises(BrokerAuthError):
            KeyRouter(_MemoryStore()).connect(gateway)
        assert self._routes_tried(gateway) == ["direct"]

    def test_reconnect_keeps_learned_restrictions(self, uk_route):
        gateway = self._gateway(ApiKeyInfo(kyc_region="GBR"))
        cached = KeyProfile(route="uk", restricted_market_types=frozenset({"linear"}))
        store = _MemoryStore({profile_key(_session()): cached})
        profile = KeyRouter(store).connect(gateway)
        assert profile.restricted_market_types == frozenset({"linear"})

    def test_venue_without_key_information_uses_the_first_route(self, monkeypatch, caplog):
        monkeypatch.setenv("CCXT_EGRESS_BINANCEUSDM", f"uk={PROXY}")
        gateway = self._gateway(None, session=_session(preset=CCXT_PRESETS["binance"]))
        profile = KeyRouter(_MemoryStore()).connect(gateway)
        assert profile == KeyProfile(route="direct")
        assert self._routes_tried(gateway) == ["direct"]
        assert "cannot be verified" in caplog.text

    def test_works_without_a_store(self, monkeypatch):
        monkeypatch.delenv("CCXT_EGRESS_BYBIT", raising=False)
        profile = KeyRouter(None).connect(self._gateway(ApiKeyInfo()))
        assert profile.route == "direct"

    def test_record_restriction_updates_cache_and_returns_the_profile(self):
        store = _MemoryStore()
        updated = KeyRouter(store).record_restriction(
            _session(), KeyProfile(route="uk"), "linear"
        )
        assert updated.restricted_market_types == {"linear"}
        assert store.get(profile_key(_session())) == updated

    def test_record_restriction_without_a_store_still_returns_the_profile(self):
        updated = KeyRouter(None).record_restriction(
            _session(), KeyProfile(route="uk"), "linear"
        )
        assert updated.restricted_market_types == {"linear"}

    def test_bad_key_disconnects_before_raising(self, uk_route):
        """The caller connected inside ``with``; nothing else will close it."""
        gateway = self._gateway(BrokerAuthError("bad key"))
        with pytest.raises(BrokerAuthError):
            KeyRouter(_MemoryStore()).connect(gateway)
        gateway.disconnect.assert_called_once()

    def test_venue_outage_on_key_info_disconnects_before_raising(self, uk_route):
        gateway = self._gateway(BrokerConnectionError("timeout"))
        with pytest.raises(BrokerConnectionError):
            KeyRouter(_MemoryStore()).connect(gateway)
        gateway.disconnect.assert_called_once()


class TestRedisKeyProfiles:
    @pytest.fixture
    def client(self):
        client = MagicMock()
        with patch("quant.trade.key_profiles.redis.Redis.from_url", return_value=client):
            yield client

    def test_put_writes_json_with_ttl(self, client):
        RedisKeyProfiles("redis://x").put("k", KeyProfile(route="uk"))
        assert client.set.call_args.kwargs["ex"] == KEY_PROFILE_TTL_S

    def test_get_round_trips(self, client):
        store = RedisKeyProfiles("redis://x")
        store.put("k", KeyProfile(route="uk", info=ApiKeyInfo(kyc_region="GBR")))
        client.get.return_value = client.set.call_args.args[1]
        assert store.get("k") == KeyProfile(route="uk", info=ApiKeyInfo(kyc_region="GBR"))

    def test_miss_and_garbage_read_as_empty(self, client):
        store = RedisKeyProfiles("redis://x")
        client.get.return_value = None
        assert store.get("k") is None
        client.get.return_value = "{not json"
        assert store.get("k") is None

    def test_unreachable_cache_is_tolerated(self, client):
        client.get.side_effect = redis.ConnectionError("down")
        client.set.side_effect = redis.ConnectionError("down")
        store = RedisKeyProfiles("redis://x")
        assert store.get("k") is None
        store.put("k", KeyProfile(route="uk"))
