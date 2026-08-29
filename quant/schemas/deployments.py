"""Pydantic schemas for trade deployments — shared by API and workers."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DeploymentStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


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
    deployment_status: DeploymentStatus = DeploymentStatus.CREATED
    # REFDATA.TM_INTERVAL_ID. None = manual apply only, no scheduler row.
    schedule_tm_interval_id: int | None = Field(None, ge=1)

    @field_validator("internal_cusip")
    @classmethod
    def strip_cusip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("internal_cusip must not be empty")
        return s


class UpdateDeploymentRequest(BaseModel):
    """PATCH body for toggling deployment state (kill switch) and schedule."""

    enabled: bool | None = None
    deployment_status: DeploymentStatus | None = None
    # Explicit null clears the schedule (back to manual-only), so the service
    # distinguishes "omitted" from "set to null" via model_fields_set.
    schedule_tm_interval_id: int | None = Field(None, ge=1)


class ScheduleOptions(BaseModel):
    """Cadences a deployment may be scheduled on.

    Exists so the schedule control can grey out what the API would refuse,
    rather than the frontend keeping its own copy of a rule that belongs to
    the backtest side of the platform.
    """

    tm_interval_ids: list[int]


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
    deployment_status: DeploymentStatus
    schedule_tm_interval_id: int | None = None
    last_run_at: datetime | None = None
    next_due_at: datetime | None = None
    transact_from_ts: datetime
    user_id: str
