"""Order value objects shared by broker adapters."""

from dataclasses import dataclass
from enum import Enum, StrEnum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


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
    raw_status: str | None = None
    side: OrderSide | None = None
    requested_qty: float | None = None
    filled_qty: float | None = None
    avg_price: float | None = None
    fee: float | None = None
