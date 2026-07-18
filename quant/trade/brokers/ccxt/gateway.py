"""ccxt gateway shared by REST crypto brokers (Bybit, Binance, …)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import ccxt

from quant.trade.brokers.ccxt.config import CcxtExchangePreset, ConnectParams
from quant.trade.errors import BrokerConnectionError, OrderNotFoundError
from quant.trade.models.session import BrokerSessionState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CcxtSessionConfig:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    preset: CcxtExchangePreset
    paper: bool = True
    demo: bool = False


class CcxtTradeGateway:
    """Thin ccxt wrapper — load markets, balance, positions; no orders in dry-run."""

    def __init__(self, config: CcxtSessionConfig) -> None:
        self._config = config
        self._exchange: ccxt.Exchange | None = None

    @property
    def exchange(self) -> ccxt.Exchange:
        if self._exchange is None:
            raise BrokerConnectionError("exchange not connected")
        return self._exchange

    def connect(self) -> None:
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
        if preset.default_type:
            params["options"] = {"defaultType": preset.default_type}
        self._exchange = exchange_cls(params)
        connect_params = ConnectParams(paper=self._config.paper, demo=self._config.demo)
        preset.wire(self._exchange, connect_params)
        try:
            self._exchange.load_markets()
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="load_markets") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"broker unreachable during load_markets: {exc}") from exc
        logger.info(
            "ccxt %s connected (paper=%s, demo=%s, markets=%d)",
            preset.exchange_id,
            self._config.paper,
            self._config.demo,
            len(self._exchange.markets),
        )

    def _auth_error(self, exc: ccxt.AuthenticationError, *, phase: str) -> BrokerConnectionError:
        hint = ""
        auth_hint = self._config.preset.auth_hint
        if auth_hint is not None:
            hint = auth_hint(
                ConnectParams(paper=self._config.paper, demo=self._config.demo)
            )
        return BrokerConnectionError(f"authentication failed during {phase}: {exc}.{hint}")

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

    def validate_credentials(self) -> None:
        """Read-only check — load markets and fetch balance."""
        try:
            self.exchange.fetch_balance()
        except ccxt.AuthenticationError as exc:
            raise self._auth_error(exc, phase="fetch_balance") from exc
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"broker unreachable: {exc}") from exc

    def market_exists(self, vendor_symbol: str) -> bool:
        if vendor_symbol in self.exchange.markets:
            return True
        try:
            self.exchange.market(vendor_symbol)
            return True
        except ccxt.BadSymbol:
            return False

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

    def fetch_position_qty(self, vendor_symbol: str) -> float:
        """Signed position size: positive for long, negative for short.

        ``fetch_positions`` returns ``symbol`` in ccxt's unified format (e.g.
        ``BTC/USDT:USDT``) while ``vendor_symbol`` is the raw exchange symbol
        (e.g. ``BTCUSDT``) from INST.PRODUCT_XREF — compare against both that
        and the raw ``info.symbol`` ccxt preserves from the exchange response.
        """
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
