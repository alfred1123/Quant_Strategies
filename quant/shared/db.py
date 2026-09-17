"""Shared database gateway for QuantDB stored procedure calls.

Provides the REFCURSOR drain and write-commit protocol used by all
schema-specific repos (BacktestCache, InstrumentCache, …). REFDATA is no
longer read from Postgres by Python — see ``src/cache.py::RedisRefData``.

Write procs return one row beginning with ``(SQLSTATE, SQLMSG, SQLERRMC)``
(the same prefix as ``BT.SP_INS_QUEUE``). Additional OUT columns, if any,
follow. ``_call_write`` validates the triplet and returns trailing OUT values
as a tuple (often empty).

Each process owns one ``ConnectionPool`` per conninfo. Gateways borrow a
connection for one call and return it — they do not hold sockets.
See decision #69 and ``docs/design/db-connections.md``.
"""

import logging
import os
import re
import threading

from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

_PROC_NAME_RE = re.compile(r"CALL\s+([\w.]+)\s*\(", re.IGNORECASE)

#: Every Fernet token starts with a 0x80 version byte, which base64-encodes to
#: this prefix. Encrypted exchange keys reach _call_write as ordinary strings,
#: so the format is the only thing that marks them as secret.
_FERNET_PREFIX = "gAAAAA"

#: Longest string parameter reproduced verbatim in a log line.
_MAX_LOGGED_PARAM_CHARS = 200

_LOCK = threading.Lock()
_pools: dict[str, ConnectionPool] = {}


def _pool_kwargs() -> dict:
    min_size = int(os.getenv("DB_POOL_MIN", "2"))
    max_size = int(os.getenv("DB_POOL_MAX", "10"))
    if min_size < 1 or max_size < min_size:
        raise ValueError("DB_POOL_MIN must be >= 1 and DB_POOL_MAX >= DB_POOL_MIN")
    return {
        "min_size": min_size,
        "max_size": max_size,
        "timeout": float(os.getenv("DB_POOL_TIMEOUT", "30")),
        "max_idle": float(os.getenv("DB_POOL_MAX_IDLE", "600")),
        "max_lifetime": float(os.getenv("DB_POOL_MAX_LIFETIME", "1800")),
        "check": ConnectionPool.check_connection,
    }


def pool_for(conninfo: str) -> ConnectionPool:
    """Process pool for ``conninfo``. Created on first use."""
    if not conninfo:
        raise ValueError("conninfo is required")
    with _LOCK:
        pool = _pools.get(conninfo)
        if pool is None or pool.closed:
            kwargs = _pool_kwargs()
            pool = ConnectionPool(conninfo, **kwargs)
            _pools[conninfo] = pool
            logger.info(
                "Postgres pool opened min=%s max=%s max_idle=%s max_lifetime=%s",
                kwargs["min_size"],
                kwargs["max_size"],
                kwargs["max_idle"],
                kwargs["max_lifetime"],
            )
        return pool


def open_pool(conninfo: str, *, timeout: float = 15.0) -> ConnectionPool:
    """Create the process pool and wait until ``min_size`` connections are up."""
    pool = pool_for(conninfo)
    pool.wait(timeout=timeout)
    return pool


def close_pools() -> None:
    """Close every pool this process opened. Safe to call repeatedly."""
    with _LOCK:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        try:
            pool.close()
        except Exception:
            logger.debug("Postgres pool close failed", exc_info=True)


def _proc_name_from_sql(sql: str) -> str:
    match = _PROC_NAME_RE.search(sql)
    return match.group(1) if match else "database"


def _redact(params: tuple) -> tuple:
    """Prepare parameters for a log sink — hide secrets, shorten bulk.

    The ciphertext alone does not reveal a key, but logs are handled far more
    loosely than the database — shipped, tailed, pasted into tickets — and
    ciphertext there plus a leaked EXCHANGE_SECRETS_KEY is a plaintext key.
    Matching on the token format rather than the parameter position keeps this
    working for any procedure that carries an encrypted column.

    Length matters for a different reason: a cached price payload is a JSON
    string of every bar in the range, so one API_REQUEST write emitted
    hundreds of KB at INFO and pushed the surrounding lines out of any
    practical `docker logs` window. The head identifies the value; the rest
    only buries whatever was logged next.
    """
    return tuple(_redact_one(p) for p in params)


