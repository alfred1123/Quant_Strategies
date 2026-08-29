"""Pydantic schemas for deployment dry-run — Phase 1.3."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from quant.trade.models.order import IntendedAction


class DryRunRequest(BaseModel):
    """Validate a deployment candidate without persisting or placing orders."""

    strategy_id: UUID
    strategy_vid: int = Field(..., ge=1)
    api_credential_id: int = Field(..., ge=1)
    app_id: int = Field(..., ge=1)
    internal_cusip: str = Field(..., min_length=1, max_length=200)
    qty: Decimal = Field(..., gt=0)
    paper: bool = True

    @field_validator("internal_cusip")
    @classmethod
    def strip_cusip(cls, v: str) -> str:
        s = v.strip().lower()
        if not s:
            raise ValueError("internal_cusip must not be empty")
        return s


class DryRunReport(BaseModel):
    """Structured dry-run outcome — no orders placed."""

    strategy_id: UUID
    strategy_vid: int
    strategy_nm: str
    internal_cusip: str
    vendor_symbol: str
    app_id: int
    paper: bool
    qty: Decimal
    signal: float
    intended_side: IntendedAction
    position_qty: float
    data_as_of: str
    notional: float | None = None
    #: Which price series the signal was computed from — ``price_bar:<venue>``
    #: or ``provider``. Shown in the report because a dry run is only a preview
    #: of the live apply if both read the same bars, and the reader cannot
    #: check that unless the source is stated.
    bar_source: str
