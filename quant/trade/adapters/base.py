"""Abstract broker session and trade adapter interfaces."""

from abc import ABC, abstractmethod

from quant.trade.models.order import IntendedAction, OrderRequest, OrderResult
from quant.trade.models.session import BrokerSessionState

# Positions smaller than this are float noise, not real exposure — treat as flat.
_FLAT_EPS = 1e-9


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
    def cancel_order(
        self, vendor_order_id: str, vendor_symbol: str | None = None
    ) -> OrderResult:
        """Cancel one order. Most ccxt exchanges require the symbol too."""

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_position_qty(self, symbol: str) -> float: ...

    def get_last_price(self, symbol: str) -> float | None:
        """Best-effort last traded price for notional estimates; ``None`` if unavailable."""
        return None

    @abstractmethod
    def execute_action(
        self,
        symbol: str,
        action: IntendedAction,
        qty: float,
        position_qty: float,
    ) -> OrderResult | None:
        """Translate a precomputed action + signed position into at most one order.

        ``position_qty`` must be the same reading used to derive ``action`` via
        :meth:`intended_side` — callers that already fetched the position (e.g.
        for audit purposes) pass it through here instead of triggering a second
        broker read, so the executed order always matches the decided action.
        """

    def apply_signal(
        self, symbol: str, signal: float, qty: float
    ) -> OrderResult | None:
        """Convenience: fetch position, decide action, execute — single call."""
        position_qty = self.get_position_qty(symbol)
        action = self.intended_side(signal, position_qty)
        return self.execute_action(symbol, action, qty, position_qty)

    @abstractmethod
    def validate_for_dry_run(self, internal_cusip: str, app_id: int) -> str:
        """Validate credentials + symbol mapping. Returns vendor symbol."""

    @staticmethod
    def intended_side(signal: float, position_qty: float) -> IntendedAction:
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

        Positions within ``_FLAT_EPS`` of zero are treated as flat so float
        dust never triggers a flatten order the exchange would reject.
        """
        sig = int(round(signal))
        if abs(position_qty) <= _FLAT_EPS:
            position_qty = 0.0
        if sig > 0:
            if position_qty < 0:
                return IntendedAction.CLOSE_SHORT
            return IntendedAction.BUY if position_qty == 0 else IntendedAction.HOLD
        if sig == 0:
            if position_qty > 0:
                return IntendedAction.SELL
            if position_qty < 0:
                return IntendedAction.CLOSE_SHORT
            return IntendedAction.HOLD
        # sig < 0
        if position_qty > 0:
            return IntendedAction.SELL
        if position_qty == 0:
            return IntendedAction.OPEN_SHORT
        return IntendedAction.HOLD
