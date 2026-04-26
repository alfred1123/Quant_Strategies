"""FastAPI dependencies for the auth module."""

from __future__ import annotations

import logging
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status

from api.auth.models import CurrentUser
from api.auth.repo import AuthRepo
from api.auth.service import AuthService

logger = logging.getLogger(__name__)

COOKIE_NAME = "qs_token"

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


def get_auth_service(request: Request) -> AuthService:
    """Return the singleton ``AuthService`` built in the lifespan handler."""
    return request.app.state.auth_service


def get_auth_repo(request: Request) -> AuthRepo:
    """Build a per-request ``AuthRepo`` against the app-wide DB conninfo."""
    return AuthRepo(request.app.state.db_conninfo, user_id="system")


def require_user(
    qs_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    auth: AuthService = Depends(get_auth_service),
    repo: AuthRepo = Depends(get_auth_repo),
) -> CurrentUser:
    """Resolve the JWT cookie into a ``CurrentUser`` or raise 401.

    See docs/design/login.md §8.2 + §10.
    """
    if not qs_token:
        raise _UNAUTHORIZED
    try:
        claims = auth.decode_token(qs_token)
    except jwt.InvalidTokenError as exc:
        logger.info("require_user: invalid JWT (%s)", exc)
        raise _UNAUTHORIZED from exc

    try:
        app_user_id = UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        logger.warning("require_user: malformed sub claim")
        raise _UNAUTHORIZED from exc

    user = auth.resolve_current_user(repo, app_user_id, int(claims["ver"]))
    if user is None:
        raise _UNAUTHORIZED
    return user
