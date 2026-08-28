"""Pydantic schemas for the live account snapshot — read-only broker state."""

from pydantic import BaseModel


class BalanceRow(BaseModel):
    """One currency's cash on the account."""

    code: str
    free: float | None = None
    used: float | None = None
    total: float | None = None


class PositionRow(BaseModel):
    """One open position, as the exchange reports it."""

    #: Raw exchange symbol (e.g. ``BTCUSDT``) — matches INST.PRODUCT_XREF.
    symbol: str
    #: ccxt's unified form (e.g. ``BTC/USDT:USDT``), kept for support questions.
    unified_symbol: str | None = None
    #: Signed size: positive long, negative short.
    qty: float
    side: str | None = None
    entry_price: float | None = None
    mark_price: float | None = None
    notional: float | None = None
    unrealized_pnl: float | None = None
    leverage: float | None = None
    liquidation_price: float | None = None


class AccountSnapshot(BaseModel):
    """What one credential holds right now, read live from the exchange.

    Every field comes from the broker, nothing from our tables — the point is to
    show reality rather than what we believe. ``paper`` records which
    environment answered, because the same credential can address a demo
    account and a real one and the two hold different money.
    """

    api_credential_id: int
    app_id: int
    paper: bool
    balances: list[BalanceRow]
    positions: list[PositionRow]
