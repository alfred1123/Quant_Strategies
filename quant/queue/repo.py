"""Shared SP wrappers for ``BT.QUEUE`` / ``BT.RESULT`` / ``BT.STRATEGY``.

All Postgres access for the backtest queue lives on :class:`BtQueueRepo`.
Reads and writes go through stored procedures — no direct ``SELECT`` in
application code.
"""

import json
import uuid
from typing import Any, TypeVar

from quant.shared.db import DbGateway, ProcedureError

T = TypeVar("T")


def _opt(cast: type[T], v: object) -> T | None:
    """``cast(v)`` when ``v`` is not ``None``; else ``None``."""
    return None if v is None else cast(v)  # type: ignore[call-arg]


class BtQueueRepo(DbGateway):
    """All ``BT.QUEUE`` / ``BT.RESULT`` reads + writes for FastAPI and the worker."""

    # ── reads (REFCURSOR procedures) ────────────────────────────────────

    def sp_get_queue(
        self,
        *,
        queue_id: uuid.UUID | str | None = None,
        strategy_id: uuid.UUID | str | None = None,
        queue_status_id: int | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Wrap ``BT.SP_GET_QUEUE``.

        ``queue_id=None`` returns active rows ordered by
        ``(PRIORITY ASC, CREATED_AT ASC)`` — the dequeue ranking. Pass
        ``queue_id`` to get the full version history of one job ordered
        by ``QUEUE_VID``.
        """
        return self._call_get(
            "CALL bt.sp_get_queue("
            "%s::uuid, %s::uuid, %s::integer, %s::text, %s::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (
                _opt(str, queue_id),
                _opt(str, strategy_id),
                _opt(int, queue_status_id),
                user_id,
                int(limit),
            ),
        )

    def sp_get_queue_latest(self, queue_id: uuid.UUID | str) -> dict | None:
        """Wrap ``BT.SP_GET_QUEUE_LATEST`` — active row + frozen STRATEGY join.

        Returns ``None`` if the queue row does not exist.
        """
        return self._call_get_one(
            "CALL bt.sp_get_queue_latest(%s::uuid, NULL, NULL, NULL, NULL)",
            (str(queue_id),),
        )

    # ── writes ──────────────────────────────────────────────────────────

    def sp_ins_queue(
        self,
        *,
        queue_id: uuid.UUID | str,
        strategy_id: uuid.UUID | str,
        strategy_vid: int,
        status_id: int,
        priority: int,
        user_id: str,
        error_text: str | None = None,
    ) -> None:
        """Wrap ``BT.SP_INS_QUEUE`` — every state transition flows through here.

        OUT row is ``(SQLSTATE, MSG, ERRMC)``; ``_call_write`` raises on
        non-``00000`` sqlstate so callers can ignore the return value.
        """
        self._call_write(
            "CALL bt.sp_ins_queue("
            "%s::uuid, %s::uuid, %s::integer, %s::integer, %s::integer, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(queue_id),
                str(strategy_id),
                int(strategy_vid),
                int(status_id),
                int(priority),
                error_text,
                user_id,
            ),
        )

    def sp_ins_strategy(
        self,
        *,
        strategy_nm: str,
        config_json: dict[str, Any],
        user_id: str,
        strategy_id: uuid.UUID | str | None = None,
    ) -> tuple[uuid.UUID, int]:
        """Wrap ``BT.SP_INS_STRATEGY`` — returns resolved ``(STRATEGY_ID, STRATEGY_VID)``.

        When ``(user_id, strategy_nm)`` already exists the SP reuses that
        ``STRATEGY_ID`` and bumps ``STRATEGY_VID``. Otherwise it allocates
        ``strategy_id`` when provided, else ``gen_random_uuid()``.
        """
        sid = None if strategy_id is None else str(strategy_id)
        (resolved_id, new_vid) = self._call_write(
            "CALL bt.sp_ins_strategy("
            "%s::uuid, %s::text, %s::jsonb, %s::text,"
            " NULL::text, NULL::text, NULL::text, NULL::uuid, NULL::integer)",
            (sid, strategy_nm, json.dumps(config_json), user_id),
        )
        return uuid.UUID(str(resolved_id)), int(new_vid)

    # ── reads (SP wrappers) ────────────────────────────────────────────

    def sp_get_queued_count(self, user_id: str, queued_status_id: int) -> int:
        """Wrap ``BT.SP_GET_QUEUED_COUNT`` — active QUEUED count for per-user cap.

        OUT row shape is ``(OUT_COUNT, SQLSTATE, SQLMSG, SQLERRMC)`` — count
        precedes the status triplet, so this cannot use ``_call_write``.
        """
        sql = (
            "CALL bt.sp_get_queued_count("
            "%s::text, %s::integer,"
            " NULL::integer, NULL::text, NULL::text, NULL::text)"
        )
        params = (user_id, int(queued_status_id))

        def work(cur) -> int:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None or len(row) < 4:
                raise RuntimeError("SP_GET_QUEUED_COUNT returned invalid OUT row")
            count, sqlstate, _, sqlerrmc = row[0], row[1], row[2], row[3]
            if sqlstate != "00000":
                raise ProcedureError(
                    proc="bt.sp_get_queued_count",
                    sqlstate=sqlstate,
                    message=sqlerrmc,
                )
            return int(count) if count is not None else 0

        result, held = self._run(work)
        if held is not None:
            held.commit()
        return result

    def list_for_user(self, user_id: str, limit: int = 50) -> list[dict]:
        """Active rows for one user via ``SP_GET_QUEUE`` (includes STRATEGY join)."""
        return self.sp_get_queue(user_id=user_id, limit=limit)

    def queued_position(self, queue_id: uuid.UUID | str, queued_status_id: int) -> int:
        """1-indexed position in the QUEUED ranking (0 if not found).

        Derived from ``sp_get_queue`` result order (PRIORITY ASC, CREATED_AT ASC).
        """
        rows = self.sp_get_queue(queue_status_id=queued_status_id, limit=500)
        qid = str(queue_id)
        for i, row in enumerate(rows, 1):
            if str(row["queue_id"]) == qid:
                return i
        return 0

    def get_active(
        self, queue_id: uuid.UUID | str, user_id: str | None = None
    ) -> dict | None:
        """Active QUEUE row + STRATEGY join via ``SP_GET_QUEUE``.

        Optional ``user_id`` scopes the lookup for ownership enforcement.
        Returns the latest VID (last row, ordered by QUEUE_VID ASC).
        """
        rows = self.sp_get_queue(queue_id=queue_id, user_id=user_id)
        if not rows:
            return None
        return rows[-1]

    def sp_get_result(self, queue_id: uuid.UUID | str) -> dict | None:
        """Wrap ``BT.SP_GET_RESULT`` — latest result row for a queue id."""
        return self._call_get_one(
            "CALL bt.sp_get_result("
            "%s::uuid,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (str(queue_id),),
        )

    def sp_get_strategy(
        self,
        strategy_id: uuid.UUID | str,
        strategy_vid: int | None = None,
        is_best_ind: str | None = None,
    ) -> list[dict]:
        """Wrap ``BT.SP_GET_STRATEGY`` — flexible filter on VID and/or IS_BEST_IND."""
        return self._call_get(
            "CALL bt.sp_get_strategy("
            "%s::uuid, %s::integer, %s::char,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (str(strategy_id), _opt(int, strategy_vid), is_best_ind),
        )

    def sp_get_strategy_list(
        self,
        *,
        user_id: str,
        limit: int = 200,
        is_best_ind: str | None = "Y",
    ) -> list[dict]:
        """Wrap ``BT.SP_GET_STRATEGY_LIST`` — caller-owned catalog for Trade picker."""
        return self._call_get(
            "CALL bt.sp_get_strategy_list("
            "%s::text, %s::integer, %s::char,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (user_id, int(limit), is_best_ind),
        )

