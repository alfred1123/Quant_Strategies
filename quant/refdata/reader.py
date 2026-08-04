"""Read-only REFDATA accessor backed by Redis.

REFDATA enums (config dimensions like ``queue_status``, ``indicator``,
``app``) are loaded into Redis by :mod:`quant.refdata.publisher`. This
module exposes them to FastAPI request handlers and worker processes.

A version stamp at ``refdata:version`` is checked on every ``get()``; if
the publisher has bumped the version, the local snapshot is dropped and
rebuilt lazily. That keeps long-lived processes in sync without pub/sub.

Behaviour notes
---------------
* If Redis returns no rows for a table, ``get()`` raises ``ValueError``
  (an empty REFDATA table is a config bug).
* If Redis is unreachable, the constructor does not fail; the first
  ``get()`` raises ``RuntimeError`` so partial outages surface at the
  right log line, not at boot.
"""

import json
import logging
from datetime import timedelta

import redis

from quant.shared.intervals import parse_period

logger = logging.getLogger(__name__)


def _key(table: str) -> str:
    return f"refdata:{table}"


_VERSION_KEY = "refdata:version"


class RedisRefData:
    """Read-only REFDATA accessor backed by Redis."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        # decode_responses=True so GET returns str (we'll json.loads it).
        # Short connect/read timeouts so REFDATA endpoints fail fast (503 via
        # ValueError) when Redis is down — otherwise the FastAPI worker hangs
        # for the OS default (~2 minutes) while the frontend dropdowns sit
        # empty. retry_on_timeout=False keeps the failure surface deterministic.
        self._r = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._store: dict[str, list[dict]] = {}
        self._version: str | None = None

    # ── internal cache management ───────────────────────────────────────

    def _check_version(self) -> None:
        """Drop the local snapshot if the publisher has bumped the version."""
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
                f"REFDATA.{table.upper()} not in Redis — publisher may not have run yet"
            )
        rows = json.loads(raw)
        self._store[table] = rows
        return rows

    # ── public read API ─────────────────────────────────────────────────

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

    def get_promotion_metrics(self) -> list[dict]:
        """Return PROMOTION_METRIC rows sorted by priority.

        Each row has: metric_key, direction, requirement_type, priority, threshold.
        """
        rows = self.get("promotion_metric")
        return sorted(rows, key=lambda r: int(r.get("priority", 999)))

    def get_interval_period(self, tm_interval_id: int) -> timedelta:
        """``PERIOD_LENGTH`` for a ``TM_INTERVAL_ID``, as a timedelta.

        Parsed here rather than handed to callers as text: the publisher
        serialises rows with ``json.dumps(default=str)``, so the Postgres
        interval arrives from Redis stringified (``"1 day, 0:00:00"``).
        """
        for r in self.get("tm_interval"):
            if int(r["tm_interval_id"]) == int(tm_interval_id):
                return parse_period(r["period_length"])
        raise RuntimeError(f"REFDATA.TM_INTERVAL missing TM_INTERVAL_ID={tm_interval_id}")

    def resolve_interval_id(self, period: timedelta) -> int:
        """``TM_INTERVAL_ID`` whose ``PERIOD_LENGTH`` equals *period*.

        The inverse of :meth:`get_interval_period` — for code that knows the
        cadence it needs (e.g. daily bars for an unscheduled live apply) but
        must take the id from REFDATA rather than hardcode it.
        """
        for r in self.get("tm_interval"):
            if parse_period(r["period_length"]) == period:
                return int(r["tm_interval_id"])
        raise RuntimeError(f"REFDATA.TM_INTERVAL has no row with PERIOD_LENGTH={period}")

    def resolve_queue_status_id(self, name: str) -> int:
        for r in self.get("queue_status"):
            if r["name"] == name:
                return int(r["queue_status_id"])
        raise RuntimeError(f"REFDATA.QUEUE_STATUS missing NAME={name!r}")

    def get_promotion_states(self) -> list[str]:
        """Return the valid PROMOTION_STATE names from REFDATA."""
        return [r["name"] for r in self.get("promotion_state")]

    def validate_promotion_state(self, name: str) -> str:
        """Validate a promotion state name against REFDATA. Returns the name or raises."""
        valid = self.get_promotion_states()
        if name not in valid:
            raise RuntimeError(
                f"REFDATA.PROMOTION_STATE missing NAME={name!r} (valid: {valid})"
            )
        return name

    # ── for tests / introspection ───────────────────────────────────────

    @property
    def url(self) -> str:
        return self._url

    def ping(self) -> bool:
        try:
            return bool(self._r.ping())
        except redis.RedisError:
            return False
