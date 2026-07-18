"""Shared ccxt trade adapter for REST crypto brokers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from quant.trade.adapters.base import TradeAdapter
from quant.trade.brokers.ccxt.config import CcxtExchangePreset
from quant.trade.brokers.ccxt.confirm import confirm_market_order
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import (
    BrokerConnectionError,
    SymbolMappingError,
    TradeValidationError,
)
from quant.trade.models.order import (
    IntendedAction,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)
from quant.trade.models.session import BrokerSessionState

if TYPE_CHECKING:
    from quant.data.instruments import InstrumentCache

logger = logging.getLogger(__name__)


def create_ccxt_adapter(
    *,
    preset: CcxtExchangePreset,
    api_key: str,
    api_secret: str,
    paper: bool,
    inst_cache: InstrumentCache,
    demo: bool = False,
) -> CcxtTradeAdapter:
    """Build a ccxt adapter from a REFDATA.APP preset."""
    return CcxtTradeAdapter(
        api_key=api_key,
        api_secret=api_secret,
        paper=paper,
        inst_cache=inst_cache,
        preset=preset,
        demo=demo,
    )


class CcxtTradeAdapter(TradeAdapter):
    """ccxt adapter — dry-run validates credentials and symbol only."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        paper: bool,
        inst_cache: InstrumentCache,
        preset: CcxtExchangePreset,
        demo: bool = False,
    ) -> None:
        self._inst = inst_cache
        self._exchange_label = preset.exchange_label
        self._gateway = CcxtTradeGateway(
            CcxtSessionConfig(
                api_key=api_key,
                api_secret=api_secret,
                preset=preset,
                paper=paper,
                demo=demo,
            )
        )
        self._paper = paper

    @property
    def gateway(self) -> CcxtTradeGateway:
        return self._gateway

    def connect(self) -> None:
        self._gateway.connect()

    def disconnect(self) -> None:
        self._gateway.disconnect()

    def health(self) -> BrokerSessionState:
        return self._gateway.health()

    def unlock_live_trading(self, trade_password: str) -> None:
        if not self._paper and trade_password:
            logger.debug("%s live unlock not required for ccxt v1", self._exchange_label)

    def _require_vendor_symbol(self, internal_cusip: str, app_id: int) -> str:
        vendor_symbol = self._inst.resolve_internal_cusip(internal_cusip, app_id)
        if vendor_symbol is not None:
            return vendor_symbol
        if self._inst.get_product_by_cusip(internal_cusip) is None:
            raise SymbolMappingError(
                f"unknown product internal_cusip={internal_cusip!r}"
            )
        raise SymbolMappingError(
            f"no INST.PRODUCT_XREF for {internal_cusip!r} app_id={app_id}"
        )

    def validate_for_dry_run(self, internal_cusip: str, app_id: int) -> str:
        """Validate xref + broker connectivity. Returns vendor symbol."""
        vendor_symbol = self._require_vendor_symbol(internal_cusip, app_id)
        self._gateway.validate_credentials()
        if not self._gateway.market_exists(vendor_symbol):
            raise SymbolMappingError(
                f"vendor symbol {vendor_symbol!r} not listed on {self._exchange_label}"
            )
        return vendor_symbol

    def get_position_qty(self, symbol: str) -> float:
        return self._gateway.fetch_position_qty(symbol)

    def get_last_price(self, symbol: str) -> float | None:
        """Best-effort last traded price for notional estimates; None if unavailable."""
        try:
            return self._gateway.fetch_last_price(symbol)
        except BrokerConnectionError:
            return None

    def place_order(self, req: OrderRequest) -> OrderResult:
        if req.order_type is not OrderType.MARKET:
            raise TradeValidationError(
                f"{req.order_type.value} orders not supported by the ccxt adapter — market only"
            )
        side = "buy" if req.side == OrderSide.BUY else "sell"
        try:
            raw = self._gateway.create_market_order(req.symbol, side, req.qty)
        except BrokerConnectionError as exc:
            return OrderResult(
                success=False, vendor_order_id=None, message=str(exc),
                side=req.side, requested_qty=req.qty,
            )
        order_id = raw.get("id")
        if order_id is None:
            return OrderResult(
                success=False, vendor_order_id=None,
                message="create_order returned no order id",
                raw_status=raw.get("status"),
                side=req.side, requested_qty=req.qty,
            )
        return confirm_market_order(
            self._gateway, req=req, vendor_order_id=str(order_id),
        )

    def cancel_order(self, vendor_order_id: str, vendor_symbol: str | None = None) -> OrderResult:
        try:
            raw = self._gateway.cancel_order(vendor_order_id, vendor_symbol)
        except BrokerConnectionError as exc:
            return OrderResult(success=False, vendor_order_id=vendor_order_id, message=str(exc))
        return OrderResult(
            success=True,
            vendor_order_id=vendor_order_id,
            message="order canceled",
            raw_status=raw.get("status"),
        )

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        return self._gateway.fetch_open_orders(symbol)

    def execute_action(
        self,
        symbol: str,
        action: IntendedAction,
        qty: float,
        position_qty: float,
    ) -> OrderResult | None:
        """Translate a precomputed action + position into at most one order."""
        match action:
            case IntendedAction.HOLD:
                return None
            case IntendedAction.BUY:
                order_req = OrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY)
            case IntendedAction.OPEN_SHORT:
                order_req = OrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL)
            case IntendedAction.SELL:
                order_req = OrderRequest(symbol=symbol, qty=abs(position_qty), side=OrderSide.SELL)
            case IntendedAction.CLOSE_SHORT:
                order_req = OrderRequest(symbol=symbol, qty=abs(position_qty), side=OrderSide.BUY)
            case _:  # pragma: no cover — exhaustive per IntendedAction
                raise ValueError(f"unhandled intended_side action: {action!r}")
        if order_req.qty <= 0:
            return None
        return self.place_order(order_req)
