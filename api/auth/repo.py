"""Auth DB repository — wraps CORE_ADMIN.SP_GET_APP_USER_BY_USERNAME / SP_UPD_APP_USER_LAST_LOGIN."""

from __future__ import annotations

import logging
from uuid import UUID

from src.db import DbGateway

logger = logging.getLogger(__name__)


class AuthRepo(DbGateway):
    """Stored-procedure access for the CORE_ADMIN.APP_USER table."""

    def get_user_by_username(self, username: str) -> dict | None:
        """Return the APP_USER row for ``username`` or None if not found.

        Returned dict keys: ``app_user_id`` (UUID), ``username`` (str),
        ``password_hash`` (str), ``is_active_ind`` (str, 'Y'/'N'),
        ``session_gen`` (int).
        """
        rows = self._call_get(
            "CALL CORE_ADMIN.SP_GET_APP_USER_BY_USERNAME(%s, NULL, NULL, NULL, NULL)",
            (username,),
        )
        return rows[0] if rows else None

    def get_user_by_id(self, app_user_id: UUID) -> dict | None:
        """Return the APP_USER row for ``app_user_id`` or None if not found.

        Same dict shape as :meth:`get_user_by_username`. Used by the
        ``require_user`` dependency on cache miss (login.md §10).
        """
        rows = self._call_get(
            "CALL CORE_ADMIN.SP_GET_APP_USER_BY_ID(%s, NULL, NULL, NULL, NULL)",
            (str(app_user_id),),
        )
        return rows[0] if rows else None

    def update_last_login(self, app_user_id: UUID) -> None:
        """Stamp LAST_LOGIN_AT = NOW() for the given user."""
        self._call_write(
            "CALL CORE_ADMIN.SP_UPD_APP_USER_LAST_LOGIN(%s, NULL, NULL, NULL)",
            (str(app_user_id),),
        )
