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

_SP_GET = (
    "CALL BT.SP_GET_QUEUE("
    "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::text, %s::integer,"
    "NULL::refcursor, NULL::text, NULL::text, NULL::text)"
)


@dataclass
class QueueRow:
    queue_id: uuid.UUID
    queue_vid: int
    strategy_id: uuid.UUID
    strategy_vid: int
    transact_from_ts: Any
    transact_to_ts: Any
    queue_status_id: int
    status_name: str
    is_terminal: bool
    priority: int
    error_text: str | None
    user_id: str
    created_at: Any


def _to_row(d: dict) -> QueueRow:
    return QueueRow(
        queue_id=d["queue_id"],
        queue_vid=d["queue_vid"],
        strategy_id=d["strategy_id"],
        strategy_vid=d["strategy_vid"],
        transact_from_ts=d["transact_from_ts"],
        transact_to_ts=d["transact_to_ts"],
        queue_status_id=d["queue_status_id"],
        status_name=d["status_name"],
        is_terminal=(d["is_terminal_ind"] == "Y"),
        priority=d["priority"],
        error_text=d["error_text"],
        user_id=d["user_id"],
        created_at=d["created_at"],
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


    def get(self, queue_id: uuid.UUID) -> QueueRow | None:
        # IN_QUEUE_ID set → SP returns all VIDs ordered ASC; last row is the active one.
        rows = self._call_get(_SP_GET, (str(queue_id), None, None, None, None, 100))
        return _to_row(rows[-1]) if rows else None

    def list_for_user(self, user_id: str | None = None, limit: int = 50) -> list[QueueRow]:
        # IN_QUEUE_ID=None → SP restricts to active rows only.
        rows = self._call_get(_SP_GET, (None, None, None, None, user_id or self.user_id, limit))
        return [_to_row(r) for r in rows]

    def list_by_status(self, status_name: str, limit: int = 50) -> list[QueueRow]:
        status_id = self.get_status_id(status_name)
        rows = self._call_get(_SP_GET, (None, None, None, status_id, None, limit))
        return [_to_row(r) for r in rows]

    def history(self, queue_id: uuid.UUID) -> list[QueueRow]:
        rows = self._call_get(_SP_GET, (str(queue_id), None, None, None, None, 1000))
        return [_to_row(r) for r in rows]
