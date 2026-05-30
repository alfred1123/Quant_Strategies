"""Unit tests for the credentials API — schemas, service masking, router responses.

These tests use mocks for DB access (no psycopg / postgres needed).
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from quant.api.credentials.schemas import (
    CreateCredentialRequest,
    CredentialResponse,
    RotateCredentialRequest,
)
from quant.api.credentials.service import CredentialService
from quant.shared.secrets_crypto import CredentialCrypto


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def crypto() -> CredentialCrypto:
    return CredentialCrypto(Fernet.generate_key().decode())


@pytest.fixture()
def svc(crypto: CredentialCrypto) -> CredentialService:
    return CredentialService(crypto)


def _fake_row(crypto: CredentialCrypto, **overrides) -> dict:
    """Build a dict mimicking an SP_GET_API_CREDENTIAL cursor row."""
    row = {
        "api_credential_id": 1,
        "api_credential_vid": 1,
        "app_user_id": uuid4(),
        "app_id": 4,
        "label": "Main",
        "api_key_ciphertext": crypto.encrypt("REAL-KEY-12345678"),
        "api_secret_ciphertext": crypto.encrypt("REAL-SECRET-ABC"),
        "is_active_ind": "Y",
        "is_current_ind": "Y",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestCreateCredentialRequest:
    def test_valid(self):
        r = CreateCredentialRequest(
            app_id=4, label="Main", api_key="key123", api_secret="secret456"
        )
        assert r.label == "Main"

    def test_label_stripped(self):
        r = CreateCredentialRequest(
            app_id=4, label="  Main  ", api_key="k", api_secret="s"
        )
        assert r.label == "Main"

    def test_empty_label_rejected(self):
        with pytest.raises(ValidationError):
            CreateCredentialRequest(
                app_id=4, label="   ", api_key="k", api_secret="s"
            )

    def test_key_stripped(self):
        r = CreateCredentialRequest(
            app_id=4, label="X", api_key="  key  ", api_secret="  sec  "
        )
        assert r.api_key == "key"
        assert r.api_secret == "sec"


class TestRotateCredentialRequest:
    def test_valid(self):
        r = RotateCredentialRequest(api_key="new-k", api_secret="new-s")
        assert r.api_key == "new-k"


# ---------------------------------------------------------------------------
# Service — masking
# ---------------------------------------------------------------------------

class TestCredentialServiceMask:
    def test_mask_row_never_contains_ciphertext(self, svc: CredentialService, crypto: CredentialCrypto):
        row = _fake_row(crypto)
        resp = svc._mask_row(row)
        assert isinstance(resp, CredentialResponse)
        resp_dict = resp.model_dump()
        for key in resp_dict:
            assert "ciphertext" not in key.lower(), f"Field {key} leaks ciphertext"

    def test_masked_key_hides_most_chars(self, svc: CredentialService, crypto: CredentialCrypto):
        row = _fake_row(crypto)
        resp = svc._mask_row(row)
        assert resp.api_key_masked.startswith("*")
        assert resp.api_key_masked.endswith("5678")

    def test_mask_row_with_empty_ciphertext(self, svc: CredentialService, crypto: CredentialCrypto):
        row = _fake_row(crypto, api_key_ciphertext="", api_secret_ciphertext="")
        resp = svc._mask_row(row)
        assert resp.api_key_masked == "****"


# ---------------------------------------------------------------------------
# Service — CRUD (mocked repo)
# ---------------------------------------------------------------------------

class TestCredentialServiceCRUD:
    def test_create_returns_masked(self, svc: CredentialService):
        repo = MagicMock()
        repo.insert_credential.return_value = (1, 1)
        user_id = uuid4()

        resp = svc.create_credential(
            repo,
            app_user_id=user_id,
            app_id=4,
            label="Test",
            api_key="KEY123456789",
            api_secret="SECRET",
        )

        assert resp.api_credential_id == 1
        assert resp.api_key_masked.startswith("*")
        assert "KEY123456789" not in resp.api_key_masked
        repo.insert_credential.assert_called_once()
        call_args = repo.insert_credential.call_args
        assert call_args.kwargs["api_key_ciphertext"] != "KEY123456789"

    def test_list_returns_masked(self, svc: CredentialService, crypto: CredentialCrypto):
        repo = MagicMock()
        repo.list_credentials.return_value = [_fake_row(crypto), _fake_row(crypto, api_credential_id=2)]
        user_id = uuid4()

        creds = svc.list_credentials(repo, user_id)
        assert len(creds) == 2
        for c in creds:
            assert "ciphertext" not in c.model_dump_json().lower()

    def test_get_not_found_returns_none(self, svc: CredentialService):
        repo = MagicMock()
        repo.get_credential.return_value = None
        assert svc.get_credential(repo, uuid4(), 999) is None

    def test_rotate_not_found_returns_none(self, svc: CredentialService):
        repo = MagicMock()
        repo.get_credential.return_value = None
        assert svc.rotate_credential(repo, uuid4(), 999, "k", "s") is None

    def test_rotate_returns_bumped_vid(self, svc: CredentialService, crypto: CredentialCrypto):
        repo = MagicMock()
        repo.get_credential.return_value = _fake_row(crypto)
        repo.insert_credential.return_value = (1, 2)
        user_id = uuid4()

        resp = svc.rotate_credential(repo, user_id, 1, "NEW-KEY", "NEW-SEC")
        assert resp is not None
        assert resp.api_credential_vid == 2
        assert resp.api_key_masked.endswith("-KEY")

    def test_revoke_not_found_returns_false(self, svc: CredentialService):
        repo = MagicMock()
        repo.get_credential.return_value = None
        assert svc.revoke_credential(repo, uuid4(), 999) is False

    def test_revoke_success(self, svc: CredentialService, crypto: CredentialCrypto):
        repo = MagicMock()
        repo.get_credential.return_value = _fake_row(crypto)
        repo.revoke_credential.return_value = 2
        assert svc.revoke_credential(repo, uuid4(), 1) is True
        repo.revoke_credential.assert_called_once()

    def test_decrypt_credential(self, svc: CredentialService, crypto: CredentialCrypto):
        repo = MagicMock()
        repo.get_credential.return_value = _fake_row(crypto)
        result = svc.decrypt_credential(repo, uuid4(), 1)
        assert result is not None
        api_key, api_secret = result
        assert api_key == "REAL-KEY-12345678"
        assert api_secret == "REAL-SECRET-ABC"


# ---------------------------------------------------------------------------
# Response model — no ciphertext fields
# ---------------------------------------------------------------------------

class TestResponseModelNoCiphertext:
    """Exit criteria: response schema never includes *_CIPHERTEXT fields."""

    def test_credential_response_fields(self):
        fields = set(CredentialResponse.model_fields.keys())
        for f in fields:
            assert "ciphertext" not in f.lower(), f"Response field '{f}' leaks ciphertext"

    def test_no_ciphertext_in_json(self, svc: CredentialService, crypto: CredentialCrypto):
        row = _fake_row(crypto)
        resp = svc._mask_row(row)
        json_str = resp.model_dump_json()
        assert "ciphertext" not in json_str.lower()
        assert "REAL-KEY" not in json_str
        assert "REAL-SECRET" not in json_str
