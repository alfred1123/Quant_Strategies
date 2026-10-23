"""Unit tests for ccxt broker adapter and exchange wiring."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import ccxt
import pytest

from quant.schemas.apply import ApplyReport
from quant.trade.brokers.ccxt.adapter import CcxtTradeAdapter, create_ccxt_adapter
from quant.trade.brokers.ccxt.config import (
    CCXT_PRESETS,
    BybitVenue,
    CcxtVenue,
    ConnectParams,
)
from quant.trade.brokers.ccxt.egress import DIRECT, EgressRoute, EgressRoutes
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import (
    BrokerAuthError,
    BrokerConnectionError,
    SymbolMappingError,
    TradeValidationError,
)
from quant.trade.models.key_profile import ApiKeyInfo, KeyProfile
from quant.trade.models.market import MarketLimits
from quant.trade.models.order import (
    IntendedAction,
    OrderRejectReason,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)
from quant.trade.order_policy import OrderRetryExecutor, OrderRetryPolicy
from quant.trade.scheduler.tick import ScheduleTickRunner, TickOutcome
from tests.unit.test_schedule_tick import _due_row

#: The seeded CONFIG.SETTING fill_confirm_delays_s.
_DELAYS = (0.3, 0.6, 1.2, 2.4, 3.5)


@pytest.fixture
def inst_cache():
    cache = MagicMock()
    cache.get_product_by_cusip.return_value = {
        "product_id": 1,
        "internal_cusip": "btcusdt.crypto",
        "issue_type": "spot",
    }
    cache.resolve_internal_cusip.return_value = "BTCUSDT"
    return cache


class TestExchangeWiring:
    def test_default_paper_enables_sandbox(self):
        exchange = MagicMock()
        CcxtVenue().wire(exchange, ConnectParams(paper=True))
        exchange.set_sandbox_mode.assert_called_once_with(True)

    def test_default_live_skips_sandbox(self):
        exchange = MagicMock()
        CcxtVenue().wire(exchange, ConnectParams(paper=False))
        exchange.set_sandbox_mode.assert_not_called()

    def test_bybit_demo_enables_demo_not_sandbox(self):
        exchange = MagicMock()
        exchange.has = {"fetchCurrencies": True}
        BybitVenue().wire(exchange, ConnectParams(paper=True, demo=True))
        assert exchange.has["fetchCurrencies"] is False
        exchange.enable_demo_trading.assert_called_once_with(True)
        exchange.set_sandbox_mode.assert_not_called()

    def test_bybit_paper_enables_sandbox_not_demo(self):
        exchange = MagicMock()
        exchange.has = {"fetchCurrencies": True}
        BybitVenue().wire(exchange, ConnectParams(paper=True, demo=False))
        assert exchange.has["fetchCurrencies"] is False
        exchange.set_sandbox_mode.assert_called_once_with(True)
        exchange.enable_demo_trading.assert_not_called()

    def test_bybit_live_skips_demo_and_sandbox(self):
        exchange = MagicMock()
        exchange.has = {"fetchCurrencies": True}
        BybitVenue().wire(exchange, ConnectParams(paper=False, demo=False))
        exchange.set_sandbox_mode.assert_not_called()
        exchange.enable_demo_trading.assert_not_called()

    def test_presets_carry_their_venue(self):
        assert isinstance(CCXT_PRESETS["bybit"].venue, BybitVenue)
        assert type(CCXT_PRESETS["binance"].venue) is CcxtVenue

    def test_default_venue_adds_nothing_to_errors(self):
        venue = CcxtVenue()
        assert venue.auth_hint(ConnectParams(paper=True)) == ""
        assert venue.classify_denial(ccxt.PermissionDenied('{"retCode":10010}')) is None


class TestIntendedActionOrderSide:
    """IntendedAction.order_side — collapses position-aware action to raw side."""

    @pytest.mark.parametrize("action,expected", [
        (IntendedAction.BUY, OrderSide.BUY),
        (IntendedAction.CLOSE_SHORT, OrderSide.BUY),
        (IntendedAction.SELL, OrderSide.SELL),
        (IntendedAction.OPEN_SHORT, OrderSide.SELL),
        (IntendedAction.HOLD, None),
    ])
    def test_mapping(self, action, expected):
        assert action.order_side() == expected


class TestSessionConfigRepr:
    def test_secrets_hidden_from_repr(self):
        cfg = CcxtSessionConfig(
            api_key="AKIA-VISIBLE-KEY",
            api_secret="super-secret-value",
            preset=CCXT_PRESETS["bybit"],
        )
        assert "AKIA-VISIBLE-KEY" not in repr(cfg)
        assert "super-secret-value" not in repr(cfg)


class TestEgressRoutes:
    """``CCXT_EGRESS_<EXCHANGE_ID>`` lists candidate routes; direct always comes first."""

    PROXY = "http://13.43.55.53:3128"

    def test_env_var_is_named_for_the_ccxt_exchange(self):
        assert EgressRoutes.env_var("bybit") == "CCXT_EGRESS_BYBIT"
        assert EgressRoutes.env_var("binanceusdm") == "CCXT_EGRESS_BINANCEUSDM"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_unset_or_blank_is_direct_only(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv("CCXT_EGRESS_BYBIT", raising=False)
        else:
            monkeypatch.setenv("CCXT_EGRESS_BYBIT", value)
        assert tuple(EgressRoutes.from_env("bybit")) == (DIRECT,)

    def test_named_proxies_follow_direct(self, monkeypatch):
        monkeypatch.setenv(
            "CCXT_EGRESS_BYBIT", f" uk = {self.PROXY} , eu=http://10.0.0.2:3128"
        )
        assert tuple(EgressRoutes.from_env("bybit")) == (
            DIRECT,
            EgressRoute("uk", self.PROXY),
            EgressRoute("eu", "http://10.0.0.2:3128"),
        )

    @pytest.mark.parametrize("entry", ["uk", "=http://x:1", "uk=", "direct=http://x:1"])
    def test_malformed_entries_are_skipped(self, monkeypatch, entry):
        monkeypatch.setenv("CCXT_EGRESS_BYBIT", f"{entry},uk={self.PROXY}")
        assert tuple(EgressRoutes.from_env("bybit")) == (
            DIRECT, EgressRoute("uk", self.PROXY),
        )

    def test_one_venue_routes_do_not_leak_to_another(self, monkeypatch):
        monkeypatch.setenv("CCXT_EGRESS_BYBIT", f"uk={self.PROXY}")
        monkeypatch.delenv("CCXT_EGRESS_BINANCEUSDM", raising=False)
        assert tuple(EgressRoutes.from_env("binanceusdm")) == (DIRECT,)

    def test_preferring_moves_one_route_to_the_front(self):
        uk, eu = EgressRoute("uk", self.PROXY), EgressRoute("eu", "http://x:1")
        routes = EgressRoutes((DIRECT, uk, eu))
        assert routes.preferring("eu") == (eu, DIRECT, uk)
        assert routes.preferring(None) == (DIRECT, uk, eu)
        assert routes.preferring("gone") == (DIRECT, uk, eu)

    def test_issue_type_selects_the_default_type(self):
        bybit = CCXT_PRESETS["bybit"]
        assert bybit.default_type_for("spot") == "spot"
        assert bybit.default_type_for("future") == "linear"
        assert CCXT_PRESETS["binance"].default_type_for("spot") is None
        with pytest.raises(ValueError, match="ISSUE_TYPE"):
            bybit.default_type_for(None)


class TestBybitKeyIntrospection:
    def test_denial_codes_are_told_apart(self):
        venue = BybitVenue()
        ip = ccxt.PermissionDenied('bybit {"retCode":10010,"retMsg":"Unmatched IP"}')
        region = ccxt.PermissionDenied('bybit {"retCode": 10024, "retMsg":"regulatory"}')
        revoked = ccxt.PermissionDenied('bybit {"retCode":10005,"retMsg":"denied"}')
        assert venue.classify_denial(ip) is OrderRejectReason.IP_NOT_ALLOWED
        assert venue.classify_denial(region) is OrderRejectReason.REGION_RESTRICTED
        assert venue.classify_denial(revoked) is None
        assert venue.classify_denial(ccxt.PermissionDenied("no json here")) is None

    def test_query_api_is_read_into_api_key_info(self):
        exchange = MagicMock()
        exchange.private_get_v5_user_query_api.return_value = {
            "result": {
                "ips": ["13.43.55.53"], "kycRegion": "GBR",
                "readOnly": 0, "expiredAt": "2027-01-01T00:00:00Z",
            }
        }
        assert BybitVenue().fetch_api_key_info(exchange) == ApiKeyInfo(
            ips=("13.43.55.53",), kyc_region="GBR",
            read_only=False, expires_at="2027-01-01T00:00:00Z",
        )

    def test_read_only_flag_and_missing_fields(self):
        exchange = MagicMock()
        exchange.private_get_v5_user_query_api.return_value = {
            "result": {"readOnly": "1"}
        }
        assert BybitVenue().fetch_api_key_info(exchange) == ApiKeyInfo(read_only=True)

    def test_default_venue_has_no_key_information_call(self):
        exchange = MagicMock()
        assert CcxtVenue().fetch_api_key_info(exchange) is None
        exchange.assert_not_called()
        assert exchange.method_calls == []


class TestGatewayRouting:
    PROXY = "http://13.43.55.53:3128"
    UK = EgressRoute("uk", PROXY)

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_gateway_hands_the_proxy_to_ccxt(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {}
        exchange.has = {}
        mock_ccxt.bybit.return_value = exchange

        gateway = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=False,
            )
        )
        gateway.connect(self.UK)

        assert mock_ccxt.bybit.call_args.args[0]["httpsProxy"] == self.PROXY
        assert gateway.route == self.UK

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_gateway_without_route_goes_direct(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {}
        exchange.has = {}
        mock_ccxt.bybit.return_value = exchange

        gateway = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"]
            )
        )
        gateway.connect()

        assert "httpsProxy" not in mock_ccxt.bybit.call_args.args[0]
        assert gateway.route == DIRECT

    @staticmethod
    def _connected(exchange, mock_ccxt):
        mock_ccxt.AuthenticationError = ccxt.AuthenticationError
        mock_ccxt.InsufficientFunds = ccxt.InsufficientFunds
        mock_ccxt.InvalidOrder = ccxt.InvalidOrder
        mock_ccxt.BaseError = ccxt.BaseError
        exchange.markets = {}
        exchange.has = {}
        mock_ccxt.bybit.return_value = exchange
        gateway = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=False,
            )
        )
        gateway.connect()
        return gateway

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_api_key_info_is_read_on_the_live_session(self, mock_ccxt):
        exchange = MagicMock()
        exchange.private_get_v5_user_query_api.return_value = {
            "result": {"ips": ["*"], "kycRegion": "HKG", "readOnly": 0}
        }
        gateway = self._connected(exchange, mock_ccxt)

        assert gateway.fetch_api_key_info().kyc_region == "HKG"
        assert mock_ccxt.bybit.call_count == 1

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_auth_error_carries_the_classified_reason(self, mock_ccxt):
        exchange = MagicMock()
        exchange.private_get_v5_user_query_api.side_effect = ccxt.PermissionDenied(
            'bybit {"retCode":10010,"retMsg":"Unmatched IP"}'
        )
        gateway = self._connected(exchange, mock_ccxt)

        with pytest.raises(BrokerAuthError) as info:
            gateway.fetch_api_key_info()
        assert info.value.reason is OrderRejectReason.IP_NOT_ALLOWED

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_an_unclassified_denial_is_still_a_typed_key_refusal(self, mock_ccxt):
        """Bybit 10005 is not in the venue map; the auth path types it anyway."""
        exchange = MagicMock()
        exchange.private_get_v5_user_query_api.side_effect = ccxt.PermissionDenied(
            'bybit {"retCode":10005,"retMsg":"permission denied"}'
        )
        gateway = self._connected(exchange, mock_ccxt)

        with pytest.raises(BrokerAuthError) as info:
            gateway.fetch_api_key_info()
        assert info.value.reason is OrderRejectReason.KEY_REFUSED
        assert not info.value.reason.requires_operator_fix

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    @pytest.mark.parametrize(
        ("exc", "reason"),
        [
            (ccxt.InsufficientFunds("not enough USDT"), OrderRejectReason.INSUFFICIENT_FUNDS),
            (ccxt.InvalidOrder("qty precision"), OrderRejectReason.INVALID_ORDER),
        ],
    )
    def test_submit_refusals_are_typed_by_the_gateway(self, mock_ccxt, exc, reason):
        exchange = MagicMock()
        exchange.create_order.side_effect = exc
        gateway = self._connected(exchange, mock_ccxt)

        with pytest.raises(BrokerConnectionError) as info:
            gateway.create_market_order("BTCUSDT", "buy", 0.01)
        assert info.value.reason is reason

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_venue_outage_is_a_connection_error(self, mock_ccxt):
        exchange = MagicMock()
        exchange.private_get_v5_user_query_api.side_effect = ccxt.NetworkError("timeout")
        gateway = self._connected(exchange, mock_ccxt)

        with pytest.raises(BrokerConnectionError) as info:
            gateway.fetch_api_key_info()
        assert not isinstance(info.value, BrokerAuthError)


class TestAdapterKeyRouting:
    """The adapter opens its session on the router's route and obeys the profile."""

    PROXY = "http://13.43.55.53:3128"

    def _adapter(self, inst_cache, router):
        return create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"], api_key="k", api_secret="s",
            paper=False, inst_cache=inst_cache, confirm_delays_s=_DELAYS, key_router=router,
        )

    def _router(self, profile):
        router = MagicMock()
        router.connect.return_value = profile
        return router

    @patch.object(CcxtTradeGateway, "connect")
    def test_connect_is_handed_to_the_router(self, connect, inst_cache):
        router = self._router(KeyProfile(route="uk"))
        adapter = self._adapter(inst_cache, router)
        adapter.connect()
        router.connect.assert_called_once_with(adapter.gateway)
        connect.assert_not_called()
        assert adapter.key_profile == KeyProfile(route="uk")

    @patch.object(CcxtTradeGateway, "fetch_api_key_info", return_value=ApiKeyInfo())
    @patch.object(CcxtTradeGateway, "connect")
    def test_no_router_still_routes_without_a_cache(self, connect, _info, inst_cache, monkeypatch):
        monkeypatch.delenv("CCXT_EGRESS_BYBIT", raising=False)
        adapter = self._adapter(inst_cache, None)
        adapter.connect()
        connect.assert_called_once_with(DIRECT)
        assert adapter.key_profile == KeyProfile(route="direct", info=ApiKeyInfo())

    @patch.object(CcxtTradeGateway, "create_market_order")
    @patch.object(CcxtTradeGateway, "connect")
    def test_read_only_key_is_refused_before_submit(self, _connect, create, inst_cache):
        profile = KeyProfile(route="direct", info=ApiKeyInfo(read_only=True))
        adapter = self._adapter(inst_cache, self._router(profile))
        adapter.connect()
        adapter.pin_instrument("btcusdt.crypto")
        result = adapter.place_order(OrderRequest("BTCUSDT", 0.001, OrderSide.BUY))
        assert result.reason is OrderRejectReason.KEY_READ_ONLY
        create.assert_not_called()

    @patch.object(CcxtTradeGateway, "create_market_order")
    @patch.object(CcxtTradeGateway, "connect")
    def test_known_region_restriction_is_refused_before_submit(self, _connect, create, inst_cache):
        """A linear refusal blocks a future instrument and leaves a spot one alone."""
        profile = KeyProfile(
            route="uk", info=ApiKeyInfo(kyc_region="GBR"),
            restricted_market_types=frozenset({"linear"}),
        )
        create.return_value = {"id": None}
        adapter = self._adapter(inst_cache, self._router(profile))
        adapter.connect()
        adapter.pin_instrument("btcusdt.crypto")
        adapter.place_order(OrderRequest("BTCUSDT", 0.001, OrderSide.BUY))
        create.assert_called_once()

        inst_cache.get_product_by_cusip.return_value = {
            "product_id": 1, "internal_cusip": "btcusdt.crypto", "issue_type": "future",
        }
        create.reset_mock()
        adapter.pin_instrument("btcusdt.crypto")
        result = adapter.place_order(OrderRequest("BTCUSDT", 0.001, OrderSide.BUY))
        assert result.reason is OrderRejectReason.REGION_RESTRICTED
        assert "GBR" in result.message
        create.assert_not_called()

    @patch.object(CcxtTradeGateway, "fetch_market_limits", return_value=MarketLimits(symbol="BTCUSDT"))
    @patch.object(CcxtTradeGateway, "create_market_order")
    @patch.object(CcxtTradeGateway, "connect")
    def test_venue_region_refusal_is_typed_and_remembered(self, _connect, create, _limits, inst_cache):
        create.side_effect = BrokerAuthError(
            "authentication failed during create_order: 10024",
            reason=OrderRejectReason.REGION_RESTRICTED,
        )
        router = self._router(KeyProfile(route="uk"))
        router.record_restriction.return_value = KeyProfile(
            route="uk", restricted_market_types=frozenset({"spot"})
        )
        adapter = self._adapter(inst_cache, router)
        adapter.connect()
        adapter.pin_instrument("btcusdt.crypto")

        result = adapter.place_order(OrderRequest("BTCUSDT", 0.001, OrderSide.BUY))

        assert result.success is False
        assert result.reason is OrderRejectReason.REGION_RESTRICTED
        session, profile, market_type = router.record_restriction.call_args.args
        assert session.api_key == "k"
        assert profile == KeyProfile(route="uk")
        assert market_type == "spot"
        # The in-memory profile follows the cache, so the next order in this
        # session is refused before it is sent.
        assert adapter.key_profile.restricted_market_types == {"spot"}
        create.reset_mock()
        again = adapter.place_order(OrderRequest("BTCUSDT", 0.001, OrderSide.BUY))
        assert again.reason is OrderRejectReason.REGION_RESTRICTED
        create.assert_not_called()


