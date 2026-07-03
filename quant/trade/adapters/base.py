"""Abstract broker session and trade adapter interfaces."""

from abc import ABC, abstractmethod

from quant.trade.models.order import OrderRequest, OrderResult
from quant.trade.models.session import BrokerSessionState


class BrokerSession(ABC):
    """Lifecycle: connect → (optional unlock) → use → disconnect."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> BrokerSessionState: ...

    def __enter__(self) -> "BrokerSession":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()


class TradeAdapter(BrokerSession):
    """Broker-agnostic trading surface for the execution loop."""

    @abstractmethod
    def unlock_live_trading(self, trade_password: str) -> None:
        """Required for REAL env; no-op or skip for paper."""

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, vendor_order_id: str) -> OrderResult: ...

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_position_qty(self, symbol: str) -> float: ...

    @abstractmethod
    def apply_signal(
        self, symbol: str, signal: float, qty: float
    ) -> OrderResult | None:
        """Translate {-1,0,1} signal to orders; None if no action."""

    @abstractmethod
    def validate_for_dry_run(self, internal_cusip: str, app_id: int) -> str:
        """Validate credentials + symbol mapping. Returns vendor symbol."""

    @staticmethod
    def intended_side(signal: float, position_qty: float) -> str:
        """Map ``(signal, signed_position)`` to an action.

        Handles long, flat, and short positions::

            signal  position   →  action
            ──────  ─────────  ─  ──────
             +1      0 (flat)  →  BUY
             +1     >0 (long)  →  HOLD          (already long)
             +1     <0 (short) →  CLOSE_SHORT   (cover before buying)
              0     >0 (long)  →  SELL           (flatten)
              0      0 (flat)  →  HOLD
              0     <0 (short) →  CLOSE_SHORT    (flatten)
             -1     >0 (long)  →  SELL
             -1      0 (flat)  →  OPEN_SHORT     (enter short)
             -1     <0 (short) →  HOLD           (already short)
        """
        sig = int(round(signal))
        if sig > 0:
            if position_qty < 0:
                return "CLOSE_SHORT"
            return "BUY" if position_qty == 0 else "HOLD"
        if sig == 0:
            if position_qty > 0:
                return "SELL"
            if position_qty < 0:
                return "CLOSE_SHORT"
            return "HOLD"
        # sig < 0
        if position_qty > 0:
            return "SELL"
        if position_qty == 0:
            return "OPEN_SHORT"
        return "HOLD"
