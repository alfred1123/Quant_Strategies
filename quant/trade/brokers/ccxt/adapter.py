"""Shared ccxt trade adapter for REST crypto brokers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from quant.trade.adapters.base import TradeAdapter
from quant.trade.brokers.ccxt.config import CcxtExchangePreset
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import SymbolMappingError
from quant.trade.models.order import OrderRequest, OrderResult
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
            raise ValueError(
                f"vendor symbol {vendor_symbol!r} not listed on {self._exchange_label}"
            )
        return vendor_symbol

    def get_position_qty(self, symbol: str) -> float:
        return self._gateway.fetch_position_qty(symbol)

    def place_order(self, req: OrderRequest) -> OrderResult:
        raise NotImplementedError("live order placement is Phase 1.7")

    def cancel_order(self, vendor_order_id: str) -> OrderResult:
        raise NotImplementedError("live order placement is Phase 1.7")

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        raise NotImplementedError("live order placement is Phase 1.7")

    def apply_signal(
        self, symbol: str, signal: float, qty: float
    ) -> OrderResult | None:
        raise NotImplementedError("live order placement is Phase 1.7")

    @staticmethod
    def intended_side(signal: float, position_qty: float) -> str:
        """Map signal + current position to the action dry-run would take."""
        sig = int(round(signal))
        if sig > 0:
            return "BUY" if position_qty == 0 else "HOLD"
        if sig == 0:
            return "SELL" if position_qty > 0 else "HOLD"
        if position_qty > 0:
            return "SELL"
        return "HOLD"
