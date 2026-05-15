"""Publish REFDATA tables from Postgres into Redis.

Replaces ``coordinator/src/refdata/cache.ts``. Discovers every table in the
``refdata`` schema, calls ``REFDATA.SP_GET_ENUM`` for each, and writes the
JSON-serialised rows under ``refdata:<table>``. Bumps ``refdata:version`` so
long-lived ``RedisRefData`` readers in FastAPI / workers see the change on
their next ``get()``.

Run modes
---------
* As a library — call ``RefDataPublisher(conninfo, redis_url).publish_all()``
  from FastAPI's ``lifespan`` hook so REFDATA is always populated when the
  API process boots.
* As a CLI — ``python -m src.refdata_publisher`` for ad-hoc reseeding (the
  ``POST /api/v1/refdata/refresh`` admin endpoint also calls into the same
  ``publish_all()``).

Key shape exactly matches the legacy TS coordinator (``refdata:<table>``,
``refdata:version``, ``refdata:invalidate``) so ``RedisRefData`` reads
unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import sys

import redis

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


REFDATA_KEY_PREFIX = "refdata:"
REFDATA_VERSION_KEY = "refdata:version"
REFDATA_INVALIDATE_CHANNEL = "refdata:invalidate"


def _key(table: str) -> str:
    return f"{REFDATA_KEY_PREFIX}{table}"


class RefDataPublisher(DbGateway):
    """Loads all REFDATA tables and publishes them atomically to Redis."""

    def __init__(self, conninfo: str, redis_url: str) -> None:
        super().__init__(conninfo)
        self._redis = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )

    # ── load ────────────────────────────────────────────────────────────

    def _discover_tables(self) -> list[str]:
        rows = self._query(
            """
            SELECT table_name
              FROM information_schema.tables
             WHERE table_schema = 'refdata'
               AND table_type   = 'BASE TABLE'
               AND table_name NOT IN ('databasechangelog', 'databasechangeloglock')
             ORDER BY table_name
            """
        )
        return [r["table_name"] for r in rows]

    def _fetch_enum(self, table: str) -> list[dict]:
        """CALL REFDATA.SP_GET_ENUM(table) → list[dict]."""
        return self._call_get(
            "CALL refdata.sp_get_enum(%s, NULL, NULL, NULL, NULL)",
            (table,),
        )

    # ── publish ─────────────────────────────────────────────────────────

    def publish_all(self) -> int:
        """Load every REFDATA table and atomically publish to Redis.

        Returns the number of tables published. Raises ``redis.RedisError``
        if Redis is unreachable — REFDATA is required for both the API and
        worker, so the caller (FastAPI lifespan) should fail fast.
        """
        tables = self._discover_tables()
        snapshot: dict[str, list[dict]] = {}
        for t in tables:
            try:
                snapshot[t] = self._fetch_enum(t)
            except Exception:
                logger.warning("refdata: failed to load %s", t, exc_info=True)
                snapshot[t] = []

        # Atomic from the writer's perspective: one round-trip, all keys
        # land before the version bump that triggers reader refresh.
        pipe = self._redis.pipeline(transaction=True)
        for table, rows in snapshot.items():
            pipe.set(_key(table), json.dumps(rows, default=str))
        pipe.incr(REFDATA_VERSION_KEY)
        pipe.execute()

        # Best-effort fan-out for any subscribers that want push notification.
        try:
            self._redis.publish(REFDATA_INVALIDATE_CHANNEL, "*")
        except redis.RedisError:
            logger.debug("refdata: invalidate publish failed (non-fatal)", exc_info=True)

        logger.info(
            "refdata: published %d tables (%s)",
            len(snapshot),
            ", ".join(sorted(snapshot.keys())),
        )
        return len(snapshot)


def main() -> int:
    """CLI entrypoint: python -m src.refdata_publisher."""
    from api.config import get_redis_url, load_config

    conninfo = load_config()
    RefDataPublisher(conninfo, get_redis_url()).publish_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
