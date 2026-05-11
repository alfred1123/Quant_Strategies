"""Auth Pydantic schemas and CurrentUser dataclass."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


@dataclass(frozen=True)
class CurrentUser:
    """Resolved user identity returned by the require_user dependency."""

    app_user_id: UUID
    username: str
    session_gen: int


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        """Trim and case-fold so DB lookup matches stored lowercase usernames."""
        s = v.strip().casefold()
        if not s:
            raise ValueError("username must not be empty")
        return s

    @field_validator("password")
    @classmethod
    def strip_password(cls, v: str) -> str:
        """Trim paste/newline junk; length checks apply after stripping."""
        return v.strip()


class LoginResponse(BaseModel):
    username: str


class MeResponse(BaseModel):
    username: str
