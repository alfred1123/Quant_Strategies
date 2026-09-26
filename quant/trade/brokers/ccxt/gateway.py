"""ccxt gateway shared by REST crypto brokers (Bybit, Binance, …)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import ccxt

from quant.trade.brokers.ccxt.config import CcxtExchangePreset, ConnectParams
from quant.trade.brokers.ccxt.egress import DIRECT, EgressRoute
from quant.trade.errors import (
    BrokerAuthError,
    BrokerConnectionError,
    OrderNotFoundError,
)
from quant.trade.models.key_profile import ApiKeyInfo
from quant.trade.models.market import MarketLimits
from quant.trade.models.session import BrokerSessionState

logger = logging.getLogger(__name__)


def _as_float(value) -> float | None:
    """Coerce a ccxt numeric field, tolerating None and empty strings.

    Exchanges return these as strings, as numbers, or omit them entirely
    depending on the endpoint and the account mode, so a snapshot must not fail
    on one missing optional field.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CcxtSessionConfig:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    preset: CcxtExchangePreset
    paper: bool = True
    demo: bool = False

    @property
    def connect_params(self) -> ConnectParams:
        return ConnectParams(paper=self.paper, demo=self.demo)

    @classmethod
    def public(cls, preset: CcxtExchangePreset) -> "CcxtSessionConfig":
        """Keyless session for what the venue publishes to everyone.

        ``load_markets`` needs no credentials, which is what lets the API cache
        order-size rules without a user's keys. Live venue rather than the
        sandbox: the rules worth caching are the ones a real order is judged
        against. Connected direct: an IP allowlist binds a key, and this session
        has none.
        """
        return cls(api_key="", api_secret="", preset=preset, paper=False)


