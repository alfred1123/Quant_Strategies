"""Live account snapshot — balances and open positions, read straight from the broker.

Read-only by construction: the adapter methods used here place, cancel, and
modify nothing. This is the counterpart to :mod:`quant.trade.dry_run`, which
also touches the exchange without trading, except that a snapshot asks about the
account rather than about a prospective order.
"""

from __future__ import annotations

import logging
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.refdata.bundle import DataCaches
from quant.schemas.account import AccountSnapshot, BalanceRow, PositionRow
from quant.trade.errors import AdapterNotFoundError, TradeValidationError
from quant.trade.registry import AdapterRegistry

logger = logging.getLogger(__name__)


def fetch_account_snapshot(
    *,
    app_user_id: UUID,
    api_credential_id: int,
    paper: bool,
    credential_service: CredentialService,
    credential_repo: ApiCredentialRepo,
    adapter_registry: AdapterRegistry,
    data_caches: DataCaches,
) -> AccountSnapshot:
    """Balances and open positions for one credential.

    ``app_id`` comes off the credential row rather than the caller, so a client
    cannot ask for one exchange's account using another's adapter.
    """
    row = credential_repo.get_credential(app_user_id, api_credential_id)
    if row is None:
        raise TradeValidationError(
            "API credential not found or not owned", status_code=404
        )
    app_id = int(row["app_id"])

    if not adapter_registry.has_adapter(app_id):
        raise AdapterNotFoundError(f"no broker adapter registered for app_id={app_id}")

    keys = credential_service.decrypt_credential(
        credential_repo, app_user_id, api_credential_id
    )
    if keys is None:
        raise TradeValidationError(
            "API credential not found or not owned", status_code=404
        )

    adapter = adapter_registry.create(
        app_id,
        api_key=keys[0],
        api_secret=keys[1],
        paper=paper,
        inst_cache=data_caches.instrument_cache,
    )
    with adapter:
        balances = adapter.get_balances()
        positions = adapter.get_open_positions()

    logger.info(
        "account snapshot: credential=%s app_id=%s paper=%s "
        "%d balance(s), %d position(s)",
        api_credential_id,
        app_id,
        paper,
        len(balances),
        len(positions),
    )
    return AccountSnapshot(
        api_credential_id=api_credential_id,
        app_id=app_id,
        paper=paper,
        balances=[BalanceRow(**b) for b in balances],
        positions=[PositionRow(**p) for p in positions],
    )
