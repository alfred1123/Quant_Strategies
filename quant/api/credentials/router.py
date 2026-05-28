"""Credentials router — /api/v1/credentials.

All routes require ``require_user`` (applied at ``include_router`` level
in ``main.py``).  POST and PUT are rate-limited per login.md §11.2.

Ownership enforcement:
- Every SP call passes ``CurrentUser.app_user_id``.
- Cross-user ids return **404** (never 403) to avoid leaking existence.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from quant.api.auth.dependencies import require_user
from quant.api.auth.models import CurrentUser
from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.schemas import (
    CreateCredentialRequest,
    CredentialListResponse,
    CredentialResponse,
    RotateCredentialRequest,
)
from quant.api.credentials.service import CredentialService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["credentials"])

limiter = Limiter(key_func=get_remote_address)


# ── dependencies ────────────────────────────────────────────────────────

def _get_repo(request: Request) -> ApiCredentialRepo:
    return ApiCredentialRepo(request.app.state.db_conninfo, user_id="system")


def _get_service(request: Request) -> CredentialService:
    return request.app.state.credential_service


# ── routes ──────────────────────────────────────────────────────────────

@router.get("", response_model=CredentialListResponse)
def list_credentials(
    user: CurrentUser = Depends(require_user),
    repo: ApiCredentialRepo = Depends(_get_repo),
    svc: CredentialService = Depends(_get_service),
) -> CredentialListResponse:
    """List all active credentials for the current user (masked)."""
    creds = svc.list_credentials(repo, user.app_user_id)
    return CredentialListResponse(credentials=creds)


@router.get("/{api_credential_id}", response_model=CredentialResponse)
def get_credential(
    api_credential_id: int,
    user: CurrentUser = Depends(require_user),
    repo: ApiCredentialRepo = Depends(_get_repo),
    svc: CredentialService = Depends(_get_service),
) -> CredentialResponse:
    """Get a single credential by id (masked).  404 if not found or not owned."""
    cred = svc.get_credential(repo, user.app_user_id, api_credential_id)
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return cred


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/15minutes")
def create_credential(
    request: Request,
    body: CreateCredentialRequest,
    user: CurrentUser = Depends(require_user),
    repo: ApiCredentialRepo = Depends(_get_repo),
    svc: CredentialService = Depends(_get_service),
) -> CredentialResponse:
    """Save a new exchange account (encrypted at rest)."""
    logger.info(
        "Creating credential for app_user_id=%s app_id=%d label=%s",
        user.app_user_id,
        body.app_id,
        body.label,
    )
    return svc.create_credential(
        repo,
        app_user_id=user.app_user_id,
        app_id=body.app_id,
        label=body.label,
        api_key=body.api_key,
        api_secret=body.api_secret,
    )


@router.put("/{api_credential_id}", response_model=CredentialResponse)
@limiter.limit("5/15minutes")
def rotate_credential(
    request: Request,
    api_credential_id: int,
    body: RotateCredentialRequest,
    user: CurrentUser = Depends(require_user),
    repo: ApiCredentialRepo = Depends(_get_repo),
    svc: CredentialService = Depends(_get_service),
) -> CredentialResponse:
    """Rotate keys on an existing credential (soft-version bump)."""
    logger.info(
        "Rotating credential api_credential_id=%d for app_user_id=%s",
        api_credential_id,
        user.app_user_id,
    )
    cred = svc.rotate_credential(
        repo,
        app_user_id=user.app_user_id,
        api_credential_id=api_credential_id,
        api_key=body.api_key,
        api_secret=body.api_secret,
    )
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return cred


@router.delete("/{api_credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_credential(
    api_credential_id: int,
    user: CurrentUser = Depends(require_user),
    repo: ApiCredentialRepo = Depends(_get_repo),
    svc: CredentialService = Depends(_get_service),
) -> None:
    """Soft-revoke a credential (sets IS_ACTIVE_IND='N', clears ciphertext)."""
    logger.info(
        "Revoking credential api_credential_id=%d for app_user_id=%s",
        api_credential_id,
        user.app_user_id,
    )
    ok = svc.revoke_credential(repo, user.app_user_id, api_credential_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
