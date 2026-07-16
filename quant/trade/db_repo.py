"""TRADE schema stored procedures + application-layer validation."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from quant.queue.repo import BtQueueRepo
from quant.shared.db import DbGateway
from quant.trade.errors import TradeValidationError

logger = logging.getLogger(__name__)


def _require(value: Any, name: str) -> None:
    if value is None:
        raise TradeValidationError(f"{name} is required")
    if isinstance(value, str) and not value.strip():
        raise TradeValidationError(f"{name} is required")


def _require_all(**fields: Any) -> None:
    for name, val in fields.items():
        _require(val, name)


class TradeRepo(DbGateway):
    """TRADE.DEPLOYMENT / EXECUTION_EVENT / TRANSACTION — validates then CALLs SPs."""

    def __init__(self, conninfo: str, bt: BtQueueRepo, **kwargs) -> None:
        super().__init__(conninfo, **kwargs)
        self._bt = bt

    # ── validation reads (via stored procedures) ──────────────────────

    def _fetch_credential(self, api_credential_id: int) -> dict | None:
        return self._call_get_one(
            "CALL core_admin.sp_get_credential_check("
            "%s::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (api_credential_id,),
        )

    def _fetch_strategy(
        self, strategy_id: UUID, strategy_vid: int
    ) -> dict | None:
        rows = self._bt.sp_get_strategy(strategy_id, strategy_vid=strategy_vid)
        return rows[0] if rows else None

    def _assert_strategy_owned(
        self, strategy_id: UUID, strategy_vid: int, app_user_id: UUID
    ) -> dict:
        """Fetch the strategy row and enforce ownership; returns the row."""
        row = self._fetch_strategy(strategy_id, strategy_vid)
        if row is None:
            raise TradeValidationError(
                "strategy_id / strategy_vid not found", status_code=404
            )
        if str(row["user_id"]) != str(app_user_id):
            raise TradeValidationError(
                "strategy does not belong to user", status_code=403
            )
        return row

    def _assert_credential_usable(
        self, api_credential_id: int, app_user_id: UUID, app_id: int
    ) -> dict:
        """Fetch the credential and enforce active/ownership/app; returns the row."""
        cred = self._fetch_credential(api_credential_id)
        if cred is None:
            raise TradeValidationError(
                "API credential not found or not current", status_code=404
            )
        if cred["is_active_ind"] != "Y":
            raise TradeValidationError("API credential is not active", status_code=400)
        if str(cred["app_user_id"]) != str(app_user_id):
            raise TradeValidationError(
                "API credential does not belong to user", status_code=403
            )
        if cred["app_id"] != app_id:
            raise TradeValidationError(
                "app_id does not match API credential", status_code=400
            )
        return cred

    def _fetch_deployment_version(
        self, deployment_id: UUID, deployment_vid: int
    ) -> dict | None:
        return self._call_get_one(
            "CALL trade.sp_get_deployment_check("
            "%s::uuid, %s::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (str(deployment_id), int(deployment_vid)),
        )

    def _fetch_current_deployment(self, deployment_id: UUID) -> dict | None:
        return self._call_get_one(
            "CALL trade.sp_get_deployment_check("
            "%s::uuid, NULL::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (str(deployment_id),),
        )

    def validate_create_deployment(
        self,
        *,
        deployment_id: UUID,
        app_user_id: UUID,
        strategy_id: UUID,
        strategy_vid: int,
        api_credential_id: int,
        app_id: int,
        internal_cusip: str,
        qty: Decimal | float,
        is_paper_ind: str,
        is_enabled_ind: str,
        deployment_status: str,
        user_id: str,
        confirm_live: bool = False,
    ) -> None:
        _require_all(
            deployment_id=deployment_id, app_user_id=app_user_id,
            strategy_id=strategy_id, strategy_vid=strategy_vid,
            api_credential_id=api_credential_id, app_id=app_id,
            internal_cusip=internal_cusip, qty=qty,
            is_paper_ind=is_paper_ind, is_enabled_ind=is_enabled_ind,
            deployment_status=deployment_status, user_id=user_id,
        )

        if is_paper_ind == "N" and not confirm_live:
            raise TradeValidationError(
                "Live trading requires explicit confirmation — set confirm_live=true",
                status_code=400,
            )

        self._assert_credential_usable(api_credential_id, app_user_id, app_id)
        self._assert_strategy_owned(strategy_id, strategy_vid, app_user_id)

        current = self._fetch_current_deployment(deployment_id)
        if current is not None and str(current["app_user_id"]) != str(app_user_id):
            raise TradeValidationError(
                "deployment_id does not belong to user", status_code=403
            )

    def validate_dry_run(
        self,
        *,
        app_user_id: UUID,
        strategy_id: UUID,
        strategy_vid: int,
        api_credential_id: int,
        app_id: int,
        internal_cusip: str,
        qty: Decimal | float,
    ) -> dict:
        """Preflight dry-run — credential + strategy ownership; returns strategy row."""
        _require_all(
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            api_credential_id=api_credential_id,
            app_id=app_id,
            internal_cusip=internal_cusip,
            qty=qty,
        )

        self._assert_credential_usable(api_credential_id, app_user_id, app_id)
        return self._assert_strategy_owned(strategy_id, strategy_vid, app_user_id)

    def validate_execution_event(
        self,
        *,
        app_user_id: UUID,
        deployment_id: UUID,
        deployment_vid: int,
        buy_sell_cd: str,
        is_success_ind: str,
        user_id: str,
    ) -> None:
        _require_all(
            app_user_id=app_user_id, deployment_id=deployment_id,
            deployment_vid=deployment_vid, buy_sell_cd=buy_sell_cd,
            is_success_ind=is_success_ind, user_id=user_id,
        )

        dep = self._fetch_deployment_version(deployment_id, deployment_vid)
        if dep is None:
            raise TradeValidationError("deployment not found", status_code=404)
        if str(dep["app_user_id"]) != str(app_user_id):
            raise TradeValidationError(
                "deployment does not belong to user", status_code=403
            )

    def validate_transaction(
        self,
        *,
        app_user_id: UUID,
        deployment_id: UUID,
        app_id: int,
        internal_cusip: str,
        buy_sell_cd: str,
        trans_ccy_cd: str,
        user_id: str,
    ) -> None:
        _require_all(
            app_user_id=app_user_id, deployment_id=deployment_id,
            app_id=app_id, internal_cusip=internal_cusip,
            buy_sell_cd=buy_sell_cd, trans_ccy_cd=trans_ccy_cd,
            user_id=user_id,
        )

        dep = self._fetch_current_deployment(deployment_id)
        if dep is None:
            raise TradeValidationError(
                "deployment not found or not current", status_code=404
            )
        if str(dep["app_user_id"]) != str(app_user_id):
            raise TradeValidationError(
                "deployment does not belong to user", status_code=403
            )
        if dep["app_id"] != app_id:
            raise TradeValidationError(
                "app_id does not match deployment", status_code=400
            )

    # ── writes ───────────────────────────────────────────────────────────

    def write_deployment(
        self,
        *,
        deployment_id: UUID,
        app_user_id: UUID,
        strategy_id: UUID,
        strategy_vid: int,
        api_credential_id: int,
        app_id: int,
        internal_cusip: str,
        qty: Decimal | float,
        is_paper_ind: str,
        is_enabled_ind: str,
        deployment_status: str,
        user_id: str,
    ) -> dict:
        """Raw SP_INS_DEPLOYMENT call + read-back — used by create and update."""
        self._call_write(
            "CALL trade.sp_ins_deployment("
            "%s::uuid, %s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer,"
            " %s::text, %s::numeric, %s::char(1), %s::char(1), %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(deployment_id),
                str(app_user_id),
                str(strategy_id),
                int(strategy_vid),
                int(api_credential_id),
                int(app_id),
                internal_cusip,
                qty,
                is_paper_ind,
                is_enabled_ind,
                deployment_status,
                user_id,
            ),
        )
        rows = self.sp_get_deployment(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
        )
        if not rows:
            raise RuntimeError(
                f"SP_INS_DEPLOYMENT succeeded but SP_GET returned no row: {deployment_id}"
            )
        return rows[0]

    def sp_ins_deployment(
        self,
        *,
        deployment_id: UUID,
        app_user_id: UUID,
        strategy_id: UUID,
        strategy_vid: int,
        api_credential_id: int,
        app_id: int,
        internal_cusip: str,
        qty: Decimal | float,
        is_paper_ind: str,
        is_enabled_ind: str,
        deployment_status: str,
        user_id: str,
        confirm_live: bool = False,
    ) -> dict:
        self.validate_create_deployment(
            deployment_id=deployment_id,
            app_user_id=app_user_id,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            api_credential_id=api_credential_id,
            app_id=app_id,
            internal_cusip=internal_cusip,
            qty=qty,
            is_paper_ind=is_paper_ind,
            is_enabled_ind=is_enabled_ind,
            deployment_status=deployment_status,
            user_id=user_id,
            confirm_live=confirm_live,
        )
        return self.write_deployment(
            deployment_id=deployment_id,
            app_user_id=app_user_id,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            api_credential_id=api_credential_id,
            app_id=app_id,
            internal_cusip=internal_cusip,
            qty=qty,
            is_paper_ind=is_paper_ind,
            is_enabled_ind=is_enabled_ind,
            deployment_status=deployment_status,
            user_id=user_id,
        )

    def sp_ins_execution_event(
        self,
        *,
        execution_event_id: UUID,
        app_user_id: UUID,
        deployment_id: UUID,
        deployment_vid: int,
        buy_sell_cd: str,
        is_success_ind: str,
        user_id: str,
        signal_value: float | Decimal | None = None,
        quantity: float | Decimal | None = None,
        vendor_order_id: str | None = None,
    ) -> None:
        self.validate_execution_event(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
            deployment_vid=deployment_vid,
            buy_sell_cd=buy_sell_cd,
            is_success_ind=is_success_ind,
            user_id=user_id,
        )
        self._call_write(
            "CALL trade.sp_ins_execution_event("
            "%s::uuid, %s::uuid, %s::integer, %s::numeric, %s::text,"
            " %s::numeric, %s::text, %s::char(1), %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(execution_event_id),
                str(deployment_id),
                int(deployment_vid),
                signal_value,
                buy_sell_cd,
                quantity,
                vendor_order_id,
                is_success_ind,
                user_id,
            ),
        )

    def sp_ins_transaction(
        self,
        *,
        transaction_id: UUID,
        app_user_id: UUID,
        deployment_id: UUID,
        app_id: int,
        internal_cusip: str,
        buy_sell_cd: str,
        trans_ccy_cd: str,
        user_id: str,
        order_state_id: int | None = None,
        trans_state_id: int | None = None,
        vendor_symbol: str | None = None,
        quantity: float | Decimal | None = None,
        price: float | Decimal | None = None,
        notional_amt: float | Decimal | None = None,
        fee_amt: float | Decimal | None = None,
        vendor_order_id: str | None = None,
    ) -> None:
        self.validate_transaction(
            app_user_id=app_user_id,
            deployment_id=deployment_id,
            app_id=app_id,
            internal_cusip=internal_cusip,
            buy_sell_cd=buy_sell_cd,
            trans_ccy_cd=trans_ccy_cd,
            user_id=user_id,
        )
        self._call_write(
            "CALL trade.sp_ins_transaction("
            "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer,"
            " %s::text, %s::text, %s::text, %s::text,"
            " %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(transaction_id),
                str(deployment_id),
                int(app_id),
                order_state_id,
                trans_state_id,
                internal_cusip,
                vendor_symbol,
                buy_sell_cd,
                trans_ccy_cd,
                quantity,
                price,
                notional_amt,
                fee_amt,
                vendor_order_id,
                user_id,
            ),
        )

    # ── reads ────────────────────────────────────────────────────────────

    def sp_get_deployment(
        self,
        *,
        app_user_id: UUID,
        deployment_id: UUID | None = None,
        deployment_vid: int | None = None,
    ) -> list[dict]:
        _require(app_user_id, "app_user_id")
        return self._call_get(
            "CALL trade.sp_get_deployment("
            "%s::uuid, %s::uuid, %s::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (
                str(app_user_id),
                str(deployment_id) if deployment_id else None,
                deployment_vid,
            ),
        )
