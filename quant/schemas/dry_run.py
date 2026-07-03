"""Pydantic schemas for deployment dry-run — Phase 1.3."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

IntendedSide = Literal["BUY", "SELL", "HOLD", "CLOSE_SHORT"]


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
    intended_side: IntendedSide
    position_qty: float
    data_as_of: str
