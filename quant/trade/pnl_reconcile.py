"""Strategy-level live return for one bar.

The position, fill gap, and fee terms are the three components in
[Deployment performance reconcile](docs/design/deployment-performance-reconcile.md)
§3.1. ``LIVE_RETURN`` is their sum.

``BACKTEST_RETURN`` is the ``pnl`` column from ``Performance`` replayed on
the same closes (``quant/strategy/performance.py``). Pass that number into
the snapshot write. This module does not reimplement the engine.

Fee conversion uses the raw ``FEE_AMT`` and ``FEE_CCY_CD`` stored on the
fill. A quote fee is the cost. A base-coin fee is the cost times the fill
price. Any other coin, or a missing currency on a non-zero cost, leaves
the fee term and the live return null. A zero or absent fee is zero.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


def _dec(value: Decimal | str | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _ccy(value: str | None) -> str:
    return (value or "").strip().upper()


@dataclass(frozen=True)
class StrategyFill:
    """One confirmed fill that belongs to the slot before this bar.

    ``side`` is ``BUY`` or ``SELL``. ``qty`` is unsigned. ``fee_amt`` is the
    raw broker cost in ``fee_ccy``, the coin the venue charged.
    """

    side: str
    qty: Decimal | str | float
    price: Decimal | str | float
    fee_amt: Decimal | str | float | None = None
    fee_ccy: str | None = None


@dataclass(frozen=True)
class StrategyBarReturn:
    """One deployment × bar, on the backtest's −1 / 0 / +1 scale."""

    unit_notional_amt: Decimal
    target_position: Decimal
    position_return: Decimal
    fill_gap_return: Decimal
    fee_return: Decimal | None
    live_return: Decimal | None


def fee_in_quote(
    *,
    fee_amt: Decimal | str | float | None,
    fee_ccy: str | None,
    fill_price: Decimal | str | float,
    quote_ccy: str,
    base_ccy: str,
) -> Decimal | None:
    """Broker fee in the product's quote currency.

    Returns ``0`` when the cost is missing or zero. Returns ``None`` when a
    non-zero cost is not in ``quote_ccy`` or ``base_ccy``. A third coin is
    left unconverted. ``base_ccy`` is supplied by the caller; the product
    master records the quote only.
    """
    if fee_amt is None:
        return Decimal(0)
    cost = _dec(fee_amt)
    if cost == 0:
        return Decimal(0)

    charged = _ccy(fee_ccy)
    quote = _ccy(quote_ccy)
    base = _ccy(base_ccy)
    price = _dec(fill_price)
    if charged and charged == quote:
        return cost
    if charged and base and charged == base and price > 0:
        return cost * price

    logger.debug(
        "fee currency %s is not quote %s or base %s",
        charged or None,
        quote or None,
        base or None,
    )
    return None


def _signed_qty(side: str, qty: Decimal) -> Decimal:
    label = side.strip().upper()
    if label == "BUY":
        return qty
    if label == "SELL":
        return -qty
    raise ValueError(f"fill side must be BUY or SELL, got {side!r}")


def strategy_bar_return(
    *,
    qty: Decimal | str | float,
    target_qty: Decimal | str | float,
    close_k: Decimal | str | float,
    close_k1: Decimal | str | float,
    quote_ccy: str,
    base_ccy: str,
    fills: tuple[StrategyFill, ...] | list[StrategyFill] = (),
) -> StrategyBarReturn:
    """Price bar ``k+1`` from the target chosen at slot ``s_k``.

    ``qty`` is the deployment quantity of one full unit. ``target_qty`` is
    ``INTENT.TARGET_QTY``. ``close_k`` and ``close_k1`` are the closes of
    bar ``k`` and bar ``k+1``. ``UNIT_NOTIONAL_AMT`` is ``qty × close_k``.

    The managed flag is stored beside this result. A pause does not flatten,
    so an unmanaged bar can still be priced from the last target.
    """
    unit_qty = _dec(qty)
    target = _dec(target_qty)
    mark = _dec(close_k)
    nxt = _dec(close_k1)
    unit_notional = unit_qty * mark
    if unit_notional <= 0:
        raise ValueError("unit notional must be positive")

    position = target * (nxt - mark) / unit_notional
    gap_quote = Decimal(0)
    fee_quote = Decimal(0)
    fee_known = True
    for fill in fills:
        fill_qty = _dec(fill.qty)
        fill_px = _dec(fill.price)
        gap_quote += _signed_qty(fill.side, fill_qty) * (mark - fill_px)
        converted = fee_in_quote(
            fee_amt=fill.fee_amt,
            fee_ccy=fill.fee_ccy,
            fill_price=fill_px,
            quote_ccy=quote_ccy,
            base_ccy=base_ccy,
        )
        if converted is None:
            fee_known = False
        else:
            fee_quote += converted

    gap = gap_quote / unit_notional
    if fee_known:
        fee_return = -fee_quote / unit_notional
        live = position + gap + fee_return
    else:
        fee_return = None
        live = None

    return StrategyBarReturn(
        unit_notional_amt=unit_notional,
        target_position=target / unit_qty,
        position_return=position,
        fill_gap_return=gap,
        fee_return=fee_return,
        live_return=live,
    )
