"""BT cache read/write via stored procedures.

Backs the dataset cache that ``run_optimize`` consults before calling out
to a vendor — see ``docs/design/separate-underlying.md``.
"""

import json
import logging
import uuid
from typing import Callable

import pandas as pd

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class BacktestCache(DbGateway):
    """BT cache read/write via stored procedures.

    Holds a long-lived Postgres connection (managed by ``DbGateway``) for
    BT schema SP calls so there is no per-query connect overhead. Uses a
    ``RedisRefData`` reader for denormalized ID lookups (APP_ID, etc.).
    """

    # Hardcoded default — daily bars. All callers omit tm_interval_id; this
    # constant is the single source of truth until a multi-interval UI lands.
    DEFAULT_TM_INTERVAL_ID = 1

    def __init__(self, conninfo: str, refdata, user_id: str = "quant_admin") -> None:
        # ``refdata`` duck-types the legacy RefDataCache surface — only
        # ``.get(table)`` and ``.resolve_app_metric_id(...)`` are used here,
        # both of which RedisRefData implements identically.
        super().__init__(conninfo, user_id, persistent=True)
        self.refdata = refdata

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _to_utc(ts) -> pd.Timestamp | None:
        """Coerce a string/Timestamp/None to a UTC pd.Timestamp."""
        if ts is None or ts == "":
            return None
        out = pd.Timestamp(ts)
        return out.tz_convert("UTC") if out.tzinfo else out.tz_localize("UTC")

    @staticmethod
    def _payload_to_df(payload) -> pd.DataFrame:
        """Convert JSONB payload (list of records) to a DataFrame indexed by datetime (UTC)."""
        if not payload:
            return pd.DataFrame()
        df = pd.DataFrame(payload)
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
            df = df.set_index("datetime").sort_index()
        return df

    @staticmethod
    def _to_utc_index(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure DataFrame's DatetimeIndex is tz-aware UTC."""
        if df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return df
        if df.index.tz is None:
            df = df.copy()
            df.index = df.index.tz_localize("UTC")
        else:
            df = df.copy()
            df.index = df.index.tz_convert("UTC")
        return df

    # ── proc wrappers ──────────────────────────────────────────────────

    def _get_api_request(self, app_id, app_metric_id, tm_interval_id, internal_cusip) -> list[dict]:
        return self._call_get(
            "CALL BT.SP_GET_API_REQUEST(%s, %s, %s, %s, NULL, NULL, NULL, NULL)",
            (app_id, app_metric_id, tm_interval_id, internal_cusip),
        )

    def _insert_api_request(self, api_req_id, app_id, app_metric_id, tm_interval_id, product_grp_id, start_ts, end_ts, payload_json, internal_cusip):
        # Deployed BT.SP_INS_API_REQUEST signature:
        #   (uuid, integer, integer, integer, integer, timestamptz, timestamptz, jsonb, text, text)
        self._call_write(
            "CALL BT.SP_INS_API_REQUEST("
            "%s::uuid, %s::integer, %s::integer, %s::integer, %s::integer, "
            "%s::timestamptz, %s::timestamptz, %s::jsonb, %s::text, %s::text, "
            "NULL::text, NULL::text, NULL::text)",
            (api_req_id, app_id, app_metric_id, tm_interval_id, product_grp_id,
             start_ts, end_ts, payload_json, self.user_id, internal_cusip),
        )

    # ── public API ───────────────────────────────────────────────────────

    class CacheMissError(RuntimeError):
        """Raised when ``refresh=False`` but the cache cannot satisfy the request."""

        def __init__(self, internal_cusip: str | None, requested: tuple[str, str], cached: tuple[pd.Timestamp, pd.Timestamp] | None):
            self.internal_cusip = internal_cusip
            self.requested = requested
            self.cached = cached
            if cached is None:
                msg = (f"No cached data for {internal_cusip!r} covering "
                       f"[{requested[0]}, {requested[1]}]. "
                       f"Tick 'Refresh dataset' to fetch from the provider.")
            else:
                msg = (f"Cached range for {internal_cusip!r} is "
                       f"[{cached[0].date()}, {cached[1].date()}] which does not cover "
                       f"requested [{requested[0]}, {requested[1]}]. "
                       f"Tick 'Refresh dataset' to fetch from the provider.")
            super().__init__(msg)

    def _lookup_current(self, app_id, app_metric_id, tm_interval_id, internal_cusip):
        """Return ``(cached_id, cached_start, cached_end, cached_df)`` for the
        current version, or ``(None, None, None, empty_df)`` if nothing cached.

        Read failures (DB down, SP error) propagate as ``RuntimeError`` — callers
        must decide whether to treat that as a cache miss or surface it. Do **not**
        silently swallow.
        """
        existing = self._get_api_request(app_id, app_metric_id, tm_interval_id, internal_cusip)
        if not existing:
            return None, None, None, pd.DataFrame()
        row = existing[0]
        return (
            row.get("api_req_id"),
            self._to_utc(row.get("range_start_ts")),
            self._to_utc(row.get("range_end_ts")),
            self._payload_to_df(row.get("payload")),
        )

    def read_payload(
        self,
        *,
        app_id: int,
        app_metric_id: int,
        internal_cusip: str | None,
        range_start: str,
        range_end: str,
        tm_interval_id: int | None = None,
    ) -> pd.DataFrame:
        """Read-only cache lookup.

        Returns the cached slice covering ``[range_start, range_end]``. Raises
        :class:`BacktestCache.CacheMissError` when the cached range does not fully
        cover the request. **Never** calls the provider and **never** writes.
        """
        if tm_interval_id is None:
            tm_interval_id = self.DEFAULT_TM_INTERVAL_ID

        req_start = self._to_utc(range_start)
        req_end = self._to_utc(range_end)

        try:
            _, cached_start, cached_end, cached_df = self._lookup_current(
                app_id, app_metric_id, tm_interval_id, internal_cusip,
            )
        except RuntimeError as exc:
            # DB read failed — treat as miss but log loudly. Unlike the write
            # path, a stale cache read is recoverable (user re-ticks Refresh).
            logger.warning("read_payload: SP_GET_API_REQUEST failed for %s: %s", internal_cusip, exc)
            cached_start = cached_end = None
            cached_df = pd.DataFrame()

        covers = (
            cached_start is not None
            and cached_end is not None
            and cached_start <= req_start
            and cached_end >= req_end
        )
        if not covers:
            cached_bounds = (cached_start, cached_end) if cached_start is not None else None
            raise self.CacheMissError(internal_cusip, (range_start, range_end), cached_bounds)

        logger.info(
            "Cache hit (read-only): %s [%s, %s] covers [%s, %s]",
            internal_cusip, cached_start.date(), cached_end.date(), range_start, range_end,
        )
        return cached_df.loc[req_start:req_end]

    def refresh_payload(
        self,
        *,
        app_id: int,
        app_metric_id: int,
        internal_cusip: str | None,
        range_start: str,
        range_end: str,
        fetcher: Callable[[str, str], pd.DataFrame],
        product_grp_id: int | None = None,
        tm_interval_id: int | None = None,
    ) -> pd.DataFrame:
        """Fetch ``[range_start, range_end]`` from the provider and persist a new
        ``API_REQUEST`` version (wholesale replace — no prefix/suffix gap math).

        The cached ``api_req_id`` is reused so the SP closes the old
        ``API_REQ_VID`` and bumps to a new one; a new UUID is allocated only when
        no prior version exists.

        **Contract:** fetch + persist is a single transactional unit. If the
        provider returns data, the SP write is mandatory — failures propagate as
        ``RuntimeError`` (or whatever ``_call_write`` raises). Callers MUST NOT
        wrap this in a bare ``except`` that swallows.
        """
        if tm_interval_id is None:
            tm_interval_id = self.DEFAULT_TM_INTERVAL_ID

        req_start = self._to_utc(range_start)
        req_end = self._to_utc(range_end)

        # Read failures here are fatal — without a definitive answer about whether
        # a row exists, we'd risk allocating a fresh UUID and orphaning the old
        # version (or vice versa). Propagate.
        cached_id, _, _, _ = self._lookup_current(
            app_id, app_metric_id, tm_interval_id, internal_cusip,
        )

        logger.info(
            "Refresh requested: fetching %s [%s, %s] from provider",
            internal_cusip, range_start, range_end,
        )
        fetched = fetcher(range_start, range_end)
        if fetched is None or fetched.empty:
            logger.warning("Provider returned empty data for %s — no new version inserted", internal_cusip)
            return pd.DataFrame()
        fetched = self._to_utc_index(fetched)

        api_req_id = str(cached_id) if cached_id is not None else str(uuid.uuid4())
        payload_records = (
            fetched.reset_index()
            .assign(datetime=lambda d: d["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S"))
            .to_dict(orient="records")
        )
        self._insert_api_request(
            api_req_id=api_req_id,
            app_id=app_id,
            app_metric_id=app_metric_id,
            tm_interval_id=tm_interval_id,
            product_grp_id=product_grp_id,
            start_ts=req_start.strftime("%Y-%m-%d %H:%M:%S+00"),
            end_ts=req_end.strftime("%Y-%m-%d %H:%M:%S+00"),
            payload_json=json.dumps(payload_records),
            internal_cusip=internal_cusip,
        )
        logger.info(
            "Refresh persisted: %s api_req_id=%s rows=%d",
            internal_cusip, api_req_id, len(fetched),
        )
        return fetched.loc[req_start:req_end]
