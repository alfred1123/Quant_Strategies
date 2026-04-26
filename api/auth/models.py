"""Auth Pydantic schemas and CurrentUser dataclass."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class CurrentUser:
    """Resolved user identity returned by the require_user dependency."""

    app_user_id: UUID
    username: str
    session_gen: int


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=12, max_length=128)


class LoginResponse(BaseModel):
    username: str


class MeResponse(BaseModel):
    username: str
