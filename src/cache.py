"""Redis caching layer — shared store for REFDATA, price snapshots, and any
other data the coordinator publishes.

Current residents
-----------------
* ``RedisRefData``  — read-only REFDATA accessor (config enums, indicator
  defaults, app/metric ID resolution).  The coordinator loads rows from
  Postgres via ``REFDATA.SP_GET_ENUM`` and publishes them under
  ``refdata:<table>``.  Python processes (FastAPI, workers) read those keys
  only — they never touch Postgres for REFDATA.

* ``DataCaches`` — bundles ``RedisRefData`` + ``InstrumentCache`` +
  ``BacktestCache`` for one DB conninfo + Redis URL (FastAPI ``lifespan`` and
  ``src.worker``).

Adding more data types
----------------------
Add a new class to this module for each additional Redis-backed store
(e.g. ``PriceCache``, ``BacktestResultCache``).  Each class takes a shared
``redis.Redis`` instance (or a ``redis_url`` string) and owns its own key
namespace.

Public surface of ``RedisRefData`` mirrors the legacy ``data.RefDataCache``
so existing call sites need no change:

    cache = RedisRefData(os.environ["REDIS_URL"])
    cache.get("queue_status")               # list[dict]
    cache.get_indicator_defaults()          # dict[str, dict]
    cache.resolve_app_id("yahoo")           # int | None
    cache.resolve_app_metric_id(1, "price") # int | None
    cache.refresh()                         # no-op (writer = coordinator)

Behaviour notes (``RedisRefData``)
-----------------------------------
* Reads go through an in-process dict hydrated lazily on first ``get()``.
  A version stamp at ``refdata:version`` is checked on each hit; if it has
  changed, the local snapshot is dropped and rebuilt.  Keeps long-lived
  FastAPI processes in sync without pub/sub.
* If Redis returns no rows for a table, ``get()`` raises ``ValueError``
  (an empty REFDATA table is a config bug).
* If Redis is unreachable, the constructor does not fail; the first
  ``get()`` raises ``RuntimeError`` so partial outages surface at the right
  log line, not at boot.
"""

from __future__ import annotations

import json
import logging
import os
import sys

import redis

# Pipeline modules (`data` → InstrumentCache, BacktestCache) live in this
# directory.  Ensure it is on sys.path so imports work whether this file was
# loaded as ``cache`` (worker) or ``src.cache`` (FastAPI), with or without a
# prior ``load_config()`` call.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

logger = logging.getLogger(__name__)


def _key(table: str) -> str:
    return f"refdata:{table}"


_VERSION_KEY = "refdata:version"


class RedisRefData:
    """Read-only REFDATA accessor backed by Redis."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        # decode_responses=True so GET returns str (we'll json.loads it).
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._store: dict[str, list[dict]] = {}
        self._version: str | None = None

    # ── internal cache management ───────────────────────────────────────

    def _check_version(self) -> None:
        """Drop the local snapshot if the coordinator has bumped the version."""
        try:
            current = self._r.get(_VERSION_KEY)
        except redis.RedisError as exc:
            raise RuntimeError(f"Redis unavailable: {exc}") from exc
        if current != self._version:
            self._store.clear()
            self._version = current

    def _load_table(self, table: str) -> list[dict]:
        try:
            raw = self._r.get(_key(table))
        except redis.RedisError as exc:
            raise RuntimeError(f"Redis unavailable: {exc}") from exc
        if raw is None:
            raise ValueError(
                f"REFDATA.{table.upper()} not in Redis — coordinator may not have published yet"
            )
        rows = json.loads(raw)
        self._store[table] = rows
        return rows

    # ── public read API (matches legacy RefDataCache) ───────────────────

    def get(self, table: str) -> list[dict]:
        self._check_version()
        rows = self._store.get(table) or self._load_table(table)
        if not rows:
            raise ValueError(f"REFDATA.{table.upper()} is empty")
        return rows

    def get_indicator_defaults(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for r in self.get("indicator"):
            result[r["method_name"]] = {
                "win_min":        r.get("win_min"),
                "win_max":        r.get("win_max"),
                "win_step":       r.get("win_step"),
                "sig_min":        float(r["sig_min"]) if r.get("sig_min") is not None else None,
                "sig_max":        float(r["sig_max"]) if r.get("sig_max") is not None else None,
                "sig_step":       float(r["sig_step"]) if r.get("sig_step") is not None else None,
                "is_bounded_ind": r.get("is_bounded_ind"),
            }
        return result

    def resolve_app_id(self, name: str) -> int | None:
        for r in self.get("app"):
            if r["name"] == name:
                return int(r["app_id"])
        return None

    def resolve_app_metric_id(self, app_id: int, metric_nm: str = "price") -> int | None:
        try:
            rows = self.get("app_metric")
        except ValueError:
            return None
        for r in rows:
            if int(r["app_id"]) == int(app_id) and r["metric_nm"] == metric_nm:
                return int(r["app_metric_id"])
        return None

    def resolve_queue_status_id(self, name: str) -> int:
        for r in self.get("queue_status"):
            if r["name"] == name:
                return int(r["queue_status_id"])
        raise RuntimeError(f"REFDATA.QUEUE_STATUS missing NAME={name!r}")

    # ── for tests / introspection ───────────────────────────────────────

    @property
    def url(self) -> str:
        return self._url

    def ping(self) -> bool:
        try:
            return bool(self._r.ping())
        except redis.RedisError:
            return False


class DataCaches:
    """Redis REFDATA + INST + BT caches wired the same way in API and worker.

    ``BacktestCache`` uses the same ``RedisRefData`` instance as ``refdata``
    so REFDATA.APP / APP_METRIC resolution matches ``run_optimize``."""

    def __init__(self, conninfo: str, redis_url: str) -> None:
        # Import here so ``import src.cache`` stays lightweight (``data`` pulls pandas/futu).
        from data import BacktestCache, InstrumentCache

        self._conninfo = conninfo
        self.refdata = RedisRefData(redis_url)
        self.instrument_cache = InstrumentCache(conninfo)
        self.backtest_cache = BacktestCache(conninfo, refdata=self.refdata)

    @property
    def conninfo(self) -> str:
        return self._conninfo

    def require_redis(self) -> None:
        """Raise if Redis is not reachable (queue worker hard-requires REFDATA)."""
        if not self.refdata.ping():
            raise RuntimeError(f"Redis at {self.refdata.url} is not reachable")

    def load_instruments(self, *, soft_fail: bool = False) -> None:
        """Load all INST products into memory.

        ``soft_fail=True`` (worker): log warning and continue with empty/partial INST.
        ``soft_fail=False`` (API): log exception; same as historical ``api/main`` —
        server still boots with an unprepared ``InstrumentCache``.
        """
        try:
            self.instrument_cache.load_all()
        except Exception:
            if soft_fail:
                logger.warning(
                    "InstrumentCache load failed — proceeding without it",
                    exc_info=True,
                )
            else:
                logger.exception(
                    "Failed to load INST data — product endpoints will be empty",
                )
