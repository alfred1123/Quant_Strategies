"""Shared database gateway for QuantDB stored procedure calls.

Provides the REFCURSOR drain and write-commit protocol used by all
schema-specific repos (RefDataCache, BacktestCache, InstrumentRepo, …).
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

    def _call_get(self, sql: str, params: tuple) -> list[dict]:
        """CALL a SP_GET proc → drain REFCURSOR → return list[dict].

        Opens and closes its own connection. Use ``_drain_cursor`` when
        you already hold an open connection.
        """
        with psycopg.connect(self._conninfo) as conn, conn.cursor() as cur:
            return self._drain_cursor(cur, sql, params)

    def _call_write(self, sql: str, params: tuple) -> None:
        """CALL a SP_INS/SP_UPD proc → check status → commit.

        Raises RuntimeError on a non-00000 SQLSTATE.
        """
        with psycopg.connect(self._conninfo) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            status = cur.fetchone()
            if status[0] != "00000":
                logger.error("_call_write failed (SQLSTATE %s): %s — params=%s", status[0], status[2], params)
                raise RuntimeError(f"Proc failed (SQLSTATE {status[0]}): {status[2]}")
            conn.commit()
            logger.info("_call_write committed — params=%s", params)

    @staticmethod
    def _drain_cursor(cur, sql: str, params: tuple) -> list[dict]:
        """Execute a SP_GET call on an existing cursor and return rows.

        Shared by ``_call_get`` (own connection) and callers that batch
        multiple reads on one connection (e.g. RefDataCache.load_all).
        """
        cur.execute(sql, params)
        status = cur.fetchone()
        cursor_name, sqlstate = status[0], status[1]
        if sqlstate != "00000":
            cur.execute(f'CLOSE "{cursor_name}"')
            logger.error("_drain_cursor failed (SQLSTATE %s): %s — params=%s", sqlstate, status[3], params)
            raise RuntimeError(f"Proc failed (SQLSTATE {sqlstate}): {status[3]}")
        cur.execute(f'FETCH ALL FROM "{cursor_name}"')
        cols = [desc.name for desc in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute(f'CLOSE "{cursor_name}"')
        logger.info("_drain_cursor returned %d row(s) — params=%s", len(rows), params)
        return rows