class TestCcxtTradeGateway:
    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_bybit_validate_credentials_success(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["bybit"],
                paper=True,
            )
        )
        gw.connect()
        gw.validate_credentials()

        exchange.set_sandbox_mode.assert_called_once_with(True)
        assert exchange.has["fetchCurrencies"] is False
        exchange.load_markets.assert_called_once()
        exchange.fetch_balance.assert_called_once()

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_bybit_demo_wiring(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["bybit"],
                paper=True,
                demo=True,
            )
        )
        gw.connect()

        exchange.enable_demo_trading.assert_called_once_with(True)
        exchange.set_sandbox_mode.assert_not_called()

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_binance_validate_credentials_success(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTC/USDT:USDT": {}}
        mock_ccxt.binanceusdm.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["binance"],
                paper=True,
            )
        )
        gw.connect()
        gw.validate_credentials()

        exchange.set_sandbox_mode.assert_called_once_with(True)
        mock_ccxt.binanceusdm.assert_called_once()
        exchange.fetch_balance.assert_called_once()

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_fetch_position_qty_matches_unified_symbol(self, mock_ccxt):
        """fetch_positions returns ccxt unified symbol (BTC/USDT:USDT), not
        the raw vendor_symbol (BTCUSDT) — must still match."""
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.market.return_value = {"symbol": "BTC/USDT:USDT"}
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0.001, "side": "long", "info": {"symbol": "BTCUSDT"}}
        ]
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True,
            )
        )
        gw.connect()
        assert gw.fetch_position_qty("BTCUSDT") == 0.001

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_fetch_position_qty_short_is_negative(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.market.return_value = {"symbol": "BTC/USDT:USDT"}
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0.002, "side": "short", "info": {"symbol": "BTCUSDT"}}
        ]
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True,
            )
        )
        gw.connect()
        assert gw.fetch_position_qty("BTCUSDT") == -0.002

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_fetch_position_qty_no_position_returns_zero(self, mock_ccxt):
        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.market.return_value = {"symbol": "BTC/USDT:USDT"}
        exchange.fetch_positions.return_value = []
        mock_ccxt.bybit.return_value = exchange

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True,
            )
        )
        gw.connect()
        assert gw.fetch_position_qty("BTCUSDT") == 0.0

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_auth_failure_raises(self, mock_ccxt):
        import ccxt

        exchange = MagicMock()
        exchange.markets = {"BTCUSDT": {}}
        exchange.has = {"fetchCurrencies": True}
        exchange.fetch_balance.side_effect = ccxt.AuthenticationError("bad key")
        mock_ccxt.bybit.return_value = exchange
        mock_ccxt.AuthenticationError = ccxt.AuthenticationError
        mock_ccxt.BaseError = ccxt.BaseError

        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k",
                api_secret="s",
                preset=CCXT_PRESETS["bybit"],
                paper=True,
            )
        )
        gw.connect()
        with pytest.raises(BrokerAuthError, match="authentication") as exc_info:
            gw.validate_credentials()
        # A rejected key is the caller's to fix, so it must not read as an
        # outage — and the hint naming testnet is the actionable part.
        assert exc_info.value.status_code == 400
        assert "testnet.bybit.com" in str(exc_info.value)

    def _connected(self, exchange) -> CcxtTradeGateway:
        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"],
            )
        )
        gw._exchange = exchange
        return gw

    def test_market_limits_come_off_the_loaded_market(self):
        exchange = MagicMock()
        exchange.market.return_value = {
            "limits": {"amount": {"min": "0.001"}, "cost": {"min": 5}}
        }
        limits = self._connected(exchange).fetch_market_limits("BTCUSDT")
        assert limits == MarketLimits("BTCUSDT", min_qty=0.001, min_notional=5.0)

    def test_a_market_that_publishes_no_limits_enforces_nothing(self):
        exchange = MagicMock()
        exchange.market.return_value = {"limits": {"amount": {}}}
        limits = self._connected(exchange).fetch_market_limits("BTCUSDT")
        assert limits == MarketLimits("BTCUSDT")

    def test_an_unlisted_symbol_enforces_nothing(self):
        exchange = MagicMock()
        exchange.market.side_effect = ccxt.BadSymbol("nope")
        assert self._connected(exchange).fetch_market_limits("NOPE").min_qty is None

    def test_a_disconnected_session_enforces_nothing(self):
        gw = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"],
            )
        )
        assert gw.fetch_market_limits("BTCUSDT") == MarketLimits("BTCUSDT")

    def test_all_limits_are_keyed_by_venue_id_and_unified_symbol(self):
        """INST.PRODUCT_XREF stores one or the other depending on the venue."""
        exchange = MagicMock()
        exchange.markets = {
            "BTC/USDT:USDT": {
                "id": "BTCUSDT",
                "symbol": "BTC/USDT:USDT",
                "linear": True,
                "limits": {"amount": {"min": 0.001}},
            }
        }
        limits = self._connected(exchange).fetch_all_market_limits()

        assert limits["BTCUSDT"] == MarketLimits("BTCUSDT", min_qty=0.001)
        assert limits["BTC/USDT:USDT"] == MarketLimits("BTC/USDT:USDT", min_qty=0.001)

    def test_a_pinned_default_type_excludes_the_other_markets(self):
        """Bybit prints BTCUSDT for both; the instrument's default type picks one."""
        exchange = MagicMock()
        exchange.options = {}
        exchange.markets = {
            "BTC/USDT:USDT": {
                "id": "BTCUSDT",
                "symbol": "BTC/USDT:USDT",
                "linear": True,
                "spot": False,
                "limits": {"amount": {"min": 0.001}},
            },
            "BTC/USDT": {
                "id": "BTCUSDT",
                "symbol": "BTC/USDT",
                "linear": False,
                "spot": True,
                "limits": {"amount": {"min": 0.000048}},
            },
        }
        gateway = self._connected(exchange)
        gateway.pin_default_type("spot")
        limits = gateway.fetch_all_market_limits()

        assert limits["BTCUSDT"].min_qty == 0.000048
        assert "BTC/USDT:USDT" not in limits

    def test_a_spot_holding_is_the_base_balance(self):
        exchange = MagicMock()
        exchange.options = {}
        exchange.market.return_value = {"base": "BTC", "symbol": "BTC/USDT"}
        exchange.fetch_balance.return_value = {"total": {"BTC": "0.25", "USDT": "10"}}
        gateway = self._connected(exchange)
        gateway.pin_default_type("spot")

        assert gateway.fetch_position_qty("BTCUSDT") == 0.25
        exchange.fetch_positions.assert_not_called()

    def test_a_public_session_carries_no_keys(self):
        config = CcxtSessionConfig.public(CCXT_PRESETS["bybit"])
        assert (config.api_key, config.api_secret) == ("", "")
        # Live venue: the cached rules must be the ones a real order faces.
        assert config.paper is False


