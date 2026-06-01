"""TRADE schema stored procedures + application-layer validation."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from quant.shared.db import DbGateway
from quant.trade.errors import TradeValidationError

logger = logging.getLogger(__name__)

ACTIVE_TS = "9999-12-31 00:00:00+00"


def _require(value: Any, name: str) -> None:
    if value is None:
        raise TradeValidationError(f"{name} is required")
    if isinstance(value, str) and not value.strip():
        raise TradeValidationError(f"{name} is required")


class TradeRepo(DbGateway):
    """TRADE.DEPLOYMENT / EXECUTION_EVENT / TRANSACTION — validates then CALLs SPs."""

    # ── validation reads (SELECT ok per AGENTS.md) ───────────────────────

    def _fetch_credential(self, api_credential_id: int) -> dict | None:
        rows = self._query(
            """
            SELECT app_user_id, app_id, is_active_ind, is_current_ind
              FROM core_admin.api_credential
             WHERE api_credential_id = %s
               AND is_current_ind = 'Y'
            """,
            (api_credential_id,),
        )
        return rows[0] if rows else None

    def _strategy_exists(self, strategy_id: UUID, strategy_vid: int) -> bool:
        rows = self._query(
            """
            SELECT 1
              FROM bt.strategy
             WHERE strategy_id = %s::uuid
               AND strategy_vid = %s
            """,
            (str(strategy_id), strategy_vid),
        )
        return bool(rows)

    def _fetch_deployment_version(
        self, deployment_id: UUID, deployment_vid: int
    ) -> dict | None:
        rows = self._query(
            """
            SELECT app_user_id, app_id
              FROM trade.deployment
             WHERE deployment_id = %s::uuid
               AND deployment_vid = %s
            """,
            (str(deployment_id), deployment_vid),
        )
        return rows[0] if rows else None

    def _fetch_current_deployment(self, deployment_id: UUID) -> dict | None:
        rows = self._query(
            """
            SELECT app_user_id, app_id, deployment_vid
              FROM trade.deployment
             WHERE deployment_id = %s::uuid
               AND transact_to_ts = %s::timestamptz
            """,
            (str(deployment_id), ACTIVE_TS),
        )
        return rows[0] if rows else None

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
        _require(deployment_id, "deployment_id")
        _require(app_user_id, "app_user_id")
        _require(strategy_id, "strategy_id")
        _require(strategy_vid, "strategy_vid")
        _require(api_credential_id, "api_credential_id")
        _require(app_id, "app_id")
        _require(internal_cusip, "internal_cusip")
        _require(qty, "qty")
        _require(is_paper_ind, "is_paper_ind")
        _require(is_enabled_ind, "is_enabled_ind")
        _require(deployment_status, "deployment_status")
        _require(user_id, "user_id")

        if is_paper_ind == "N" and not confirm_live:
            raise TradeValidationError(
                "Live trading requires explicit confirmation — set confirm_live=true",
                status_code=400,
            )

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

        if not self._strategy_exists(strategy_id, strategy_vid):
            raise TradeValidationError(
                "strategy_id / strategy_vid not found", status_code=404
            )

        current = self._fetch_current_deployment(deployment_id)
        if current is not None and str(current["app_user_id"]) != str(app_user_id):
            raise TradeValidationError(
                "deployment_id does not belong to user", status_code=403
            )

    def validate_execution_event(
        self,
        *,
        app_user_id: UUID,
        deployment_id: UUID,
        deployment_vid: int,
        buy_sell_cd: str,
        is_success_ind: str,
        user_id: str,
        execution_event_id: UUID | None = None,
    ) -> None:
        _require(app_user_id, "app_user_id")
        _require(deployment_id, "deployment_id")
        _require(deployment_vid, "deployment_vid")
        _require(buy_sell_cd, "buy_sell_cd")
        _require(is_success_ind, "is_success_ind")
        _require(user_id, "user_id")
        if execution_event_id is not None:
            _require(execution_event_id, "execution_event_id")

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
        transaction_id: UUID | None = None,
    ) -> None:
        _require(app_user_id, "app_user_id")
        _require(deployment_id, "deployment_id")
        _require(app_id, "app_id")
        _require(internal_cusip, "internal_cusip")
        _require(buy_sell_cd, "buy_sell_cd")
        _require(trans_ccy_cd, "trans_ccy_cd")
        _require(user_id, "user_id")
        if transaction_id is not None:
            _require(transaction_id, "transaction_id")

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
                f"deployment insert succeeded but SP_GET returned no row: {deployment_id}"
            )
        return rows[0]

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
            execution_event_id=execution_event_id,
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
            transaction_id=transaction_id,
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
