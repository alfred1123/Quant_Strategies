"""Backtest queue repository.

Writes:  BT.SP_INS_QUEUE (7 IN params) and BT.SP_INS_RESULT.
Reads:   BT.SP_GET_QUEUE (dynamic SQL, force_custom_plan).
BT.RESULT inserts are done directly per AGENTS.md carve-out.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from db import DbGateway

logger = logging.getLogger(__name__)



@dataclass
class QueueRow:
    queue_id: uuid.UUID
    queue_vid: int
    strategy_id: uuid.UUID
    strategy_vid: int
    transact_from_ts: Any
    queue_status_id: int
    queue_status: str
    priority: int
    error_text: str | None
    user_id: str


def _to_row(d: dict) -> QueueRow:
    return QueueRow(
        queue_id=d["queue_id"],
        queue_vid=d["queue_vid"],
        strategy_id=d["strategy_id"],
        strategy_vid=d["strategy_vid"],
        transact_from_ts=d["transact_from_ts"],
        queue_status_id=d["queue_status_id"],
        queue_status=d["queue_status"],
        priority=d["priority"],
        error_text=d["error_text"],
        user_id=d["user_id"],
    )


@dataclass
class TerminalRow:
    queue_id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_vid: int
    strategy_nm: str | None
    strat_current_ind: str
    transact_from_ts: Any
    queue_status: str
    priority: int
    user_id: str
    config_json: dict | None
    error_text: str | None


def _to_terminal_row(d: dict) -> TerminalRow:
    return TerminalRow(
        queue_id=d["queue_id"],
        strategy_id=d["strategy_id"],
        strategy_vid=d["strategy_vid"],
        strategy_nm=d["strategy_nm"],
        strat_current_ind=d["strat_current_ind"],
        transact_from_ts=d["transact_from_ts"],
        queue_status=d["queue_status"],
        priority=d["priority"],
        user_id=d["user_id"],
        config_json=d["config_json"],
        error_text=d["error_text"],
    )


class BacktestJobRepo(DbGateway):
    
    def __init__(self, conninfo: str, refdata: RefdataCache, user_id: str = "alfcheun") -> None:
        super().__init__(conninfo, user_id)
        self._refdata = refdata

    def insert_queue(
        self,
        queue_id: uuid.UUID,
        strategy_id: uuid.UUID,
        strategy_vid: int,
        queue_status_id: int,
        priority: int,
        error_text: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self._call_write(
            "CALL BT.SP_INS_QUEUE("
            "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer, %s::text, %s::text,"
            "NULL::text, NULL::text, NULL::text)",
            (str(queue_id), str(strategy_id), strategy_vid,
             queue_status_id, priority, error_text, user_id or self.user_id),
        )

    def get_status_id(self, name: str) -> int:
        for row in self._refdata.get("queue_status"):
            if row["name"] == name:
                return int(row["queue_status_id"])
        raise ValueError(f"REFDATA.QUEUE_STATUS missing NAME={name!r}")

    def insert_result(
        self, queue_id: uuid.UUID, payload: dict[str, Any], user_id: str | None = None
    ) -> int:
        self._call_write("CALL BT.SP_INS_RESULT("
            "%s::uuid, %s::jsonb, %s::text, %s::integer, %s::text, %s::text, %s::text)",
            (str(queue_id), json.dumps(payload), user_id or self.user_id, 0, None, None, None)
        )


    def query_queue(
        self,
        *,
        queue_id: uuid.UUID | None = None,
        strategy_id: uuid.UUID | None = None,
        status_name: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[QueueRow]:
        """Wrapper for BT.SP_GET_QUEUE with all-optional filters.

        - queue_id set  → all VIDs for that job (full history).
        - queue_id None → active rows only (TRANSACT_TO_TS sentinel).
        - status_name   → resolved to QUEUE_STATUS_ID via REFDATA cache.
        """
        status_id = self.get_status_id(status_name) if status_name else None
        rows = self._call_get(
            "CALL BT.SP_GET_QUEUE("
            "%s::uuid, %s::uuid, %s::integer, %s::text, %s::integer,"
            "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (
                str(queue_id) if queue_id else None,
                str(strategy_id) if strategy_id else None,
                status_id,
                user_id,
                limit,
            ),
        )
        return [_to_row(r) for r in rows]

    def query_queue_for_terminal(
        self,
        *,
        user_id: str | None = None,
        status_name: str | None = None,
        limit: int = 50,
    ) -> list[TerminalRow]:
        """Wrapper for BT.SP_GET_QUEUE_FOR_TERMINAL.

        Returns active queue rows joined to the submitted strategy version,
        including STRATEGY_NM, CONFIG_JSON, and STRATEGY_IS_CURRENT_IND
        to flag if the strategy was updated after submission.
        """
        status_id = self.get_status_id(status_name) if status_name else None
        rows = self._call_get(
            "CALL BT.SP_GET_QUEUE_FOR_TERMINAL("
            "%s::text, %s::integer, %s::integer,"
            "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (user_id, status_id, limit),
        )
        return [_to_terminal_row(r) for r in rows]
