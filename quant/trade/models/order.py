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
    #: The key's IP allowlist admits none of this platform's egress routes.
    IP_NOT_ALLOWED = "IP_NOT_ALLOWED"
    #: The venue will not offer this product to the account (e.g. Bybit 10024).
    REGION_RESTRICTED = "REGION_RESTRICTED"
    KEY_READ_ONLY = "KEY_READ_ONLY"

    @property
    def requires_operator_fix(self) -> bool:
        """True when no retry can succeed until someone changes something.

        Both the retry executor (give up after one attempt) and the scheduler
        (pause rather than spend the tick budget) ask this, so the answer lives
        with the reason instead of being decided twice. Every reason so far is
        a setting — a deployment's qty, or a key's allowlist, permissions, or
        account region — that the next tick would meet unchanged.
        """
        return True


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
