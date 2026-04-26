"""Auth service — Argon2 verification, JWT mint/decode, 5 s user-resolution cache.

See docs/design/login.md §8.3, §10, §11.1.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from threading import Lock
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from api.auth.models import CurrentUser
from api.auth.repo import AuthRepo

logger = logging.getLogger(__name__)


def _resolve_jwt_secret(explicit: str | None) -> str:
    """Return the JWT signing secret, auto-generating in dev mode if absent.

    Production (``APP_ENV=prod``) always requires an explicit secret —
    either passed as ``explicit`` or via the ``JWT_SECRET`` env var.

    In dev mode (default), a missing secret is auto-generated so that new
    developers can start the API without manual setup.  The generated
    secret is written back to ``JWT_SECRET`` in the process environment
    so all components in the same process see the same value; however it
    does **not** persist across restarts — each boot gets a fresh secret
    and all prior JWTs become invalid (acceptable for local dev).
    """
    secret = explicit if explicit is not None else os.getenv("JWT_SECRET")
    if secret:
        return secret

    is_prod = os.getenv("APP_ENV", "dev").lower() == "prod"
    if is_prod:
        raise RuntimeError(
            "JWT_SECRET is not set. Generate one with `openssl rand -base64 32` "
            "and add it to .env (or SSM /quant/<env>/JWT_SECRET)."
        )

    secret = secrets.token_urlsafe(32)
    os.environ["JWT_SECRET"] = secret
    logger.warning(
        "JWT_SECRET was not set — auto-generated a random dev secret. "
        "Sessions will not survive restarts. "
        "Run `openssl rand -base64 32` and add JWT_SECRET to .env to persist."
    )
    return secret


class AuthService:
    """Encapsulates Argon2 hashing, JWT signing, and a TTL cache for user lookups.

    A single instance is built at FastAPI startup (in the ``lifespan`` block)
    and stored on ``app.state.auth_service``. Routes obtain it via the
    ``get_auth_service`` dependency.
    """

    JWT_ALGORITHM = "HS256"
    JWT_ISSUER = "quant-strategies"
    JWT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
    CACHE_TTL_SECONDS = 5.0

    def __init__(
        self,
        jwt_secret: str | None = None,
        *,
        hasher: PasswordHasher | None = None,
    ) -> None:
        self._jwt_secret: str = _resolve_jwt_secret(jwt_secret)
        self._hasher: PasswordHasher = hasher or PasswordHasher(
            memory_cost=65536, time_cost=3, parallelism=4
        )
        # Pre-computed once at construction: used for timing-attack hardening
        # when the username does not exist (login.md §11.1).
        self._dummy_hash: str = self._hasher.hash("not-a-real-password-xyz")

        self._cache: dict[UUID, tuple[float, dict]] = {}
        self._cache_lock: Lock = Lock()

    # ── JWT ──────────────────────────────────────────────────────────────

    def create_token(self, app_user_id: UUID, session_gen: int) -> str:
        now = int(time.time())
        payload = {
            "sub": str(app_user_id),
            "ver": session_gen,
            "iat": now,
            "exp": now + self.JWT_TTL_SECONDS,
            "iss": self.JWT_ISSUER,
        }
        return jwt.encode(payload, self._jwt_secret, algorithm=self.JWT_ALGORITHM)

    def decode_token(self, token: str) -> dict:
        """Verify signature + exp + iss. Raises ``jwt.InvalidTokenError`` on failure."""
        return jwt.decode(
            token,
            self._jwt_secret,
            algorithms=[self.JWT_ALGORITHM],
            issuer=self.JWT_ISSUER,
            options={"require": ["sub", "ver", "iat", "exp", "iss"]},
        )

    # ── Login (timing-attack hardened — login.md §11.1) ─────────────────

    def verify_credentials(
        self, repo: AuthRepo, username: str, password: str
    ) -> dict | None:
        """Return the APP_USER row dict on success, else None.

        Always runs an Argon2 verify (against the dummy hash if the user
        does not exist) so that login latency is independent of username
        validity.
        """
        user = repo.get_user_by_username(username)
        hash_to_verify = user["password_hash"] if user else self._dummy_hash
        try:
            self._hasher.verify(hash_to_verify, password)
        except VerifyMismatchError:
            return None
        except Exception:
            logger.exception("Argon2 verify raised — treating as failed login")
            return None
        if user is None or user["is_active_ind"] != "Y":
            return None
        try:
            if self._hasher.check_needs_rehash(user["password_hash"]):
                logger.info(
                    "Password hash for %s needs rehash — admin should rotate.",
                    username,
                )
        except Exception:
            pass
        return user

    # ── 5 s TTL cache for require_user lookups (login.md §10) ───────────

    def _cache_get(self, app_user_id: UUID) -> dict | None:
        with self._cache_lock:
            entry = self._cache.get(app_user_id)
            if entry is None:
                return None
            expires_at, user = entry
            if expires_at < time.monotonic():
                self._cache.pop(app_user_id, None)
                return None
            return user

    def cache_user(self, user: dict) -> None:
        """Insert / refresh a user in the 5-second require_user cache."""
        with self._cache_lock:
            self._cache[user["app_user_id"]] = (
                time.monotonic() + self.CACHE_TTL_SECONDS,
                user,
            )

    def invalidate_cache(self, app_user_id: UUID) -> None:
        """Drop a single user from the cache (used on logout)."""
        with self._cache_lock:
            self._cache.pop(app_user_id, None)

    def resolve_current_user(
        self, repo: AuthRepo, app_user_id: UUID, claim_session_gen: int
    ) -> CurrentUser | None:
        """Look up the user (cached, 5 s TTL) and verify they're still allowed.

        Returns None if the user no longer exists, has been deactivated, or
        the JWT was issued before the most recent ``SESSION_GEN`` bump
        (logout-everywhere / password change).
        """
        user = self._cache_get(app_user_id)
        if user is None:
            user = repo.get_user_by_id(app_user_id)
            if user is None:
                return None
            self.cache_user(user)
        if user["is_active_ind"] != "Y":
            return None
        if int(user["session_gen"]) != int(claim_session_gen):
            return None
        return CurrentUser(
            app_user_id=app_user_id,
            username=user["username"],
            session_gen=int(user["session_gen"]),
        )
