"""Poll-to-confirm helpers for ccxt market orders."""

from __future__ import annotations

import time
from dataclasses import dataclass

from quant.trade.brokers.ccxt.gateway import CcxtTradeGateway
from quant.trade.errors import BrokerConnectionError, OrderNotFoundError
from quant.trade.models.order import OrderRejectReason, OrderRequest, OrderResult

_CONFIRM_DELAYS_S = (0.3, 0.6, 1.2, 2.4, 3.5)


@dataclass(frozen=True)
class _FillStatus:
    """Parsed terminal state from a ccxt order dict — NOT an OrderResult."""

    success: bool
    vendor_order_id: str | None
    message: str
    raw_status: str | None
    reason: OrderRejectReason | None = None
    filled_qty: float | None = None
    avg_price: float | None = None
    fee: float | None = None
    fee_ccy: str | None = None


def _fee_ccy(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_fee(order: dict) -> tuple[float | None, str | None]:
    """Raw ``fee.cost`` and ``fee.currency``. The cost is not converted."""
    fee = order.get("fee")
    if isinstance(fee, dict):
        cost = fee.get("cost")
        amount = float(cost) if cost is not None else None
        return amount, _fee_ccy(fee.get("currency"))
    return None, None


def _parse_terminal(order: dict, *, vendor_order_id: str | None) -> _FillStatus | None:
    """Return parsed fill status if the order reached a terminal state, else ``None``."""
    status = (order.get("status") or "").lower()
    filled = float(order.get("filled") or 0)
    avg = order.get("average")
    avg_price = float(avg) if avg is not None else None
    fee, fee_ccy = _extract_fee(order)
    oid = str(order.get("id")) if order.get("id") is not None else vendor_order_id

    if status == "closed" or (
        filled > 0 and status in ("canceled", "cancelled", "expired")
    ):
        return _FillStatus(
            success=True,
            vendor_order_id=oid,
            message="order filled",
            raw_status=status or "closed",
            filled_qty=filled,
            avg_price=avg_price,
            fee=fee,
            fee_ccy=fee_ccy,
        )
    if status == "rejected" or (
        filled == 0 and status in ("canceled", "cancelled", "expired")
    ):
        return _FillStatus(
            success=False,
            vendor_order_id=oid,
            message=f"order rejected status={status or 'unknown'}",
            raw_status=status,
            reason=OrderRejectReason.VENUE_REJECTED,
        )
    return None


def _unconfirmed(
    req: OrderRequest, vendor_order_id: str, last_status: str | None,
) -> OrderResult:
    """The fill is unknown. The executor cancels this id before placing again."""
    return OrderResult(
        success=False,
        vendor_order_id=vendor_order_id,
        message=(
            f"fill unconfirmed after {sum(_CONFIRM_DELAYS_S):.1f}s — "
            f"vendor_order_id={vendor_order_id} requires manual reconciliation"
            + (f" (last status={last_status!r})" if last_status else "")
        ),
        raw_status=last_status,
        side=req.side,
        requested_qty=req.qty,
    )


def confirm_market_order(
    gateway: CcxtTradeGateway,
    *,
    req: OrderRequest,
    vendor_order_id: str,
) -> OrderResult:
    """Poll ``fetch_order`` until a terminal outcome or the backoff budget expires.

    This is the **single point** that builds ``OrderResult`` for the fill path.
    The gateway returns raw dicts; this function owns the domain translation.
    A typed connection error is that outcome and keeps ``exc.reason``. An
    untyped one is the same unconfirmed result as an exhausted poll.
    """
    last_status: str | None = None
    for delay in _CONFIRM_DELAYS_S:
        time.sleep(delay)
        try:
            order = gateway.fetch_order(vendor_order_id, req.symbol)
        except OrderNotFoundError:
            continue
        except BrokerConnectionError as exc:
            if exc.reason is not None:
                return OrderResult(
                    success=False,
                    vendor_order_id=vendor_order_id,
                    message=str(exc),
                    reason=exc.reason,
                    side=req.side,
                    requested_qty=req.qty,
                )
            return _unconfirmed(req, vendor_order_id, last_status)
        last_status = order.get("status")
        fill = _parse_terminal(order, vendor_order_id=vendor_order_id)
        if fill is not None:
            return OrderResult(
                success=fill.success,
                vendor_order_id=fill.vendor_order_id,
                message=fill.message,
                reason=fill.reason,
                raw_status=fill.raw_status,
                side=req.side,
                requested_qty=req.qty,
                filled_qty=fill.filled_qty,
                avg_price=fill.avg_price,
                fee=fill.fee,
                fee_ccy=fill.fee_ccy,
            )

    return _unconfirmed(req, vendor_order_id, last_status)