class TestCreateCcxtAdapter:
    @patch.object(CcxtTradeGateway, "validate_credentials")
    @patch.object(CcxtTradeGateway, "connect")
    @patch.object(CcxtTradeGateway, "market_exists", return_value=True)
    def test_bybit_dry_run(self, _market, _conn, _val, inst_cache):
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache, confirm_delays_s=_DELAYS,
        )
        symbol = adapter.validate_for_dry_run("btcusdt.crypto", 34)
        assert symbol == "BTCUSDT"
        assert adapter.gateway._config.preset.exchange_id == "bybit"

    @patch.object(CcxtTradeGateway, "validate_credentials")
    @patch.object(CcxtTradeGateway, "connect")
    @patch.object(CcxtTradeGateway, "market_exists", return_value=True)
    def test_binance_dry_run(self, _market, _conn, _val, inst_cache):
        inst_cache.resolve_internal_cusip.return_value = "BTC/USDT:USDT"
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["binance"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache, confirm_delays_s=_DELAYS,
        )
        symbol = adapter.validate_for_dry_run("btcusdt.crypto", 35)
        assert symbol == "BTC/USDT:USDT"
        assert adapter.gateway._config.preset.exchange_id == "binanceusdm"

    def test_unknown_cusip_raises(self, inst_cache):
        inst_cache.resolve_internal_cusip.return_value = None
        inst_cache.get_product_by_cusip.return_value = None
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache, confirm_delays_s=_DELAYS,
        )
        with pytest.raises(SymbolMappingError, match="unknown product"):
            adapter.validate_for_dry_run("missing.crypto", 34)

