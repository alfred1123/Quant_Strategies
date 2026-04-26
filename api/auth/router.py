"""Auth router — POST /login, POST /logout, GET /me.

Cookie attributes:
- ``HttpOnly + SameSite=Lax + Path=/api`` always.
- ``Secure`` is set when ``COOKIE_SECURE=1`` (default in prod with TLS).
  For HTTP-only prod deploys, set ``COOKIE_SECURE=0`` explicitly.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.auth.dependencies import (
    COOKIE_NAME,
    get_auth_repo,
    get_auth_service,
    require_user,
)
from api.auth.models import CurrentUser, LoginRequest, LoginResponse, MeResponse
from api.auth.repo import AuthRepo
from api.auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Per-process slowapi limiter — backs the @limiter.limit decorator below.
limiter = Limiter(key_func=get_remote_address)

_GENERIC_LOGIN_FAILURE = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid username or password.",
)


def _cookie_secure() -> bool:
    flag = os.getenv("COOKIE_SECURE", "").strip()
    if flag:
        return flag == "1"
    return os.getenv("APP_ENV", "dev").lower() == "prod"


def _set_session_cookie(response: Response, token: str) -> None:
    secure = _cookie_secure()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=AuthService.JWT_TTL_SECONDS,
        path="/api",
        httponly=True,
        secure=secure,
        samesite="strict" if secure else "lax",
    )


def _clear_session_cookie(response: Response) -> None:
    secure = _cookie_secure()
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api",
        httponly=True,
        secure=secure,
        samesite="strict" if secure else "lax",
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/15minutes")
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
    repo: AuthRepo = Depends(get_auth_repo),
) -> LoginResponse:
    """Verify credentials and set the ``qs_token`` cookie.

    The Argon2 cost is paid on every call (incl. unknown usernames) so the
    response time does not leak username validity — see login.md §11.1.
    """
    username = body.username.strip().lower()
    user = auth.verify_credentials(repo, username, body.password)
    if user is None:
        # Failed logins are auditable, but the password is never logged.
        logger.info(
            "Login failed for username=%s (ip=%s)",
            username,
            get_remote_address(request),
        )
        raise _GENERIC_LOGIN_FAILURE

    token = auth.create_token(user["app_user_id"], int(user["session_gen"]))
    _set_session_cookie(response, token)
    auth.cache_user(user)

    # Fire-and-forget: a failure to stamp LAST_LOGIN_AT must not block login.
    try:
        repo.update_last_login(user["app_user_id"])
    except Exception:
        logger.exception("Failed to stamp LAST_LOGIN_AT for user=%s", username)

    logger.info("Login OK for username=%s", username)
    return LoginResponse(username=user["username"])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    user: CurrentUser = Depends(require_user),
    auth: AuthService = Depends(get_auth_service),
) -> Response:
    """Clear the ``qs_token`` cookie and evict the user from the in-memory cache."""
    _clear_session_cookie(response)
    auth.invalidate_cache(user.app_user_id)
    logger.info("Logout for username=%s", user.username)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(require_user)) -> MeResponse:
    """Return the current authenticated user. Used by the SPA on page load."""
    return MeResponse(username=user.username)
