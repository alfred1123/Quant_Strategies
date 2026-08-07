"""Unit tests for the scheduler's service-token path into the API.

The EventBridge Lambda has no user session, so maintenance endpoints admit a
shared secret instead. These tests pin the refusals rather than the happy path:
a gate that fails open is worse than one that never worked.
"""

import logging
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from quant.api.auth.dependencies import (
    SERVICE_CALLER,
    _presents_service_token,
    require_user_or_service,
)

TOKEN = "s3rvic3-t0ken-long-enough-to-be-real"


@pytest.fixture
def configured():
    with patch.dict("os.environ", {"TRADE_SERVICE_TOKEN": TOKEN}):
        yield


class TestPresentsServiceToken:
    """The header check itself."""

    def test_matching_bearer_token_is_accepted(self, configured):
        assert _presents_service_token(f"Bearer {TOKEN}") is True

    def test_scheme_is_case_insensitive(self, configured):
        assert _presents_service_token(f"bearer {TOKEN}") is True

    def test_wrong_token_is_refused(self, configured):
        assert _presents_service_token("Bearer not-the-right-token-at-all") is False

    def test_missing_header_is_refused(self, configured):
        assert _presents_service_token(None) is False
        assert _presents_service_token("") is False

    def test_non_bearer_scheme_is_refused(self, configured):
        assert _presents_service_token(f"Basic {TOKEN}") is False
        assert _presents_service_token(TOKEN) is False

    def test_empty_credential_is_refused(self, configured):
        assert _presents_service_token("Bearer ") is False
        assert _presents_service_token("Bearer") is False


class TestFailsClosed:
    """With no usable secret configured, no bearer credential may pass."""

    def test_unconfigured_token_refuses_every_credential(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _presents_service_token("Bearer anything") is False
            assert _presents_service_token("Bearer ") is False

    def test_blank_token_does_not_admit_a_blank_credential(self):
        with patch.dict("os.environ", {"TRADE_SERVICE_TOKEN": "   "}):
            assert _presents_service_token("Bearer    ") is False

    def test_placeholder_token_is_treated_as_unset(self, caplog):
        with patch.dict("os.environ", {"TRADE_SERVICE_TOKEN": "changeme"}):
            with caplog.at_level(logging.WARNING):
                assert _presents_service_token("Bearer changeme") is False
        assert "shorter than" in caplog.text

    def test_refusal_is_logged_when_nothing_is_configured(self, caplog):
        with patch.dict("os.environ", {}, clear=True):
            with caplog.at_level(logging.WARNING):
                _presents_service_token("Bearer anything")
        assert "not" in caplog.text and "configured" in caplog.text

    def test_secret_never_reaches_the_log(self, caplog):
        with patch.dict("os.environ", {"TRADE_SERVICE_TOKEN": TOKEN}):
            with caplog.at_level(logging.DEBUG):
                _presents_service_token("Bearer wrong-token-entirely")
        assert TOKEN not in caplog.text


class TestRequireUserOrService:
    """The dependency composes the service check with the session check."""

    def test_service_token_names_the_scheduler(self, configured):
        caller = require_user_or_service(
            authorization=f"Bearer {TOKEN}", qs_token=None, auth=None, repo=None
        )
        assert caller == SERVICE_CALLER

    def test_service_caller_is_not_a_username(self, configured):
        """A caller label must not collide with a real APP_USER name."""
        assert SERVICE_CALLER == "scheduler"

    def test_wrong_token_falls_through_to_session_auth(self, configured):
        with pytest.raises(HTTPException) as exc:
            require_user_or_service(
                authorization="Bearer wrong", qs_token=None, auth=None, repo=None
            )
        assert exc.value.status_code == 401

    def test_no_credentials_at_all_is_unauthorized(self, configured):
        with pytest.raises(HTTPException) as exc:
            require_user_or_service(
                authorization=None, qs_token=None, auth=None, repo=None
            )
        assert exc.value.status_code == 401

    def test_valid_cookie_still_works_without_a_bearer(self, configured):
        user = type("U", (), {"username": "alice"})()
        with patch(
            "quant.api.auth.dependencies.require_user", return_value=user
        ) as ru:
            caller = require_user_or_service(
                authorization=None, qs_token="jwt", auth="svc", repo="repo"
            )
        assert caller == "alice"
        ru.assert_called_once_with(qs_token="jwt", auth="svc", repo="repo")

    def test_service_token_short_circuits_session_lookup(self, configured):
        """A valid token must not need the database to resolve a user."""
        with patch("quant.api.auth.dependencies.require_user") as ru:
            require_user_or_service(
                authorization=f"Bearer {TOKEN}", qs_token=None, auth=None, repo=None
            )
        ru.assert_not_called()


class TestRotation:
    """A rotated secret takes effect without restarting the process."""

    def test_new_value_is_honoured_immediately(self):
        with patch.dict("os.environ", {"TRADE_SERVICE_TOKEN": TOKEN}):
            assert _presents_service_token(f"Bearer {TOKEN}") is True
        rotated = "rotated-token-also-long-enough"
        with patch.dict("os.environ", {"TRADE_SERVICE_TOKEN": rotated}):
            assert _presents_service_token(f"Bearer {rotated}") is True
            assert _presents_service_token(f"Bearer {TOKEN}") is False