class TestPlaceOrder:
    def _adapter(self, inst_cache):
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache, confirm_delays_s=_DELAYS,
        )
        adapter.pin_instrument("btcusdt.crypto")
        return adapter

    @patch("quant.trade.brokers.ccxt.adapter.confirm_market_order")
    def test_place_order_buy_success(self, mock_confirm, inst_cache):
        adapter = self._adapter(inst_cache)
        mock_confirm.return_value = OrderResult(
            success=True, vendor_order_id="abc123", message="order filled",
            raw_status="closed", side=OrderSide.BUY, requested_qty=0.01,
            filled_qty=0.01, avg_price=64000.0, fee=0.256,
        )
        with patch.object(
            adapter.gateway, "create_market_order",
            return_value={"id": "abc123", "status": "open"},
        ) as mock_create:
            req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            result = adapter.place_order(req)

        mock_create.assert_called_once_with("BTCUSDT", "buy", 0.01)
        mock_confirm.assert_called_once_with(
            adapter.gateway, req=req, vendor_order_id="abc123", delays_s=_DELAYS,
        )
        assert result.success is True
        assert result.vendor_order_id == "abc123"
        assert result.filled_qty == 0.01

    @patch("quant.trade.brokers.ccxt.adapter.confirm_market_order")
    def test_place_order_sell_maps_side(self, mock_confirm, inst_cache):
        adapter = self._adapter(inst_cache)
        mock_confirm.return_value = OrderResult(
            success=True, vendor_order_id="xyz", message="filled",
            side=OrderSide.SELL, requested_qty=0.01,
        )
        with patch.object(
            adapter.gateway, "create_market_order", return_value={"id": "xyz"},
        ) as mock_create:
            adapter.place_order(OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.SELL))
        mock_create.assert_called_once_with("BTCUSDT", "sell", 0.01)

    def test_place_order_rejects_limit_orders(self, inst_cache):
        adapter = self._adapter(inst_cache)
        req = OrderRequest(
            symbol="BTCUSDT",
            qty=0.01,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=50_000.0,
        )
        with pytest.raises(TradeValidationError, match="market only"):
            adapter.place_order(req)

    def test_place_order_broker_error_returns_failed_result(self, inst_cache):
        """The gateway's typed reason rides onto the result unchanged."""
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "create_market_order",
            side_effect=BrokerConnectionError(
                "insufficient funds", reason=OrderRejectReason.INSUFFICIENT_FUNDS,
            ),
        ):
            req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            result = adapter.place_order(req)

        assert result.success is False
        assert result.vendor_order_id is None
        assert result.side == OrderSide.BUY
        assert result.requested_qty == 0.01
        assert result.reason is OrderRejectReason.INSUFFICIENT_FUNDS
        assert "insufficient funds" in result.message

    def test_place_order_no_order_id_returns_failed(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "create_market_order",
            return_value={"id": None, "status": "unknown"},
        ):
            req = OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            result = adapter.place_order(req)

        assert result.success is False
        assert result.reason is OrderRejectReason.NOT_ACKNOWLEDGED
        assert "no order id" in result.message

    def test_size_reject_never_reaches_the_venue(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "fetch_market_limits",
            return_value=MarketLimits("BTCUSDT", min_qty=0.001),
        ), patch.object(adapter.gateway, "create_market_order") as mock_create:
            req = OrderRequest(symbol="BTCUSDT", qty=0.0001, side=OrderSide.BUY)
            result = adapter.place_order(req)

        mock_create.assert_not_called()
        assert result.success is False
        assert result.reason is OrderRejectReason.SIZE_BELOW_MINIMUM
        assert "min qty 0.001" in result.message
        assert result.side == OrderSide.BUY
        assert result.requested_qty == 0.0001

    def test_notional_check_prices_the_order(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "fetch_market_limits",
            return_value=MarketLimits("BNBUSDT", min_notional=5.0),
        ), patch.object(adapter.gateway, "fetch_last_price", return_value=350.0), \
             patch.object(adapter.gateway, "create_market_order") as mock_create:
            result = adapter.place_order(
                OrderRequest(symbol="BNBUSDT", qty=0.001, side=OrderSide.BUY)
            )

        mock_create.assert_not_called()
        assert result.reason is OrderRejectReason.SIZE_BELOW_MINIMUM
        assert "min notional 5" in result.message

    def test_an_unpriceable_symbol_still_goes_to_the_broker(self, inst_cache):
        """No quote, no opinion — the venue's own reject text is what we record."""
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "fetch_market_limits",
            return_value=MarketLimits("BNBUSDT", min_notional=5.0),
        ), patch.object(
            adapter.gateway, "fetch_last_price",
            side_effect=BrokerConnectionError("fetch_ticker failed"),
        ), patch.object(
            adapter.gateway, "create_market_order",
            side_effect=BrokerConnectionError("invalid order: too small"),
        ) as mock_create:
            result = adapter.place_order(
                OrderRequest(symbol="BNBUSDT", qty=0.001, side=OrderSide.BUY)
            )

        mock_create.assert_called_once()
        assert result.reason is None
        assert "too small" in result.message

    @patch("quant.trade.brokers.ccxt.adapter.confirm_market_order")
    def test_a_size_within_the_limits_is_submitted(self, mock_confirm, inst_cache):
        adapter = self._adapter(inst_cache)
        mock_confirm.return_value = OrderResult(
            success=True, vendor_order_id="ok1", message="order filled",
        )
        with patch.object(
            adapter.gateway, "fetch_market_limits",
            return_value=MarketLimits("BTCUSDT", min_qty=0.001, min_notional=5.0),
        ), patch.object(adapter.gateway, "fetch_last_price", return_value=64000.0), \
             patch.object(
                 adapter.gateway, "create_market_order", return_value={"id": "ok1"},
             ) as mock_create:
            result = adapter.place_order(
                OrderRequest(symbol="BTCUSDT", qty=0.01, side=OrderSide.BUY)
            )

        mock_create.assert_called_once_with("BTCUSDT", "buy", 0.01)
        assert result.success is True

    def test_cancel_order_success(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "cancel_order", return_value={"status": "canceled"},
        ) as mock_cancel:
            result = adapter.cancel_order("order-1", "BTCUSDT")
        mock_cancel.assert_called_once_with("order-1", "BTCUSDT")
        assert result.success is True
        assert result.vendor_order_id == "order-1"

    @pytest.mark.parametrize(
        "message",
        [
            "authentication failed during cancel_order: permission denied",
            pytest.param("", id="empty-message"),
        ],
    )
    def test_cancel_order_keeps_a_typed_key_refusal(self, inst_cache, message):
        """The refusal is typed on the exception. Dropping it here is where the cause is lost."""
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "cancel_order",
            side_effect=BrokerAuthError(message, reason=OrderRejectReason.KEY_REFUSED),
        ):
            result = adapter.cancel_order("order-1", "BTCUSDT")
        assert result.success is False
        assert result.vendor_order_id == "order-1"
        assert result.reason is OrderRejectReason.KEY_REFUSED
        assert result.message == message

    @pytest.mark.parametrize(
        "message",
        [
            "cancel_order failed: timeout",
            pytest.param("", id="empty-message"),
        ],
    )
    def test_cancel_order_without_a_typed_reason_leaves_it_unset(self, inst_cache, message):
        adapter = self._adapter(inst_cache)
        with patch.object(
            adapter.gateway, "cancel_order",
            side_effect=BrokerConnectionError(message),
        ):
            result = adapter.cancel_order("order-1", "BTCUSDT")
        assert result.success is False
        assert result.vendor_order_id == "order-1"
        assert result.reason is None

    def test_get_open_orders_delegates_to_gateway(self, inst_cache):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter.gateway, "fetch_open_orders", return_value=[{"id": "1"}]) as mock_fetch:
            orders = adapter.get_open_orders("BTCUSDT")
        mock_fetch.assert_called_once_with("BTCUSDT")
        assert orders == [{"id": "1"}]


