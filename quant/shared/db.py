"""Shared database gateway for QuantDB stored procedure calls.

Provides the REFCURSOR drain and write-commit protocol used by all
schema-specific repos (BacktestCache, InstrumentCache, …). REFDATA is no
longer read from Postgres by Python — see ``src/cache.py::RedisRefData``.

Write procs return one row beginning with ``(SQLSTATE, SQLMSG, SQLERRMC)``
(the same prefix as ``BT.SP_INS_QUEUE``). Additional OUT columns, if any,
follow. ``_call_write`` validates the triplet and returns trailing OUT values
as a tuple (often empty).
"""

import logging

import psycopg

logger = logging.getLogger(__name__)


class DbGateway:
    """Concrete base owning conninfo + SP call helpers.

    Subclasses add proc wrappers and business methods per schema.
    """

    def __init__(self, conninfo: str, user_id: str = "alfcheun") -> None:
        self._conninfo = conninfo
        self.user_id = user_id

    # ── helpers ──────────────────────────────────────────────────────────

    def _call_get(
        self,
        sql: str,
        params: tuple,
        *,
        conn: psycopg.Connection | None = None,
    ) -> list[dict]:
        """CALL a SP_GET proc → drain REFCURSOR → return list[dict].

        With ``conn``, uses that connection (caller owns lifecycle + rollback on
        error). Without ``conn``, opens a short-lived connection.
        """
        def _refcur_rows(cur) -> list[dict]:
            cur.execute(sql, params)
            status = cur.fetchone()
            cursor_name, sqlstate = status[0], status[1]
            if sqlstate != "00000":
                cur.execute(f'CLOSE "{cursor_name}"')
                logger.error("_call_get failed (SQLSTATE %s): %s — params=%s", sqlstate, status[3], params)
                raise RuntimeError(f"Proc failed (SQLSTATE {sqlstate}): {status[3]}")
            cur.execute(f'FETCH ALL FROM "{cursor_name}"')
            cols = [desc.name for desc in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute(f'CLOSE "{cursor_name}"')
            logger.info("_call_get returned %d row(s) — params=%s", len(rows), params)
            return rows

        if conn is not None:
            try:
                with conn.cursor() as cur:
                    return _refcur_rows(cur)
            except Exception:
                conn.rollback()
                raise
        with psycopg.connect(self._conninfo) as c, c.cursor() as cur:
            return _refcur_rows(cur)

    def _call_write(
        self,
        sql: str,
        params: tuple,
        *,
        conn: psycopg.Connection | None = None,
    ) -> tuple:
        """CALL a SP_INS/SP_UPD proc whose OUT row starts with the status triplet.

        With ``conn``, commits/rolls back on that connection. Without ``conn``,
        uses a short-lived connection (committed by context manager).
        """
        def _tail_from_cursor(cur) -> tuple:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None or len(row) < 3:
                logger.error("_call_write: no row or short OUT — params=%s", params)
                raise RuntimeError("Proc returned no row or invalid OUT shape")
            sqlstate, _sqlmsg, sqlerrmc = row[0], row[1], row[2]
            if sqlstate != "00000":
                logger.error(
                    "_call_write failed (SQLSTATE %s): %s — params=%s",
                    sqlstate,
                    sqlerrmc,
                    params,
                )
                raise RuntimeError(f"Proc failed (SQLSTATE {sqlstate}): {sqlerrmc}")
            return row[3:]

        if conn is not None:
            try:
                with conn.cursor() as cur:
                    tail = _tail_from_cursor(cur)
                conn.commit()
                logger.info("_call_write committed — params=%s", params)
                return tail
            except Exception:
                conn.rollback()
                raise
        with psycopg.connect(self._conninfo) as c, c.cursor() as cur:
            tail = _tail_from_cursor(cur)
        logger.info("_call_write committed — params=%s", params)
        return tail
