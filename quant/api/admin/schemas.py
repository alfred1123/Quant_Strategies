"""Pydantic schemas for admin maintenance endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DetachApiRequestPayloadRequest(BaseModel):
    """POST /api/v1/admin/db/detach-api-request-payload body."""

    retention_days: int = Field(
        default=14,
        ge=1,
        le=3660,
        description="Drop payload partitions whose range ended more than this many days ago.",
    )


class TerminateStaleConnectionsRequest(BaseModel):
    """POST /api/v1/admin/db/terminate-stale-connections body."""

    idle_seconds: int = Field(
        default=3600,
        ge=60,
        le=86_400,
        description="Terminate idle quant_app sessions older than this many seconds.",
    )