def _unconfirmed(vendor_order_id: str = "ord-1") -> OrderResult:
    return OrderResult(
        success=False,
        vendor_order_id=vendor_order_id,
        message="fill unconfirmed after 8.0s — requires manual reconciliation",
        side=OrderSide.BUY,
        requested_qty=0.01,
    )


def _tick_paused(outcome) -> bool:
    """One due deployment, paused on the first pass."""
    from quant.trade.order_policy import OrderRetryResult

    assert OrderRetryResult.pauses_deployment(outcome.failure_stage, outcome.result.reason)
    repo = MagicMock()
    repo.sp_get_missed_due_deployments.return_value = [_due_row()]
    result = outcome.result
    report = ApplyReport(
        deployment_id=uuid4(),
        deployment_vid=1,
        action=outcome.action,
        vendor_symbol="BTCUSDT",
        signal=1.0,
        position_qty=outcome.position_qty,
        order_success=False,
        vendor_order_id=result.vendor_order_id,
        message=result.message,
        reject_reason=result.reason,
        failure_stage=outcome.failure_stage,
    )
    runner = ScheduleTickRunner(
        repo, lambda _user, _deployment: report, max_attempts=3, retry_backoff_s=0,
    )
    tick = runner.run_interval(1)
    paused = tick.results[0]
    return (
        paused.outcome is TickOutcome.PAUSED
        and paused.attempt == 1
        and repo.write_deployment.call_args.kwargs["deployment_status"] == "PAUSED"
        and repo.write_deployment.call_args.kwargs["is_enabled_ind"] == "N"
    )


