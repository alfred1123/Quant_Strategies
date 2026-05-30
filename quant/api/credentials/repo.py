"""Credential DB repository — wraps CORE_ADMIN.SP_*_API_CREDENTIAL.

All writes go through stored procedures; no raw DML.  The repo returns
raw rows (including ciphertext columns) — the *service* layer is
responsible for masking / stripping before the data reaches HTTP.
"""

from __future__ import annotations

import logging
from uuid import UUID

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class ApiCredentialRepo(DbGateway):
    """SP wrappers for CORE_ADMIN.API_CREDENTIAL."""

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def list_credentials(self, app_user_id: UUID) -> list[dict]:
        """All current + active credentials for *app_user_id*."""
        return self._call_get(
            "CALL CORE_ADMIN.SP_GET_API_CREDENTIAL(%s, NULL, NULL, NULL, NULL, NULL)",
            (str(app_user_id),),
        )

    def get_credential(self, app_user_id: UUID, api_credential_id: int) -> dict | None:
        """One current + active credential or ``None`` (empty cursor = 404)."""
        rows = self._call_get(
            "CALL CORE_ADMIN.SP_GET_API_CREDENTIAL(%s, %s, NULL, NULL, NULL, NULL)",
            (str(app_user_id), api_credential_id),
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------

    def insert_credential(
        self,
        app_user_id: UUID,
        app_id: int,
        label: str,
        api_key_ciphertext: str,
        api_secret_ciphertext: str,
        api_credential_id: int | None = None,
    ) -> tuple[int, int]:
        """Insert new account (id=None) or rotate keys (id set).

        Returns ``(api_credential_id, api_credential_vid)``.
        """
        tail = self._call_write(
            "CALL CORE_ADMIN.SP_INS_API_CREDENTIAL("
            "%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL"
            ")",
            (
                str(app_user_id),
                app_id,
                label,
                api_key_ciphertext,
                api_secret_ciphertext,
                api_credential_id,
            ),
        )
        return int(tail[0]), int(tail[1])

    def revoke_credential(
        self, app_user_id: UUID, api_credential_id: int
    ) -> int:
        """Soft-version revoke.  Returns the new ``api_credential_vid``."""
        tail = self._call_write(
            "CALL CORE_ADMIN.SP_UPD_API_CREDENTIAL_REVOKE("
            "%s, %s, NULL, NULL, NULL, NULL"
            ")",
            (str(app_user_id), api_credential_id),
        )
        return int(tail[0])
