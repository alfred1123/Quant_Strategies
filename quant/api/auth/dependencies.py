"""FastAPI dependencies for the auth module."""


import logging
import os
import secrets
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from quant.api.auth.models import CurrentUser
from quant.api.auth.repo import AuthRepo
from quant.api.auth.service import AuthService

logger = logging.getLogger(__name__)

COOKIE_NAME = "qs_token"

# Caller label recorded when a request arrives on the service token rather than
# a user session. Not a username — no APP_USER row exists for it.
SERVICE_CALLER = "scheduler"

# A token shorter than this is treated as unset. init-ssm-params.sh provisions
# `openssl rand -base64 32`, so anything this short is a placeholder left in a
# .env by mistake, and accepting it would be worse than refusing the caller.
_MIN_SERVICE_TOKEN_LEN = 16

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


def _configured_service_token() -> str | None:
    """The shared secret the scheduler must present, or None if unusable.

    Read per call rather than cached: load_config() populates the environment
    from SSM at startup, and reading live keeps a rotated value from needing a
    restart to take effect.
    """
    token = (os.getenv("TRADE_SERVICE_TOKEN") or "").strip()
    if not token:
        return None
    if len(token) < _MIN_SERVICE_TOKEN_LEN:
        logger.warning(
            "TRADE_SERVICE_TOKEN is shorter than %d characters — ignoring it. "
            "Generate one with `openssl rand -base64 32`.",
            _MIN_SERVICE_TOKEN_LEN,
        )
        return None
    return token


def _presents_service_token(authorization: str | None) -> bool:
    """Whether the Authorization header carries the configured service token.

    Compared with compare_digest so a wrong token cannot be recovered by
    timing the response.
    """
    if not authorization:
        return False
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        return False

    expected = _configured_service_token()
    if expected is None:
        logger.warning(
            "Bearer credential presented but TRADE_SERVICE_TOKEN is not "
            "configured on this host — refusing the caller."
        )
        return False
    return secrets.compare_digest(credential, expected)


def require_user_or_service(
    authorization: str | None = Header(default=None),
    qs_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    auth: AuthService = Depends(get_auth_service),
    repo: AuthRepo = Depends(get_auth_repo),
) -> str:
    """Admit a signed-in user or the scheduler, and name whoever got in.

    Maintenance endpoints are driven both by a human on the UI and by the
    EventBridge Lambda, which has no session to present. The return value is a
    caller label for the audit log, not an identity: work reached this way is
    owned by the platform, so these routes must not scope anything to a user.
    """
    if _presents_service_token(authorization):
        return SERVICE_CALLER
    return require_user(qs_token=qs_token, auth=auth, repo=repo).username
