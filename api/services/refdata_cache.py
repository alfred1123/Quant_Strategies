"""In-process cache for REFDATA tables (PostgreSQL localhost:5433).

Loaded once at FastAPI startup via ``lifespan``, refreshable via
``POST /api/v1/refdata/refresh``.
"""

import logging
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

REFDATA_TABLES = frozenset({
    "indicator", "signal_type", "asset_type", "data_column",
    "conjunction", "ticker_mapping", "app",
    "api_limit", "tm_interval", "order_state", "trans_state",
})


class RefDataCache:
    """In-process cache for REFDATA tables.

    Thread-safe for reads (immutable snapshot after load).
    """

    def __init__(self, conninfo: str):
        self._conninfo = conninfo
        self._store: dict[str, list[dict[str, Any]]] = {}

    def load_all(self) -> None:
        """Fetch every allow-listed REFDATA table into memory via SP_GET_ENUM."""
        with psycopg.connect(self._conninfo) as conn:
            for table in REFDATA_TABLES:
                try:
                    self._store[table] = self._fetch_table(conn, table)
                except Exception:
                    logger.warning("Failed to load REFDATA.%s — table may not exist yet",
                                   table, exc_info=True)
                    self._store[table] = []
        logger.info("RefDataCache loaded %d tables", len(self._store))

    def get(self, table: str) -> list[dict[str, Any]]:
        if table not in REFDATA_TABLES:
            raise ValueError(f"Unknown REFDATA table: {table}")
        return self._store.get(table, [])

    def get_indicator_defaults(self) -> dict[str, dict]:
        """Return ``{method_name: {win_min, win_max, ..., is_bounded_ind}}``."""
        result = {}
        for r in self.get("indicator"):
            result[r["method_name"]] = {
                "win_min": r.get("win_min"),
                "win_max": r.get("win_max"),
                "win_step": r.get("win_step"),
                "sig_min": float(r["sig_min"]) if r.get("sig_min") is not None else None,
                "sig_max": float(r["sig_max"]) if r.get("sig_max") is not None else None,
                "sig_step": float(r["sig_step"]) if r.get("sig_step") is not None else None,
                "is_bounded_ind": r.get("is_bounded_ind"),
            }
        return result

    def refresh(self) -> None:
        self.load_all()

    @staticmethod
    def _fetch_table(conn, table: str) -> list[dict[str, Any]]:
        """Call REFDATA.SP_GET_ENUM and drain the returned REFCURSOR."""
        with conn.cursor() as cur:
            cur.execute(
                "CALL REFDATA.SP_GET_ENUM(%s, NULL, NULL, NULL, NULL)",
                (table,),
            )
            row = cur.fetchone()
            cursor_name, sqlstate, sqlmsg, sqlerrmc = row[0], row[1], row[2], row[3]

            if sqlstate != "00000":
                raise RuntimeError(
                    f"SP_GET_ENUM({table}) failed — state={sqlstate} msg={sqlerrmc}"
                )

            cur.execute(f'FETCH ALL FROM "{cursor_name}"')
            cols = [desc.name for desc in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute(f'CLOSE "{cursor_name}"')
            return rows
