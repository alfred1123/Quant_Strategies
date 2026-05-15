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

    Encapsulates all psycopg usage. Subclasses add proc wrappers and
    business methods per schema and **never** import psycopg directly.

    Connection mode is set at construction via ``persistent``:

    - ``persistent=False`` (default) — every call opens and closes a
      short-lived connection (one connect per call).
    - ``persistent=True`` — a single connection is opened at init and
      reused for every call until ``close()`` is invoked. Used by long-
      lived caches (``InstrumentCache``, ``BacktestCache``).
    """

    def __init__(
        self,
        conninfo: str,
        user_id: str = "quant_admin",
        *,
        persistent: bool = False,
    ) -> None:
        self._conninfo = conninfo
        self.user_id = user_id
        self._conn: psycopg.Connection | None = (
            psycopg.connect(conninfo) if persistent else None
        )

    # ── lifecycle ────────────────────────────────────────────────────────

    def close(self) -> None:
        """Release the persistent connection, if any. Safe to call repeatedly."""
        if self._conn is None:
            return
        try:
            self._conn.close()
        except Exception:
            logger.debug("DbGateway connection close failed", exc_info=True)
        finally:
            self._conn = None

    # ── helpers ──────────────────────────────────────────────────────────

    def _run(self, fn):
        """Execute ``fn(cursor)`` on the held connection (if persistent) or
        on a fresh short-lived one. Returns ``(result, conn)`` where ``conn``
        is the held connection or ``None`` for short-lived. Rolls back on
        error.
        """
        if self._conn is not None:
            try:
                with self._conn.cursor() as cur:
                    return fn(cur), self._conn
            except Exception:
                self._conn.rollback()
                raise
        with psycopg.connect(self._conninfo) as c, c.cursor() as cur:
            return fn(cur), None

    def _call_get(self, sql: str, params: tuple) -> list[dict]:
        """CALL a SP_GET proc → drain REFCURSOR → return ``list[dict]``."""
        def work(cur) -> list[dict]:
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

        rows, _ = self._run(work)
        return rows

    def _call_write(self, sql: str, params: tuple) -> tuple:
        """CALL a SP_INS/SP_UPD proc whose OUT row starts with the status triplet.

        Commits on the held connection (persistent mode) or via the
        short-lived connection's commit. Returns trailing OUT values
        (often empty).
        """
        def work(cur) -> tuple:
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

        tail, held = self._run(work)
        if held is not None:
            held.commit()
        logger.info("_call_write committed — params=%s", params)
        return tail

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run a plain SELECT → ``list[dict]``. For introspection / catalog
        queries that don't go through a stored procedure (e.g. ``information_schema``).

        Per AGENTS.md, this MUST NOT be used for INSERT/UPDATE/DELETE on
        application tables — those go through SPs via ``_call_write``.
        """
        def work(cur) -> list[dict]:
            cur.execute(sql, params)
            cols = [desc.name for desc in (cur.description or [])]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        rows, _ = self._run(work)
        return rows

    def health_check(self, *, timeout: int = 3) -> None:
        """Cheap connectivity probe — raises ``psycopg.Error`` on failure,
        returns ``None`` on success. Used by the FastAPI readiness endpoint.
        Always uses a short-lived connection independent of ``persistent``.
        """
        with psycopg.connect(self._conninfo, connect_timeout=timeout) as conn:
            conn.execute("SELECT 1")
