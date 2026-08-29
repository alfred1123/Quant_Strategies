"""Pydantic schemas for trade execution diary and fill history — Phase 1.8."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionEventRow(BaseModel):
    """One TRADE.EXECUTION_EVENT row with deployment context for the UI."""

    execution_event_id: UUID
    deployment_id: UUID
    deployment_vid: int
    internal_cusip: str
    api_credential_id: int
    app_id: int
    is_paper_ind: Literal["Y", "N"]
    signal_value: Decimal | None = None
    position_qty: Decimal | None = None
    buy_sell_cd: str
    quantity: Decimal | None = None
    vendor_order_id: str | None = None
    is_success_ind: Literal["Y", "N"]
    transact_at: datetime


class TransactionRow(BaseModel):
    """One TRADE.TRANSACTION row with deployment context for the UI."""

    transaction_id: UUID
    deployment_id: UUID
    deployment_vid: int
    internal_cusip: str
    api_credential_id: int
    app_id: int
    is_paper_ind: Literal["Y", "N"]
    vendor_symbol: str | None = None
    buy_sell_cd: str
    quantity: Decimal | None = None
    price: Decimal | None = None
    notional_amt: Decimal | None = None
    fee_amt: Decimal | None = None
    vendor_order_id: str | None = None
    trans_ccy_cd: str
    filled_at: datetime


class ExecutionLogQuery(BaseModel):
    """Shared query params for execution log reads."""

    limit: int = Field(50, ge=1, le=200)
    deployment_id: UUID | None = None
