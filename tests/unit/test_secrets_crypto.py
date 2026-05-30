"""Unit tests for quant.shared.secrets_crypto — Fernet encrypt/decrypt + masking."""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

from quant.shared.secrets_crypto import CredentialCrypto, _resolve_exchange_secrets_key


# ---------------------------------------------------------------------------
# _resolve_exchange_secrets_key
# ---------------------------------------------------------------------------

class TestResolveExchangeSecretsKey:
    def test_explicit_key_returned(self):
        key = Fernet.generate_key().decode()
        assert _resolve_exchange_secrets_key(key) == key

    def test_env_var_used_when_no_explicit(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"EXCHANGE_SECRETS_KEY": key}, clear=False):
            assert _resolve_exchange_secrets_key(None) == key

    def test_explicit_takes_precedence_over_env(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"EXCHANGE_SECRETS_KEY": "from-env"}, clear=False):
            assert _resolve_exchange_secrets_key(key) == key

    def test_prod_raises_when_missing(self):
        with patch.dict(os.environ, {"APP_ENV": "prod"}, clear=False):
            os.environ.pop("EXCHANGE_SECRETS_KEY", None)
            with pytest.raises(RuntimeError, match="EXCHANGE_SECRETS_KEY is not set"):
                _resolve_exchange_secrets_key(None)

    def test_dev_auto_generates_when_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EXCHANGE_SECRETS_KEY", None)
            os.environ.pop("APP_ENV", None)
            key = _resolve_exchange_secrets_key(None)
            assert key
            assert os.environ["EXCHANGE_SECRETS_KEY"] == key

    def test_dev_auto_generated_keys_differ(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EXCHANGE_SECRETS_KEY", None)
            os.environ.pop("APP_ENV", None)
            k1 = _resolve_exchange_secrets_key(None)
            os.environ.pop("EXCHANGE_SECRETS_KEY", None)
            k2 = _resolve_exchange_secrets_key(None)
            assert k1 != k2


# ---------------------------------------------------------------------------
# CredentialCrypto
# ---------------------------------------------------------------------------

@pytest.fixture()
def crypto() -> CredentialCrypto:
    key = Fernet.generate_key().decode()
    return CredentialCrypto(key)


class TestCredentialCrypto:
    def test_encrypt_decrypt_roundtrip(self, crypto: CredentialCrypto):
        plain = "my-api-key-value"
        token = crypto.encrypt(plain)
        assert token != plain
        assert crypto.decrypt(token) == plain

    def test_different_encryptions_differ(self, crypto: CredentialCrypto):
        plain = "same-value"
        t1 = crypto.encrypt(plain)
        t2 = crypto.encrypt(plain)
        assert t1 != t2  # Fernet includes timestamp

    def test_decrypt_wrong_key_raises(self, crypto: CredentialCrypto):
        token = crypto.encrypt("secret")
        other = CredentialCrypto(Fernet.generate_key().decode())
        with pytest.raises(InvalidToken):
            other.decrypt(token)

    def test_decrypt_tampered_raises(self, crypto: CredentialCrypto):
        token = crypto.encrypt("secret")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(Exception):
            crypto.decrypt(tampered)


class TestMask:
    def test_mask_long_value(self):
        assert CredentialCrypto.mask("abcdefghij") == "******ghij"

    def test_mask_short_value(self):
        assert CredentialCrypto.mask("ab") == "**"

    def test_mask_exact_visible_length(self):
        assert CredentialCrypto.mask("abcd") == "****"

    def test_mask_custom_visible(self):
        assert CredentialCrypto.mask("abcdefgh", visible=2) == "******gh"
