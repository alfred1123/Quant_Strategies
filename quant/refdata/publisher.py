"""Publish REFDATA and CONFIG tables from Postgres into Redis.

Discovers every table in the ``refdata`` and ``config`` schemas, calls
that schema's ``SP_GET_ENUM``, and writes the rows under its own prefix:
``refdata:<table>`` or ``config:<table>``. Each schema has its own version
stamp, so a reader drops only the snapshot that changed.

Run modes
---------
* As a library — call ``RefDataPublisher(conninfo, redis_url).publish_all()``
  from FastAPI's ``lifespan`` hook so both snapshots are populated when the
  API process boots.
* As a CLI — ``python -m quant.refdata.publisher`` publishes both snapshots.
  ``POST /api/v1/refdata/refresh`` publishes catalogs only.
  ``POST /api/v1/config/refresh`` publishes policy rows only.
"""

import json
import logging
import os
import sys

import redis

from quant.refdata.reader import cache_key, invalidate_channel, version_key
from quant.shared.db import DbGateway, close_pools, open_pool

logger = logging.getLogger(__name__)

_ENUM_SQL = {
    "refdata": "CALL refdata.sp_get_enum(%s, NULL, NULL, NULL, NULL)",
    "config": "CALL config.sp_get_enum(%s, NULL, NULL, NULL, NULL)",
}


class RefDataPublisher(DbGateway):
    """Loads REFDATA and CONFIG tables and publishes them atomically to Redis."""

    def __init__(self, conninfo: str, redis_url: str) -> None:
        super().__init__(conninfo)
        self._redis = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )

    # ── load ────────────────────────────────────────────────────────────

    def _discover_tables(self, schema: str) -> list[str]:
        rows = self._query(
            """
            SELECT table_name
              FROM information_schema.tables
             WHERE table_schema = %s
               AND table_type   = 'BASE TABLE'
               AND table_name NOT IN ('databasechangelog', 'databasechangeloglock')
             ORDER BY table_name
            """,
            (schema,),
        )
        return [r["table_name"] for r in rows]

    def _fetch_enum(self, schema: str, table: str) -> list[dict]:
        """CALL that schema's SP_GET_ENUM(table) → list[dict]."""
        return self._call_get(_ENUM_SQL[schema], (table,))

    # ── publish ─────────────────────────────────────────────────────────

    def publish_all(self) -> int:
        """Publish both snapshots. Startup and the CLI use this."""
        return self.publish("refdata") + self.publish("config")

    def publish(self, schema: str) -> int:
        """Publish one schema under its own Redis prefix and version stamp."""
        if schema not in ("refdata", "config"):
            raise ValueError(f"unknown snapshot schema {schema!r}")
        tables = self._discover_tables(schema)
        snapshot: dict[str, list[dict]] = {}
        for table in tables:
            try:
                snapshot[table] = self._fetch_enum(schema, table)
            except Exception:
                logger.warning("%s: failed to load %s", schema, table, exc_info=True)
                snapshot[table] = []

        pipe = self._redis.pipeline(transaction=True)
        owned = set(snapshot)
        for table, rows in snapshot.items():
            pipe.set(cache_key(schema, table), json.dumps(rows, default=str))
        for key in self._redis.scan_iter(match=f"{schema}:*"):
            table = key.removeprefix(f"{schema}:")
            if table in owned or table in ("version", "invalidate"):
                continue
            pipe.delete(key)
        pipe.incr(version_key(schema))
        pipe.execute()

        try:
            self._redis.publish(invalidate_channel(schema), "*")
        except redis.RedisError:
            logger.debug("%s: invalidate publish failed (non-fatal)", schema, exc_info=True)

        logger.info(
            "%s: published %d tables (%s)",
            schema,
            len(snapshot),
            ", ".join(sorted(snapshot)),
        )
        return len(snapshot)


def main() -> int:
    """CLI entrypoint: python -m src.refdata_publisher."""
    from quant.shared.config import get_redis_url, load_config

    conninfo = load_config()
    try:
        open_pool(conninfo)
        RefDataPublisher(conninfo, get_redis_url()).publish_all()
        return 0
    finally:
        close_pools()


if __name__ == "__main__":
    sys.exit(main())
