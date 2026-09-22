"""Order value objects shared by broker adapters."""

from dataclasses import dataclass
from enum import Enum, StrEnum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderRejectReason(StrEnum):
    """Why an order was refused, typed where the refusal was decided.

    Carried on :class:`OrderResult` so policy reads a value instead of grepping
    the message text back apart — the message exists for humans.
    """

    SIZE_BELOW_MINIMUM = "SIZE_BELOW_MINIMUM"

    @property
    def requires_operator_fix(self) -> bool:
        """True when no retry can succeed until someone edits the deployment.

        Both the retry executor (give up after one attempt) and the scheduler
        (pause rather than spend the tick budget) ask this, so the answer lives
        with the reason instead of being decided twice.
        """
        return self is OrderRejectReason.SIZE_BELOW_MINIMUM


class IntendedAction(StrEnum):
    """Position-aware action from ``TradeAdapter.intended_side``.

    Richer than :class:`OrderSide` — OPEN_SHORT/CLOSE_SHORT carry the position
    context; execution collapses them back to a raw buy/sell order side.
    """

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    OPEN_SHORT = "OPEN_SHORT"
    CLOSE_SHORT = "CLOSE_SHORT"

    def order_side(self) -> "OrderSide | None":
        """Raw exchange side this action executes as; ``None`` for HOLD."""
        if self in (IntendedAction.BUY, IntendedAction.CLOSE_SHORT):
            return OrderSide.BUY
        if self in (IntendedAction.SELL, IntendedAction.OPEN_SHORT):
            return OrderSide.SELL
        return None


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    qty: float
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None


@dataclass(frozen=True)
class OrderResult:
    success: bool
    vendor_order_id: str | None
    message: str
    #: Set when the refusal was classified at its source; ``None`` for a broker
    #: error we only have prose for.
    reason: OrderRejectReason | None = None
    raw_status: str | None = None
    side: OrderSide | None = None
    requested_qty: float | None = None
    filled_qty: float | None = None
    avg_price: float | None = None
    fee: float | None = None
