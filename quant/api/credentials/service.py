"""Credential service — encrypt, mask, and validate exchange API keys.

Sits between the router and the repo.  The router never touches
ciphertext or plaintext keys — only masked responses leave this layer.
"""

from __future__ import annotations

import logging
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.schemas import CredentialResponse
from quant.shared.secrets_crypto import CredentialCrypto

logger = logging.getLogger(__name__)


class CredentialService:
    """Orchestrates encrypt → SP → mask for the credentials API."""

    def __init__(self, crypto: CredentialCrypto) -> None:
        self._crypto = crypto

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _mask_row(self, row: dict) -> CredentialResponse:
        """Convert a raw SP row (with ciphertext) into a masked response."""
        api_key_ct = row.get("api_key_ciphertext", "")
        if api_key_ct:
            try:
                plain = self._crypto.decrypt(api_key_ct)
                masked = CredentialCrypto.mask(plain)
            except Exception:
                masked = "****"
        else:
            masked = "****"

        return CredentialResponse(
            api_credential_id=row["api_credential_id"],
            api_credential_vid=row["api_credential_vid"],
            app_id=row["app_id"],
            label=row["label"],
            api_key_masked=masked,
            is_active_ind=row["is_active_ind"],
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_credentials(
        self, repo: ApiCredentialRepo, app_user_id: UUID
    ) -> list[CredentialResponse]:
        rows = repo.list_credentials(app_user_id)
        return [self._mask_row(r) for r in rows]

    def get_credential(
        self, repo: ApiCredentialRepo, app_user_id: UUID, api_credential_id: int
    ) -> CredentialResponse | None:
        row = repo.get_credential(app_user_id, api_credential_id)
        if row is None:
            return None
        return self._mask_row(row)

    def create_credential(
        self,
        repo: ApiCredentialRepo,
        app_user_id: UUID,
        app_id: int,
        label: str,
        api_key: str,
        api_secret: str,
    ) -> CredentialResponse:
        key_ct = self._crypto.encrypt(api_key)
        secret_ct = self._crypto.encrypt(api_secret)

        cred_id, cred_vid = repo.insert_credential(
            app_user_id=app_user_id,
            app_id=app_id,
            label=label,
            api_key_ciphertext=key_ct,
            api_secret_ciphertext=secret_ct,
        )

        logger.info(
            "Created credential api_credential_id=%d vid=%d for app_user_id=%s app_id=%d",
            cred_id,
            cred_vid,
            app_user_id,
            app_id,
        )

        return CredentialResponse(
            api_credential_id=cred_id,
            api_credential_vid=cred_vid,
            app_id=app_id,
            label=label,
            api_key_masked=CredentialCrypto.mask(api_key),
            is_active_ind="Y",
        )

    def rotate_credential(
        self,
        repo: ApiCredentialRepo,
        app_user_id: UUID,
        api_credential_id: int,
        api_key: str,
        api_secret: str,
    ) -> CredentialResponse | None:
        """Rotate keys on an existing credential.  Returns None if not found."""
        existing = repo.get_credential(app_user_id, api_credential_id)
        if existing is None:
            return None

        key_ct = self._crypto.encrypt(api_key)
        secret_ct = self._crypto.encrypt(api_secret)

        cred_id, cred_vid = repo.insert_credential(
            app_user_id=app_user_id,
            app_id=existing["app_id"],
            label=existing["label"],
            api_key_ciphertext=key_ct,
            api_secret_ciphertext=secret_ct,
            api_credential_id=api_credential_id,
        )

        logger.info(
            "Rotated credential api_credential_id=%d vid=%d for app_user_id=%s",
            cred_id,
            cred_vid,
            app_user_id,
        )

        return CredentialResponse(
            api_credential_id=cred_id,
            api_credential_vid=cred_vid,
            app_id=existing["app_id"],
            label=existing["label"],
            api_key_masked=CredentialCrypto.mask(api_key),
            is_active_ind="Y",
        )

    def revoke_credential(
        self, repo: ApiCredentialRepo, app_user_id: UUID, api_credential_id: int
    ) -> bool:
        """Soft-revoke.  Returns True on success, False if not found."""
        existing = repo.get_credential(app_user_id, api_credential_id)
        if existing is None:
            return False

        vid = repo.revoke_credential(app_user_id, api_credential_id)
        logger.info(
            "Revoked credential api_credential_id=%d vid=%d for app_user_id=%s",
            api_credential_id,
            vid,
            app_user_id,
        )
        return True

    # ------------------------------------------------------------------
    # Internal (for broker adapter in Phase 1.3)
    # ------------------------------------------------------------------

    def decrypt_credential(
        self, repo: ApiCredentialRepo, app_user_id: UUID, api_credential_id: int
    ) -> tuple[str, str] | None:
        """Return ``(api_key, api_secret)`` in plaintext for the adapter.

        Only call from the worker / adapter boundary — never from an HTTP
        handler.  Returns None if the credential is not found / not owned.
        """
        row = repo.get_credential(app_user_id, api_credential_id)
        if row is None:
            return None
        return (
            self._crypto.decrypt(row["api_key_ciphertext"]),
            self._crypto.decrypt(row["api_secret_ciphertext"]),
        )