class TestTypedCancelRefusal:
    """A refused cancel keeps the venue's reason and still stops the retry."""

    def _adapter(self, inst_cache):
        adapter = create_ccxt_adapter(
            preset=CCXT_PRESETS["bybit"],
            api_key="k",
            api_secret="s",
            paper=True,
            inst_cache=inst_cache,
            confirm_delays_s=_DELAYS,
        )
        adapter.pin_instrument("btcusdt.crypto")
        return adapter

    @pytest.mark.parametrize("max_attempts", [1, 5])
    @pytest.mark.parametrize(
        "message",
        [
            "authentication failed during cancel_order: permission denied",
            pytest.param("", id="empty-message"),
        ],
    )
    @patch("quant.trade.order_policy.time.sleep")
    def test_key_refused_on_cancel_is_kept_places_once_and_pauses(
        self, _sleep, inst_cache, message, max_attempts,
    ):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "place_order", wraps=adapter.place_order) as place, \
             patch.object(
                 adapter.gateway, "fetch_market_limits",
                 return_value=MarketLimits("BTCUSDT"),
             ), patch.object(
                 adapter.gateway, "fetch_position_qty", return_value=0.0,
             ) as position, patch.object(
                 adapter.gateway, "create_market_order",
                 return_value={"id": "ord-1"},
             ), patch.object(
                 adapter.gateway, "cancel_order",
                 side_effect=BrokerAuthError(
                     message, reason=OrderRejectReason.KEY_REFUSED,
                 ),
             ), patch(
                 "quant.trade.brokers.ccxt.adapter.confirm_market_order",
                 return_value=_unconfirmed(),
             ):
            outcome = OrderRetryExecutor(
                OrderRetryPolicy(max_attempts=max_attempts, backoff_s=2.0),
            ).execute(adapter, "BTCUSDT", 1.0, 0.01)

        result = outcome.result
        assert result is not None
        assert result.reason is OrderRejectReason.KEY_REFUSED
        assert result.message == OrderRejectReason.KEY_REFUSED.value
        assert not result.reason.requires_operator_fix
        assert result.success is False
        assert result.vendor_order_id == "ord-1"
        assert place.call_count == 1
        assert position.call_count == 1
        from quant.trade.models.order import OrderFailureStage
        from quant.trade.order_policy import OrderRetryResult
        assert outcome.failure_stage is OrderFailureStage.CANCEL
        assert len(outcome.attempts) == 1
        assert outcome.permanent_failure
        assert OrderRetryResult.pauses_deployment(outcome.failure_stage, result.reason)
        assert _tick_paused(outcome)
        _sleep.assert_not_called()

    @pytest.mark.parametrize(
        "message",
        [
            "cancel_order failed: timeout",
            pytest.param("", id="empty-message"),
        ],
    )
    @patch("quant.trade.order_policy.time.sleep")
    def test_untyped_cancel_failure_stays_cancel_failed(
        self, _sleep, inst_cache, message,
    ):
        adapter = self._adapter(inst_cache)
        with patch.object(adapter, "place_order", wraps=adapter.place_order) as place, \
             patch.object(
                 adapter.gateway, "fetch_market_limits",
                 return_value=MarketLimits("BTCUSDT"),
             ), patch.object(
                 adapter.gateway, "fetch_position_qty", return_value=0.0,
             ), patch.object(
                 adapter.gateway, "create_market_order",
                 return_value={"id": "ord-1"},
             ), patch.object(
                 adapter.gateway, "cancel_order",
                 side_effect=BrokerConnectionError(message),
             ), patch(
                 "quant.trade.brokers.ccxt.adapter.confirm_market_order",
                 return_value=_unconfirmed(),
             ):
            outcome = OrderRetryExecutor(
                OrderRetryPolicy(max_attempts=5, backoff_s=2.0),
            ).execute(adapter, "BTCUSDT", 1.0, 0.01)

        result = outcome.result
        assert result is not None
        assert result.reason is OrderRejectReason.CANCEL_FAILED
        assert result.message == OrderRejectReason.CANCEL_FAILED.value
        assert result.reason.requires_operator_fix
        from quant.trade.models.order import OrderFailureStage
        from quant.trade.order_policy import OrderRetryResult
        assert outcome.failure_stage is OrderFailureStage.CANCEL
        assert result.success is False
        assert place.call_count == 1
        assert len(outcome.attempts) == 1
        assert OrderRetryResult.pauses_deployment(outcome.failure_stage, result.reason)
        assert _tick_paused(outcome)
        _sleep.assert_not_called()
