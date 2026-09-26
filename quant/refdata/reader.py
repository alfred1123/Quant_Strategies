"""Read-only accessor for the REFDATA and CONFIG snapshots in Redis.

Catalogs live under ``refdata:<table>`` with stamp ``refdata:version``.
Policy rows live under ``config:<table>`` with stamp ``config:version``.
A bump drops only that schema's local rows, so a gate change does not
reload the indicator list.

Behaviour notes
---------------
* If Redis returns no rows for a table, ``get()`` raises ``ValueError``.
* If Redis is unreachable, the constructor does not fail; the first
  ``get()`` raises ``RuntimeError`` so partial outages surface at the
  right log line, not at boot.
"""

import json
import logging
from datetime import time, timedelta

import redis

from quant.shared.intervals import parse_period

logger = logging.getLogger(__name__)


def cache_key(schema: str, table: str) -> str:
    return f"{schema}:{table}"


def version_key(schema: str) -> str:
    return f"{schema}:version"


def invalidate_channel(schema: str) -> str:
    return f"{schema}:invalidate"


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
        self._store: dict[tuple[str, str], list[dict]] = {}
        self._versions: dict[str, str | None] = {}

    def _check_version(self, schema: str) -> None:
        """Drop this schema's local rows if its publisher stamp moved."""
        try:
            current = self._r.get(version_key(schema))
        except redis.RedisError as exc:
            raise RuntimeError(f"Redis unavailable: {exc}") from exc
        if current != self._versions.get(schema):
            for key in [k for k in self._store if k[0] == schema]:
                del self._store[key]
            self._versions[schema] = current

    def _load_table(self, schema: str, table: str) -> list[dict]:
        try:
            raw = self._r.get(cache_key(schema, table))
        except redis.RedisError as exc:
            raise RuntimeError(f"Redis unavailable: {exc}") from exc
        if raw is None:
            raise ValueError(
                f"{schema}.{table} not in Redis — publisher may not have run yet"
            )
        rows = json.loads(raw)
        self._store[(schema, table)] = rows
        return rows

    def get(self, table: str) -> list[dict]:
        """Rows from the REFDATA catalog snapshot."""
        return self._get("refdata", table)

    def get_config(self, table: str) -> list[dict]:
        """Rows from the CONFIG policy snapshot."""
        return self._get("config", table)

    def _get(self, schema: str, table: str) -> list[dict]:
        self._check_version(schema)
        rows = self._store.get((schema, table)) or self._load_table(schema, table)
        if not rows:
            raise ValueError(f"{schema}.{table} is empty")
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
        rows = self.get_config("promotion_metric")
        return sorted(rows, key=lambda r: int(r.get("priority", 999)))

    @staticmethod
    def _listing_exchange_key(listing_exchange: str | None) -> str:
        """Normalize ``INST.PRODUCT.EXCHANGE`` (``''`` when NULL — default crypto calendar)."""
        return (listing_exchange or "").strip()

    @staticmethod
    def _parse_clock(value: time | str | None) -> time | None:
        """A ``MARKET_*_TIME`` as a ``time``. Parsed here, not handed to callers as text.

        psycopg returns a ``time``; the Redis snapshot serialises it to
        ``"HH:MM:SS"`` (``json.dumps(default=str)``), so accept both — the same
        dual-shape ``get_interval_period`` handles for ``PERIOD_LENGTH``.
        """
        if value is None or value == "":
            return None
        if isinstance(value, time):
            return value
        parts = str(value).split(":")
        if len(parts) < 2:
            raise ValueError(f"unrecognised MARKET time: {value!r}")
        seconds = int(float(parts[2])) if len(parts) > 2 else 0
        return time(int(parts[0]), int(parts[1]), seconds)

    @classmethod
    def _format_market_calendar(cls, row: dict) -> dict:
        return {
            "listing_exchange": str(row.get("listing_exchange") or ""),
            "bar_timezone": str(row["bar_timezone"]),
            "market_open_time": cls._parse_clock(row.get("market_open_time")),
            "market_close_time": cls._parse_clock(row.get("market_close_time")),
        }

    def get_market_calendar(self, *, listing_exchange: str | None = None) -> dict:
        """Session calendar for a listing venue (``REFDATA.MARKET_CALENDAR``).

        *listing_exchange* is ``INST.PRODUCT.EXCHANGE``; ``None`` / empty selects
        the default row (``LISTING_EXCHANGE = ''``) used by ``.crypto`` products.
        """
        listing_key = self._listing_exchange_key(listing_exchange)
        for r in self.get("market_calendar"):
            if str(r.get("listing_exchange") or "") == listing_key:
                return self._format_market_calendar(r)
        raise RuntimeError(
            f"REFDATA.MARKET_CALENDAR missing LISTING_EXCHANGE={listing_key!r}"
        )

    def get_execute_offset(self, app_id: int, tm_interval_id: int) -> timedelta:
        """Lead time before bar close for broker + schedule cadence."""
        for r in self.get_config("app_apply_timing"):
            if int(r["app_id"]) == int(app_id) and int(r["tm_interval_id"]) == int(
                tm_interval_id
            ):
                return parse_period(r["execute_offset"])
        raise RuntimeError(
            "CONFIG.APP_APPLY_TIMING missing "
            f"APP_ID={app_id} TM_INTERVAL_ID={tm_interval_id}"
        )

    def get_apply_timing(
        self,
        app_id: int,
        tm_interval_id: int,
        *,
        listing_exchange: str | None = None,
    ) -> dict:
        """Merged listing calendar + broker execute offset for scheduled apply.

        Calendar comes from the product's listing venue; offset from the broker.
        See ``docs/design/ccxt-bar-timezones.md``.
        """
        return {
            **self.get_market_calendar(listing_exchange=listing_exchange),
            "execute_offset": self.get_execute_offset(app_id, tm_interval_id),
        }

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

    def interval_label(self, tm_interval_id: int) -> str:
        """``DISPLAY_NAME`` for a ``TM_INTERVAL_ID``, for text a user reads.

        Falls back to ``NAME``, then to the id itself, because the only callers
        are error messages: one that cannot name an interval must still say
        which one it meant rather than raise on top of the original problem.
        """
        for r in self.get("tm_interval"):
            if int(r["tm_interval_id"]) == int(tm_interval_id):
                return str(r.get("display_name") or r.get("name") or tm_interval_id)
        return str(tm_interval_id)

    def interval_name(self, tm_interval_id: int) -> str:
        """``NAME`` for a ``TM_INTERVAL_ID`` — the token identity is built from.

        Distinct from :meth:`interval_label`, which returns ``DISPLAY_NAME``
        for prose and degrades to the id rather than raise. This one feeds
        ``STRATEGY_NM`` (``TRADE@VENUE:CADENCE``), where a fallback would put
        an id into a lineage key, so a missing row raises instead.
        """
        for r in self.get("tm_interval"):
            if int(r["tm_interval_id"]) == int(tm_interval_id):
                return str(r["name"])
        raise RuntimeError(f"REFDATA.TM_INTERVAL missing TM_INTERVAL_ID={tm_interval_id}")

    def interval_ids(self) -> list[int]:
        """Every ``TM_INTERVAL_ID``, shortest period first.

        The scheduler sweeps intervals rather than deployments, so it needs the
        set to sweep. Ordered by period so a poll pass settles the fast cadences
        before the slow ones.
        """
        rows = self.get("tm_interval")
        return [
            int(r["tm_interval_id"])
            for r in sorted(rows, key=lambda r: parse_period(r["period_length"]))
        ]

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
