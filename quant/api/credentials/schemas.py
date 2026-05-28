"""Pydantic request / response schemas for /api/v1/credentials.

Response models intentionally omit ciphertext columns — the service layer
strips them before building these objects.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CreateCredentialRequest(BaseModel):
    """POST /api/v1/credentials — save a new exchange account."""

    app_id: int = Field(..., ge=1)
    label: str = Field(..., min_length=1, max_length=200)
    api_key: str = Field(..., min_length=1, max_length=500)
    api_secret: str = Field(..., min_length=1, max_length=500)

    @field_validator("label")
    @classmethod
    def strip_label(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("label must not be empty")
        return s

    @field_validator("api_key", "api_secret")
    @classmethod
    def strip_key(cls, v: str) -> str:
        return v.strip()


class RotateCredentialRequest(BaseModel):
    """PUT /api/v1/credentials/{id} — rotate keys on existing account."""

    api_key: str = Field(..., min_length=1, max_length=500)
    api_secret: str = Field(..., min_length=1, max_length=500)

    @field_validator("api_key", "api_secret")
    @classmethod
    def strip_key(cls, v: str) -> str:
        return v.strip()


class CredentialResponse(BaseModel):
    """Masked credential — never exposes ciphertext or full secrets."""

    api_credential_id: int
    api_credential_vid: int
    app_id: int
    label: str
    api_key_masked: str
    is_active_ind: Literal["Y", "N"]


class CredentialListResponse(BaseModel):
    """Wrapper for GET /api/v1/credentials."""

    credentials: list[CredentialResponse]