class CcxtTradeGateway:
    """Thin ccxt wrapper — load markets, balance, positions; no orders in dry-run."""

    def __init__(self, config: CcxtSessionConfig) -> None:
        self._config = config
        self._exchange: ccxt.Exchange | None = None
        self._route: EgressRoute = DIRECT
        self._default_type: str | None = None

    @property
    def exchange(self) -> ccxt.Exchange:
        if self._exchange is None:
            raise BrokerConnectionError("exchange not connected")
        return self._exchange

    @property
    def session(self) -> CcxtSessionConfig:
        return self._config

    @property
    def route(self) -> EgressRoute:
        """The egress route of the current (or last) connection."""
        return self._route

    def _build_exchange(self, route: EgressRoute) -> ccxt.Exchange:
        preset = self._config.preset
        exchange_cls = getattr(ccxt, preset.exchange_id, None)
        if exchange_cls is None:
            raise BrokerConnectionError(
                f"ccxt has no exchange class {preset.exchange_id!r}"
            )
        params: dict = {
            "apiKey": self._config.api_key,
            "secret": self._config.api_secret,
            "enableRateLimit": True,
        }
        default_type = self._default_type or preset.default_type
        if default_type:
            params["options"] = {"defaultType": default_type}
        if route.proxy_url:
            params["httpsProxy"] = route.proxy_url
        exchange = exchange_cls(params)
        preset.venue.wire(exchange, self._config.connect_params)
        return exchange

    def connect(self, route: EgressRoute = DIRECT) -> None:
        """Open a session on *route*; a failure leaves the gateway disconnected.

        Cleaning up here matters because callers connect inside ``with`` —
        an exception out of ``__enter__`` never reaches ``__exit__``.
        """
        preset = self._config.preset
        self._route = route
        self._exchange = self._build_exchange(route)
        try:
            self._exchange.load_markets()
        except ccxt.AuthenticationError as exc:
            self.disconnect()
            raise self._auth_error(exc, phase="load_markets") from exc
        except ccxt.BaseError as exc:
            self.disconnect()
            raise BrokerConnectionError(f"broker unreachable during load_markets: {exc}") from exc
        logger.info(
            "ccxt %s connected (paper=%s, demo=%s, markets=%d, proxy=%s)",
            preset.exchange_id,
            self._config.paper,
            self._config.demo,
            len(self._exchange.markets),
            route.proxy_url or route.name,
        )

    def _auth_error(self, exc: ccxt.AuthenticationError, *, phase: str) -> BrokerAuthError:
        venue = self._config.preset.venue
        hint = venue.auth_hint(self._config.connect_params)
        return BrokerAuthError(
            f"authentication failed during {phase}: {exc}.{hint}",
            reason=venue.classify_denial(exc),
        )

    def disconnect(self) -> None:
        if self._exchange is not None:
            try:
                self._exchange.close()
            except Exception:
                logger.debug("ccxt close failed", exc_info=True)
            self._exchange = None

    def health(self) -> BrokerSessionState:
        if self._exchange is None:
            return BrokerSessionState(connected=False, message="not connected")
        return BrokerSessionState(connected=True, message="ok")

    def fetch_api_key_info(self) -> ApiKeyInfo | None:
        """The venue's description of this session's key; ``None`` if it has no such call."""
        try:
            return self._config.preset.venue.fetch_api_key_info(self.exchange)
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_api_key_info") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_api_key_info failed: {exc}") from exc

    def validate_credentials(self) -> None:
        """Read-only check — load markets and fetch balance."""
        try:
            self.exchange.fetch_balance()
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_balance") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"broker unreachable: {exc}") from exc

    def pin_default_type(self, default_type: str | None) -> None:
        """Select the product ``market()`` resolves a shared id to.

        Bybit prints ``BTCUSDT`` for the spot pair and the perpetual. ccxt
        picks the one whose flag matches ``options.defaultType``, read on
        each call, so a session can follow the instrument it is about to trade.
        """
        self._default_type = default_type
        if self._exchange is None or not default_type:
            return
        options = getattr(self._exchange, "options", None)
        if not isinstance(options, dict):
            self._exchange.options = {"defaultType": default_type}
        else:
            options["defaultType"] = default_type

    def market_exists(self, vendor_symbol: str) -> bool:
        if vendor_symbol in self.exchange.markets:
            return True
        try:
            self.exchange.market(vendor_symbol)
            return True
        except ccxt.BadSymbol:
            return False

    def fetch_market_limits(self, vendor_symbol: str) -> MarketLimits:
        """The venue's min lot and min notional for *vendor_symbol*.

        Raw ``load_markets`` facts only — whether a given order is too small for
        them is :class:`MarketLimits`' question, not the session's. Unknown
        symbol, unlisted rule, or no session all yield empty limits, which
        enforce nothing.
        """
        if self._exchange is None:
            return MarketLimits(symbol=vendor_symbol)
        try:
            market = self.exchange.market(vendor_symbol)
        except ccxt.BadSymbol:
            return MarketLimits(symbol=vendor_symbol)
        except ccxt.BaseError:
            logger.debug("market limits lookup failed", exc_info=True)
            return MarketLimits(symbol=vendor_symbol)

        return self._limits_of(market, symbol=vendor_symbol)

    def fetch_all_market_limits(self) -> dict[str, MarketLimits]:
        """Limits for every symbol this session's default type lists.

        Keyed by both the venue's own id (``BTCUSDT``) and ccxt's unified symbol
        (``BTC/USDT:USDT``), because ``INST.PRODUCT_XREF`` stores one or the
        other depending on the venue and either must resolve.

        The pinned default type, or the preset's ``default_type``, drops every
        other market. Bybit prints ``BTCUSDT`` for the spot pair and the
        perpetual, and only one of those is the instrument being traded.
        """
        default_type = self._default_type or self._config.preset.default_type
        out: dict[str, MarketLimits] = {}
        for market in self.exchange.markets.values():
            if default_type and not market.get(default_type):
                continue
            for key in (market.get("id"), market.get("symbol")):
                if key:
                    out[key] = self._limits_of(market, symbol=key)
        return out

    @staticmethod
    def _limits_of(market: dict, *, symbol: str) -> MarketLimits:
        limits = market.get("limits") or {}
        return MarketLimits(
            symbol=symbol,
            min_qty=_as_float((limits.get("amount") or {}).get("min")),
            min_notional=_as_float((limits.get("cost") or {}).get("min")),
        )

    def create_market_order(self, vendor_symbol: str, side: str, qty: float) -> dict:
        """Submit a market order. ``side`` is ``'buy'`` or ``'sell'`` (ccxt lowercase)."""
        try:
            return self.exchange.create_order(vendor_symbol, "market", side, qty)
        except ccxt.InsufficientFunds as exc:
            raise BrokerConnectionError(f"insufficient funds: {exc}") from exc
        except ccxt.InvalidOrder as exc:
            raise BrokerConnectionError(f"invalid order: {exc}") from exc
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="create_order") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"create_order failed: {exc}") from exc

    def cancel_order(self, vendor_order_id: str, vendor_symbol: str | None = None) -> dict:
        try:
            return self.exchange.cancel_order(vendor_order_id, vendor_symbol)
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="cancel_order") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"cancel_order failed: {exc}") from exc

    def fetch_open_orders(self, vendor_symbol: str | None = None) -> list[dict]:
        try:
            return self.exchange.fetch_open_orders(vendor_symbol)
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_open_orders") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_open_orders failed: {exc}") from exc

    def fetch_order(self, vendor_order_id: str, vendor_symbol: str) -> dict:
        """Read one order's status."""
        params = dict(self._config.preset.fetch_order_params or {})
        try:
            return self.exchange.fetch_order(
                vendor_order_id, vendor_symbol, params=params or None
            )
        except ccxt.OrderNotFound as exc:
            raise OrderNotFoundError(f"order not found: {exc}") from exc
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_order") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_order failed: {exc}") from exc

    def fetch_last_price(self, vendor_symbol: str) -> float | None:
        """Best-effort mark/last price for notional estimates."""
        try:
            ticker = self.exchange.fetch_ticker(vendor_symbol)
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_ticker") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_ticker failed: {exc}") from exc
        for key in ("last", "close", "bid", "ask"):
            val = ticker.get(key)
            if val is not None:
                return float(val)
        return None

    def fetch_balances(self) -> list[dict]:
        """Per-currency cash: ``code``, ``free``, ``used``, ``total``.

        Currencies with nothing in them are dropped — a unified account reports
        every listed asset, and a table of a hundred zeroes hides the one row
        that matters. A currency held only as margin (``free`` 0, ``used`` > 0)
        is kept, since that is a real holding.
        """
        try:
            raw = self.exchange.fetch_balance()
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_balance") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_balance failed: {exc}") from exc

        totals = raw.get("total") or {}
        free = raw.get("free") or {}
        used = raw.get("used") or {}
        rows = []
        for code in sorted(totals):
            row = {
                "code": code,
                "free": _as_float(free.get(code)),
                "used": _as_float(used.get(code)),
                "total": _as_float(totals.get(code)),
            }
            if row["total"] or row["free"] or row["used"]:
                rows.append(row)
        return rows

    def fetch_open_positions(self) -> list[dict]:
        """Every open position on the account, signed and flattened.

        Not filtered to symbols the platform deploys on: a position opened by
        hand, or left behind by a stopped deployment, is exactly what an
        operator needs to see. Zero-size entries are dropped — exchanges return
        placeholder rows for symbols once traded.
        """
        try:
            positions = self.exchange.fetch_positions()
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_positions") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_positions failed: {exc}") from exc

        rows = []
        for pos in positions:
            info = pos.get("info") or {}
            qty = _as_float(pos.get("contracts"))
            if qty is None:
                qty = _as_float(info.get("size")) or 0.0
            if not qty:
                continue
            side = pos.get("side")
            rows.append(
                {
                    # Prefer the exchange's own symbol so it matches
                    # INST.PRODUCT_XREF and the deployment rows beside it.
                    "symbol": info.get("symbol") or pos.get("symbol") or "",
                    "unified_symbol": pos.get("symbol"),
                    "qty": -abs(qty) if side == "short" else abs(qty),
                    "side": side,
                    "entry_price": _as_float(pos.get("entryPrice")),
                    "mark_price": _as_float(pos.get("markPrice")),
                    "notional": _as_float(pos.get("notional")),
                    "unrealized_pnl": _as_float(pos.get("unrealizedPnl")),
                    "leverage": _as_float(pos.get("leverage")),
                    "liquidation_price": _as_float(pos.get("liquidationPrice")),
                }
            )
        return rows

    def fetch_position_qty(self, vendor_symbol: str) -> float:
        """Signed position size: positive for long, negative for short.

        A spot instrument has no position row. The holding is the base-coin
        balance. A contract instrument is the signed ``fetch_positions`` size.

        ``fetch_positions`` returns ``symbol`` in ccxt's unified format (e.g.
        ``BTC/USDT:USDT``) while ``vendor_symbol`` is the raw exchange symbol
        (e.g. ``BTCUSDT``) from INST.PRODUCT_XREF — compare against both that
        and the raw ``info.symbol`` ccxt preserves from the exchange response.
        """
        if self._default_type == "spot":
            return self._base_balance(vendor_symbol)
        try:
            positions = self.exchange.fetch_positions([vendor_symbol])
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_positions failed: {exc}") from exc
        try:
            unified_symbol = self.exchange.market(vendor_symbol)["symbol"]
        except ccxt.BadSymbol:
            unified_symbol = vendor_symbol
        for pos in positions:
            info = pos.get("info") or {}
            if vendor_symbol not in (pos.get("symbol"), unified_symbol, info.get("symbol")):
                continue
            contracts = pos.get("contracts")
            if contracts is not None:
                qty = float(contracts)
            else:
                size = info.get("size")
                qty = float(size) if size is not None else 0.0
            if pos.get("side") == "short":
                qty = -abs(qty)
            return qty
        return 0.0

    def _base_balance(self, vendor_symbol: str) -> float:
        """Total balance of the market's base coin — the spot holding."""
        try:
            market = self.exchange.market(vendor_symbol)
            raw = self.exchange.fetch_balance()
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_balance") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_balance failed: {exc}") from exc
        base = market.get("base")
        if not base:
            raise BrokerConnectionError(f"no base currency for {vendor_symbol}")
        qty = _as_float((raw.get("total") or {}).get(base))
        return qty or 0.0
