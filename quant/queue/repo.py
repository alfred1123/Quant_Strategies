"""Shared SP wrappers for ``BT.QUEUE`` / ``BT.RESULT`` / ``BT.STRATEGY``.

All Postgres access for the backtest queue lives on :class:`BtQueueRepo`.
Reads and writes go through stored procedures — no direct ``SELECT`` in
application code.
"""

import json
import uuid
from typing import Any, TypeVar

from quant.shared.db import DbGateway

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

        New ``STRATEGY_ID`` ⇒ VID=1 (``IS_BEST_IND='Y'``); existing ID ⇒
        prior active row closed (``TRANSACT_TO_TS = now``) and new VID
        inserted as active (``IS_BEST_IND='N'`` until promoted).
        """
        (new_vid,) = self._call_write(
            "CALL bt.sp_ins_strategy("
            "%s::uuid, %s::text, %s::jsonb, %s::text,"
            " NULL::text, NULL::text, NULL::text, NULL::integer)",
            (str(strategy_id), strategy_nm, json.dumps(config_json), user_id),
        )
        return int(new_vid)

    def sp_upd_promote_strategy(
        self,
        *,
        strategy_id: uuid.UUID | str,
        strategy_vid: int | None,
        user_id: str,
    ) -> None:
        """Wrap ``BT.SP_UPD_PROMOTE_STRATEGY``.

        ``strategy_vid=None`` → demote-only (no replacement promoted).
        """
        vid_param = int(strategy_vid) if strategy_vid is not None else None
        self._call_write(
            "CALL bt.sp_upd_promote_strategy("
            "%s::uuid, %s::integer, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (str(strategy_id), vid_param, user_id),
        )

    def sp_ins_promotion(
        self,
        *,
        promotion_id: uuid.UUID,
        queue_id: uuid.UUID | str,
        strategy_id: uuid.UUID | str,
        strategy_vid: int,
        outcome: str,
        user_id: str,
        compared_vid: int | None = None,
        gate_results: list[dict] | None = None,
    ) -> None:
        """Wrap ``BT.SP_INS_PROMOTION``."""
        self._call_write(
            "CALL bt.sp_ins_promotion("
            "%s::uuid, %s::uuid, %s::uuid, %s::integer, %s::text,"
            " %s::integer, %s::jsonb, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(promotion_id),
                str(queue_id),
                str(strategy_id),
                int(strategy_vid),
                outcome,
                compared_vid,
                json.dumps(gate_results) if gate_results else None,
                user_id,
            ),
        )

    # ── reads (SP wrappers) ────────────────────────────────────────────

    def sp_get_queued_count(self, user_id: str, queued_status_id: int) -> int:
        """Wrap ``BT.SP_GET_QUEUED_COUNT`` — active QUEUED count for per-user cap."""
        row = self._call_write(
            "CALL bt.sp_get_queued_count("
            "%s::text, %s::integer,"
            " NULL::integer, NULL::text, NULL::text, NULL::text)",
            (user_id, int(queued_status_id)),
        )
        return int(row[0]) if row and row[0] is not None else 0

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
        rows = self._call_get(
            "CALL bt.sp_get_result("
            "%s::uuid,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (str(queue_id),),
        )
        return rows[0] if rows else None

    def sp_get_strategy(
        self,
        *,
        strategy_id: uuid.UUID | str,
        strategy_vid: int | None = None,
        is_best_ind: str | None = None,
    ) -> dict | None:
        """Wrap ``BT.SP_GET_STRATEGY``.

        Three modes controlled by the caller:
          - ``strategy_vid`` set → exact frozen VID.
          - ``is_best_ind='Y'`` (vid None) → IS_BEST_IND='Y' row.
          - both None → active row (TRANSACT_TO_TS = 9999-12-31).
        """
        rows = self._call_get(
            "CALL bt.sp_get_strategy("
            "%s::uuid, %s::integer, %s::char,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (
                str(strategy_id),
                _opt(int, strategy_vid),
                is_best_ind,
            ),
        )
        return rows[0] if rows else None