def _redact_one(param: object) -> object:
    if not isinstance(param, str):
        return param
    if param.startswith(_FERNET_PREFIX):
        return f"<encrypted:{len(param)} chars>"
    if len(param) > _MAX_LOGGED_PARAM_CHARS:
        head = param[:_MAX_LOGGED_PARAM_CHARS]
        return f"{head}...<truncated, {len(param)} chars total>"
    return param


class ProcedureError(RuntimeError):
    """Stored procedure returned a non-``00000`` SQLSTATE."""

    def __init__(self, *, proc: str, sqlstate: str, message: str) -> None:
        self.proc = proc
        self.sqlstate = sqlstate
        self.message = message
        super().__init__(message)


class DbGateway:
    """Concrete base owning conninfo + SP call helpers.

    Encapsulates all psycopg usage. Subclasses add proc wrappers and
    business methods per schema and **never** import psycopg directly.

    Connections come from the process pool. A gateway does not own a
    socket and has no ``close()`` — entry points call ``close_pools()``.
    """

    def __init__(self, conninfo: str, user_id: str = "quant_admin") -> None:
        self._conninfo = conninfo
        self.user_id = user_id

    def _run(self, fn):
        """Borrow a pooled connection, run ``fn(cursor)``, return it.

        The pool context commits on success and rolls back on error.
        """
        with pool_for(self._conninfo).connection() as conn, conn.cursor() as cur:
            return fn(cur)

    def _call_get(self, sql: str, params: tuple) -> list[dict]:
        """CALL a SP_GET proc → drain REFCURSOR → return ``list[dict]``."""
        def work(cur) -> list[dict]:
            cur.execute(sql, params)
            status = cur.fetchone()
            cursor_name, sqlstate = status[0], status[1]
            if sqlstate != "00000":
                cur.execute(f'CLOSE "{cursor_name}"')
                proc = _proc_name_from_sql(sql)
                logger.error(
                    "_call_get failed (SQLSTATE %s) proc=%s: %s — params=%s",
                    sqlstate,
                    proc,
                    status[3],
                    _redact(params),
                )
                raise ProcedureError(proc=proc, sqlstate=sqlstate, message=status[3])
            cur.execute(f'FETCH ALL FROM "{cursor_name}"')
            cols = [desc.name for desc in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute(f'CLOSE "{cursor_name}"')
            logger.info(
                "_call_get returned %d row(s) — params=%s", len(rows), _redact(params)
            )
            return rows

        return self._run(work)

    def _call_get_one(self, sql: str, params: tuple) -> dict | None:
        """CALL a SP_GET proc returning at most one row → first row or ``None``."""
        rows = self._call_get(sql, params)
        return rows[0] if rows else None

    def _call_write(self, sql: str, params: tuple) -> tuple:
        """CALL a SP_INS/SP_UPD proc whose OUT row starts with the status triplet.

        The borrowed connection commits when ``_run`` returns cleanly.
        Returns trailing OUT values (often empty).
        """
        def work(cur) -> tuple:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None or len(row) < 3:
                logger.error(
                    "_call_write: no row or short OUT — params=%s", _redact(params)
                )
                raise RuntimeError("Proc returned no row or invalid OUT shape")
            sqlstate, _sqlmsg, sqlerrmc = row[0], row[1], row[2]
            if sqlstate != "00000":
                proc = _proc_name_from_sql(sql)
                logger.error(
                    "_call_write failed (SQLSTATE %s) proc=%s: %s — params=%s",
                    sqlstate,
                    proc,
                    sqlerrmc,
                    _redact(params),
                )
                raise ProcedureError(proc=proc, sqlstate=sqlstate, message=sqlerrmc)
            return row[3:]

        tail = self._run(work)
        logger.info("_call_write committed — params=%s", _redact(params))
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

        return self._run(work)

    def health_check(self, *, timeout: int = 3) -> None:
        """Probe the process pool — raises on failure, ``None`` on success."""
        with pool_for(self._conninfo).connection(timeout=timeout) as conn:
            conn.execute("SELECT 1")
