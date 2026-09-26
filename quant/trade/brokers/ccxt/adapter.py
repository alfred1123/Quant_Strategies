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
from quant.trade.brokers.ccxt.routing import KeyRouter
from quant.trade.models.key_profile import KeyProfile
from quant.trade.models.order import (
    IntendedAction,
    OrderRejectReason,
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
    key_router: KeyRouter | None = None,
) -> CcxtTradeAdapter:
    """Build a ccxt adapter from a REFDATA.APP preset.

    ``key_router=None`` routes without a cache: every connect re-asks the venue.
    """
    return CcxtTradeAdapter(
        api_key=api_key,
        api_secret=api_secret,
        paper=paper,
        inst_cache=inst_cache,
        preset=preset,
        demo=demo,
        key_router=key_router or KeyRouter(None),
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
        key_router: KeyRouter,
        demo: bool = False,
    ) -> None:
        self._inst = inst_cache
        self._session = CcxtSessionConfig(
            api_key=api_key,
            api_secret=api_secret,
            preset=preset,
            paper=paper,
            demo=demo,
        )
        self._gateway = CcxtTradeGateway(self._session)
        self._key_router = key_router
        self._key_profile: KeyProfile | None = None
        self._default_type: str | None = None

    @property
    def gateway(self) -> CcxtTradeGateway:
        return self._gateway

    @property
    def preset(self) -> CcxtExchangePreset:
        return self._session.preset

    @property
    def key_profile(self) -> KeyProfile | None:
        return self._key_profile

    def connect(self) -> None:
        """Open the session on whichever egress route this key's allowlist accepts."""
        self._key_profile = self._key_router.connect(self._gateway)

    def disconnect(self) -> None:
        self._gateway.disconnect()

    def health(self) -> BrokerSessionState:
        return self._gateway.health()

    def unlock_live_trading(self, trade_password: str) -> None:
        if not self._session.paper and trade_password:
            logger.debug("%s live unlock not required for ccxt v1", self.preset.exchange_label)

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

    def pin_instrument(self, internal_cusip: str) -> None:
        """Point this session at the product the instrument cache names.

        ``ISSUE_TYPE`` selects the ccxt default type. A Bybit id is shared by
        the spot pair and the perpetual, and the session must not guess.
        """
        if not self.preset.default_type_by_issue:
            return
        product = self._inst.get_product_by_cusip(internal_cusip)
        issue_type = product.get("issue_type") if isinstance(product, dict) else None
        try:
            default_type = self.preset.default_type_for(issue_type)
        except ValueError as exc:
            raise TradeValidationError(str(exc)) from exc
        self._default_type = default_type
        self._gateway.pin_default_type(default_type)

    def _market_type(self) -> str:
        return self._default_type or self.preset.market_type

    def validate_for_dry_run(self, internal_cusip: str, app_id: int) -> str:
        """Validate xref + broker connectivity. Returns vendor symbol."""
        vendor_symbol = self._require_vendor_symbol(internal_cusip, app_id)
        self.pin_instrument(internal_cusip)
        self._gateway.validate_credentials()
        if not self._gateway.market_exists(vendor_symbol):
            raise SymbolMappingError(
                f"vendor symbol {vendor_symbol!r} not listed on {self.preset.exchange_label}"
            )
        return vendor_symbol

    def get_position_qty(self, symbol: str) -> float:
        return self._gateway.fetch_position_qty(symbol)

    def get_balances(self) -> list[dict]:
        return self._gateway.fetch_balances()

    def get_open_positions(self) -> list[dict]:
        return self._gateway.fetch_open_positions()

    def get_last_price(self, symbol: str) -> float | None:
        """Best-effort last traded price for notional estimates; None if unavailable."""
        try:
            return self._gateway.fetch_last_price(symbol)
        except BrokerConnectionError:
            return None

    def _undersized(self, req: OrderRequest) -> str | None:
        """Venue reject text when *req* is below the min lot or notional.

        Asked before submitting, because the qty that trips this is a deployment
        setting: every tick would place the same doomed order, and a reject
        typed here is what pauses the schedule instead of retrying it.
        """
        limits = self._gateway.fetch_market_limits(req.symbol)
        price = (
            self.get_last_price(req.symbol) if limits.min_notional is not None else None
        )
        return limits.undersized(req.qty, price)

    def _key_refusal(self) -> tuple[OrderRejectReason, str] | None:
        """What the key profile already says this order will meet.

        A read-only key, or a product the venue has refused this account
        before, fails the same way every tick; refusing here is what types the
        failure so the scheduler pauses instead of retrying.
        """
        if self._key_profile is None:
            return None
        return self._key_profile.refusal(self._market_type())

    @staticmethod
    def _rejected(
        req: OrderRequest, message: str, reason: OrderRejectReason | None
    ) -> OrderResult:
        """An order that did not reach the book, typed when the cause is known."""
        return OrderResult(
            success=False, vendor_order_id=None, message=message,
            reason=reason, side=req.side, requested_qty=req.qty,
        )

    def place_order(self, req: OrderRequest) -> OrderResult:
        if req.order_type is not OrderType.MARKET:
            raise TradeValidationError(
                f"{req.order_type.value} orders not supported by the ccxt adapter — market only"
            )
        if self.preset.default_type_by_issue and self._default_type is None:
            raise TradeValidationError(
                f"{self.preset.exchange_label} order needs the instrument ISSUE_TYPE"
            )
        side = "buy" if req.side == OrderSide.BUY else "sell"
        refusal = self._key_refusal()
        if refusal is not None:
            reason, message = refusal
            return self._rejected(req, message, reason)
        undersized = self._undersized(req)
        if undersized is not None:
            return self._rejected(req, undersized, OrderRejectReason.SIZE_BELOW_MINIMUM)
        try:
            raw = self._gateway.create_market_order(req.symbol, side, req.qty)
        except BrokerConnectionError as exc:
            if exc.reason is OrderRejectReason.REGION_RESTRICTED and self._key_profile:
                self._key_profile = self._key_router.record_restriction(
                    self._session, self._key_profile, self._market_type()
                )
            return self._rejected(req, str(exc), exc.reason)
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
