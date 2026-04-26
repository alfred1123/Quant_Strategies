"""Unit tests for api.auth.service — JWT secret resolution and AuthService basics."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from api.auth.service import AuthService, _resolve_jwt_secret


class TestResolveJwtSecret:
    """Tests for _resolve_jwt_secret (dev auto-gen vs prod fail-fast)."""

    def test_explicit_secret_returned_as_is(self):
        assert _resolve_jwt_secret("my-secret") == "my-secret"

    def test_env_var_used_when_no_explicit(self):
        with patch.dict(os.environ, {"JWT_SECRET": "from-env"}, clear=False):
            assert _resolve_jwt_secret(None) == "from-env"

    def test_explicit_takes_precedence_over_env(self):
        with patch.dict(os.environ, {"JWT_SECRET": "from-env"}, clear=False):
            assert _resolve_jwt_secret("explicit") == "explicit"

    def test_prod_raises_when_missing(self):
        env = {"APP_ENV": "prod"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("JWT_SECRET", None)
            with pytest.raises(RuntimeError, match="JWT_SECRET is not set"):
                _resolve_jwt_secret(None)

    def test_dev_auto_generates_when_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JWT_SECRET", None)
            os.environ.pop("APP_ENV", None)
            secret = _resolve_jwt_secret(None)
            assert secret
            assert len(secret) > 20
            assert os.environ["JWT_SECRET"] == secret

    def test_dev_auto_generated_secrets_differ(self):
        """Each call without a stored secret produces a fresh random value."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JWT_SECRET", None)
            os.environ.pop("APP_ENV", None)
            s1 = _resolve_jwt_secret(None)
            os.environ.pop("JWT_SECRET", None)
            s2 = _resolve_jwt_secret(None)
            assert s1 != s2


class TestAuthServiceInit:
    """Smoke tests for AuthService construction."""

    def test_constructs_with_explicit_secret(self):
        svc = AuthService(jwt_secret="test-secret-value-32-chars-long!")
        token = svc.create_token(
            app_user_id=__import__("uuid").uuid4(), session_gen=1
        )
        assert token

    def test_dev_mode_constructs_without_secret(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JWT_SECRET", None)
            os.environ.pop("APP_ENV", None)
            svc = AuthService()
            assert svc
