"""ccxt gateway shared by REST crypto brokers (Bybit, Binance, …)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import ccxt

from quant.trade.brokers.ccxt.config import CcxtExchangePreset, ConnectParams
from quant.trade.errors import BrokerConnectionError
from quant.trade.models.session import BrokerSessionState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CcxtSessionConfig:
    api_key: str
    api_secret: str
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
        exchange_cls = getattr(ccxt, preset.exchange_id)
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

    def fetch_position_qty(self, vendor_symbol: str) -> float:
        try:
            positions = self.exchange.fetch_positions([vendor_symbol])
        except ccxt.BaseError as exc:
            raise BrokerConnectionError(f"fetch_positions failed: {exc}") from exc
        for pos in positions:
            if pos.get("symbol") == vendor_symbol:
                contracts = pos.get("contracts")
                if contracts is not None:
                    return float(contracts)
                info = pos.get("info") or {}
                size = info.get("size")
                if size is not None:
                    return float(size)
        return 0.0
