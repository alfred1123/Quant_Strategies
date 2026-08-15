"""Pydantic schemas for live apply — Phase 1.7."""

from uuid import UUID

from pydantic import BaseModel

from quant.trade.models.order import IntendedAction


class ApplyReport(BaseModel):
    """Result of a single live-apply cycle."""

    deployment_id: UUID
    deployment_vid: int
    action: IntendedAction
    vendor_symbol: str
    signal: float
    position_qty: float
    order_success: bool | None = None
    vendor_order_id: str | None = None
    filled_qty: float | None = None
    avg_price: float | None = None
    fee: float | None = None
    message: str
    # Which price series produced `signal` — e.g. "price_bar:bybit" or
    # "provider". Strategy parameters are fitted on provider history, so a
    # scheduled apply trades on a different series than it was optimized on;
    # recording the input is what makes that divergence traceable afterwards.
    bar_source: str | None = None
