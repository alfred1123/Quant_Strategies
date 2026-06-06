"""Shared SP wrappers + reads for ``BT.QUEUE`` / ``BT.RESULT`` / ``BT.STRATEGY``.

All Postgres access for the backtest queue lives on :class:`BtQueueRepo`.
Writes go through ``BT.SP_INS_QUEUE`` and ``BT.SP_INS_STRATEGY``. Reads
use stored procedures where one fits the projection
(``sp_get_queue``, ``sp_get_queue_latest``); the remaining reads —
aggregates, window-function ranking, and joins not covered by the SPs —
are direct ``SELECT``s on this class so callers never inline SQL.
"""

import json
import uuid
from typing import Any, TypeVar

from quant.shared.db import DbGateway

T = TypeVar("T")

# Sentinel for the soft-versioning open-ended TRANSACT_TO_TS used across BT.*.
ACTIVE_TS = "9999-12-31 00:00:00+00"


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
        rows = self._call_get(
            "CALL bt.sp_get_queue_latest(%s::uuid, NULL, NULL, NULL, NULL)",
            (str(queue_id),),
        )
        return rows[0] if rows else None

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
        strategy_id: uuid.UUID | str,
        strategy_nm: str,
        config_json: dict[str, Any],
        user_id: str,
    ) -> int:
        """Wrap ``BT.SP_INS_STRATEGY`` — returns the assigned ``STRATEGY_VID``.

        New ``STRATEGY_ID`` ⇒ VID=1; existing ID ⇒ prior current row flipped
        to ``IS_CURRENT_IND='N'`` and new row inserted as next VID.
        """
        (new_vid,) = self._call_write(
            "CALL bt.sp_ins_strategy("
            "%s::uuid, %s::text, %s::jsonb, %s::text,"
            " NULL::text, NULL::text, NULL::text, NULL::integer)",
            (str(strategy_id), strategy_nm, json.dumps(config_json), user_id),
        )
        return int(new_vid)

    # ── reads (direct SELECT — no SP covers these projections) ──────────

    def count_queued_for_user(self, user_id: str, queued_status_id: int) -> int:
        """Active QUEUED row count for one user — used to enforce per-user cap."""
        rows = self._query(
            "SELECT COUNT(*)::INTEGER AS n FROM BT.QUEUE"
            " WHERE TRANSACT_TO_TS = %s::timestamptz"
            "   AND QUEUE_STATUS_ID = %s"
            "   AND USER_ID = %s",
            (ACTIVE_TS, int(queued_status_id), user_id),
        )
        return int(rows[0]["n"]) if rows else 0

    def list_for_user(self, user_id: str, limit: int = 50) -> list[dict]:
        """Active rows for one user with ``STRATEGY_NM`` + ``CONFIG_JSON`` + result sharpe join."""
        return self._query(
            "SELECT q.QUEUE_ID, q.QUEUE_VID, q.STRATEGY_ID, q.STRATEGY_VID,"
            "       s.STRATEGY_NM, s.CONFIG_JSON,"
            "       q.QUEUE_STATUS_ID,"
            "       (SELECT NAME FROM REFDATA.QUEUE_STATUS"
            "         WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,"
            "       q.PRIORITY, q.USER_ID, q.TRANSACT_FROM_TS, q.ERROR_TEXT,"
            "       r.BEST_SHARPE, r.TOTAL_TRIALS"
            "  FROM BT.QUEUE q"
            "  LEFT JOIN BT.STRATEGY s ON s.STRATEGY_ID = q.STRATEGY_ID"
            "                         AND s.STRATEGY_VID = q.STRATEGY_VID"
            "  LEFT JOIN LATERAL ("
            "    SELECT (PAYLOAD_JSON->'best'->>'sharpe')::NUMERIC AS BEST_SHARPE,"
            "           (PAYLOAD_JSON->>'total_trials')::INTEGER AS TOTAL_TRIALS"
            "      FROM BT.RESULT"
            "     WHERE QUEUE_ID = q.QUEUE_ID"
            "     ORDER BY CREATED_AT DESC LIMIT 1"
            "  ) r ON TRUE"
            " WHERE q.TRANSACT_TO_TS = %s::timestamptz"
            "   AND q.USER_ID = %s"
            " ORDER BY q.PRIORITY ASC, q.TRANSACT_FROM_TS ASC"
            " LIMIT %s",
            (ACTIVE_TS, user_id, int(limit)),
        )

    def queued_position(self, queue_id: uuid.UUID | str, queued_status_id: int) -> int:
        """1-indexed position in the QUEUED ranking (0 if not found).

        ROW_NUMBER() over the full active-QUEUED set — no equivalent SP.
        """
        rows = self._query(
            "WITH ranked AS ("
            "  SELECT QUEUE_ID, ROW_NUMBER() OVER ("
            "    ORDER BY PRIORITY ASC, TRANSACT_FROM_TS ASC) AS pos"
            "    FROM BT.QUEUE"
            "   WHERE TRANSACT_TO_TS = %s::timestamptz"
            "     AND QUEUE_STATUS_ID = %s"
            ") SELECT pos FROM ranked WHERE QUEUE_ID = %s::uuid",
            (ACTIVE_TS, int(queued_status_id), str(queue_id)),
        )
        return int(rows[0]["pos"]) if rows else 0

    def get_active(
        self, queue_id: uuid.UUID | str, user_id: str | None = None
    ) -> dict | None:
        """Active QUEUE row + STRATEGY_NM/CONFIG_JSON + status text.

        Optional ``user_id`` scopes the lookup so the router can enforce
        ownership without branching 404 vs 403. Wider projection than
        either ``SP_GET_QUEUE`` or ``SP_GET_QUEUE_LATEST``.
        """
        sql = (
            "SELECT q.QUEUE_ID, q.QUEUE_VID, q.STRATEGY_ID, q.STRATEGY_VID,"
            "       s.STRATEGY_NM, s.CONFIG_JSON,"
            "       q.QUEUE_STATUS_ID,"
            "       (SELECT NAME FROM REFDATA.QUEUE_STATUS"
            "         WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,"
            "       q.PRIORITY, q.USER_ID, q.TRANSACT_FROM_TS, q.ERROR_TEXT"
            "  FROM BT.QUEUE q"
            "  LEFT JOIN BT.STRATEGY s ON s.STRATEGY_ID = q.STRATEGY_ID"
            "                         AND s.STRATEGY_VID = q.STRATEGY_VID"
            " WHERE q.QUEUE_ID = %s::uuid"
            "   AND q.TRANSACT_TO_TS = %s::timestamptz"
        )
        params: tuple = (str(queue_id), ACTIVE_TS)
        if user_id is not None:
            sql += " AND q.USER_ID = %s"
            params = params + (user_id,)
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def get_result(self, queue_id: uuid.UUID | str) -> dict | None:
        """Latest ``BT.RESULT`` row for a queue id."""
        rows = self._query(
            "SELECT RESULT_ID, PAYLOAD_JSON"
            "  FROM BT.RESULT"
            " WHERE QUEUE_ID = %s::uuid"
            " ORDER BY CREATED_AT DESC"
            " LIMIT 1",
            (str(queue_id),),
        )
        return rows[0] if rows else None

    def soft_delete(self, queue_id: uuid.UUID | str) -> None:
        """Soft-delete a job by closing its active row (set TRANSACT_TO_TS = now()).

        This hides the job from user queries without losing audit history.
        """
        def work(cur):
            cur.execute(
                "UPDATE BT.QUEUE SET TRANSACT_TO_TS = NOW()"
                " WHERE QUEUE_ID = %s::uuid AND TRANSACT_TO_TS = %s::timestamptz",
                (str(queue_id), ACTIVE_TS),
            )
            return cur.rowcount

        count, held = self._run(work)
        if held is not None:
            held.commit()
