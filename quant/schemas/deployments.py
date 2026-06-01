"""Pydantic schemas for trade deployments — shared by API and workers."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

DeploymentStatus = Literal["CREATED", "ACTIVE", "PAUSED", "STOPPED"]


class CreateDeploymentRequest(BaseModel):
    """Apply or re-apply a strategy to a broker account."""

    deployment_id: UUID | None = None
    strategy_id: UUID
    strategy_vid: int = Field(..., ge=1)
    api_credential_id: int = Field(..., ge=1)
    app_id: int = Field(..., ge=1)
    internal_cusip: str = Field(..., min_length=1, max_length=200)
    qty: Decimal = Field(..., gt=0)
    paper: bool = True
    confirm_live: bool = False
    enabled: bool = True
    deployment_status: DeploymentStatus = "CREATED"

    @field_validator("internal_cusip")
    @classmethod
    def strip_cusip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("internal_cusip must not be empty")
        return s


class DeploymentRow(BaseModel):
    """One TRADE.DEPLOYMENT row returned by SP_GET_DEPLOYMENT."""

    deployment_id: UUID
    deployment_vid: int
    app_user_id: UUID
    strategy_id: UUID
    strategy_vid: int
    api_credential_id: int
    app_id: int
    internal_cusip: str
    qty: Decimal
    is_paper_ind: Literal["Y", "N"]
    is_enabled_ind: Literal["Y", "N"]
    deployment_status: str
    user_id: str
    created_at: datetime
