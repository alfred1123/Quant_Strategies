"""Fernet encryption for exchange API credentials (Phase 1.1).

Mirrors the ``_resolve_jwt_secret`` pattern in ``quant.api.auth.service``:
production fails fast if ``EXCHANGE_SECRETS_KEY`` is absent; dev auto-
generates an ephemeral key with a loud warning.

Usage::

    from quant.shared.secrets_crypto import CredentialCrypto
    crypto = CredentialCrypto()          # reads EXCHANGE_SECRETS_KEY from env
    token  = crypto.encrypt("my-key")    # → base64 Fernet token (str)
    plain  = crypto.decrypt(token)       # → "my-key"

The key must be a 32-byte URL-safe base64-encoded string (standard Fernet
key format).  Generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENV_VAR = "EXCHANGE_SECRETS_KEY"


def _resolve_exchange_secrets_key(explicit: str | None = None) -> str:
    """Return the Fernet key, failing fast in prod if absent.

    Dev mode auto-generates an ephemeral key so local development works
    without manual setup — but keys encrypted with it won't survive a
    restart.
    """
    key = explicit if explicit is not None else os.getenv(_ENV_VAR)
    if key:
        return key

    is_prod = os.getenv("APP_ENV", "dev").lower() == "prod"
    if is_prod:
        raise RuntimeError(
            f"{_ENV_VAR} is not set.  Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"\n"
            f"and add it to SSM /quant/<env>/{_ENV_VAR}."
        )

    key = Fernet.generate_key().decode()
    os.environ[_ENV_VAR] = key
    logger.warning(
        "%s was not set — auto-generated a random dev key.  "
        "Encrypted credentials will not survive restarts.  "
        "Run the generate command above and add %s to .env to persist.",
        _ENV_VAR,
        _ENV_VAR,
    )
    return key


class CredentialCrypto:
    """Fernet encrypt / decrypt for exchange API key ciphertext columns."""

    def __init__(self, key: str | None = None) -> None:
        resolved = _resolve_exchange_secrets_key(key)
        self._fernet = Fernet(resolved.encode() if isinstance(resolved, str) else resolved)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* → URL-safe base64 Fernet token (``str``)."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet token back to the original ``str``.

        Raises ``cryptography.fernet.InvalidToken`` on bad / tampered data.
        """
        return self._fernet.decrypt(ciphertext.encode()).decode()

    @staticmethod
    def mask(value: str, *, visible: int = 4) -> str:
        """Return a masked version showing only the last *visible* chars."""
        if len(value) <= visible:
            return "*" * len(value)
        return "*" * (len(value) - visible) + value[-visible:]
