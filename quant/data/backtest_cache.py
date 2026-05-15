"""BT cache read/write via stored procedures.

Backs the dataset cache that ``run_optimize`` consults before calling out
to a vendor — see ``docs/design/separate-underlying.md``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Callable

import pandas as pd
import psycopg

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class BacktestCache(DbGateway):
    """BT cache read/write via stored procedures.

    Uses a long-lived ``bt_conn`` for BT schema SP calls (no per-query connect).
    Uses a ``RedisRefData`` reader for denormalized ID lookups (APP_ID, etc.).
    """

    # Hardcoded default — daily bars. All callers omit tm_interval_id; this
    # constant is the single source of truth until a multi-interval UI lands.
    DEFAULT_TM_INTERVAL_ID = 1

    def __init__(self, conninfo: str, refdata, user_id: str = "alfcheun") -> None:
        # ``refdata`` duck-types the legacy RefDataCache surface — only
        # ``.get(table)`` and ``.resolve_app_metric_id(...)`` are used here,
        # both of which RedisRefData implements identically.
        super().__init__(conninfo, user_id)
        self.refdata = refdata
        self.bt_conn = psycopg.connect(conninfo)

    def close(self) -> None:
        """Release the Postgres connection (optional — tests or shutdown)."""
        try:
            self.bt_conn.close()
        except Exception:
            logger.debug("BacktestCache.bt_conn close failed", exc_info=True)

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
            conn=self.bt_conn,
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
            conn=self.bt_conn,
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

    def get_or_fetch_payload(
        self,
        *,
        app_id: int,
        app_metric_id: int,
        internal_cusip: str | None,
        range_start: str,
        range_end: str,
        fetcher: Callable[[str, str], pd.DataFrame],
        refresh: bool = False,
        product_grp_id: int | None = None,
        tm_interval_id: int | None = None,
    ) -> pd.DataFrame:
        """Return data covering ``[range_start, range_end]``.

        Two modes, controlled by ``refresh``:

        * ``refresh=False`` (default — read-only):
          Read the current cached row via ``SP_GET_API_REQUEST``. If it
          fully covers the requested range, return the slice. Otherwise
          raise :class:`BacktestCache.CacheMissError`. The provider is
          **never** called and **no** new version is inserted.

        * ``refresh=True`` (write — opt-in via UI checkbox):
          Call ``fetcher(range_start, range_end)`` for the **full**
          requested range and insert a new version via
          ``SP_INS_API_REQUEST``. The cached ``api_req_id`` is reused
          (so the SP closes the old ``API_REQ_VID`` and bumps to a new
          one); a new UUID is allocated only when no prior version
          exists. No prefix/suffix gap math — the user explicitly asked
          for a refresh, so we replace the dataset wholesale.
        """
        if tm_interval_id is None:
            tm_interval_id = self.DEFAULT_TM_INTERVAL_ID

        req_start = self._to_utc(range_start)
        req_end = self._to_utc(range_end)

        # 1. Look up existing version
        try:
            existing = self._get_api_request(app_id, app_metric_id, tm_interval_id, internal_cusip)
        except RuntimeError:
            existing = []

        cached_df = pd.DataFrame()
        cached_start = cached_end = None
        cached_id = None
        if existing:
            row = existing[0]
            cached_id = row.get("api_req_id")
            cached_start = self._to_utc(row.get("range_start_ts"))
            cached_end = self._to_utc(row.get("range_end_ts"))
            cached_df = self._payload_to_df(row.get("payload"))

        covers = (
            cached_start is not None
            and cached_end is not None
            and cached_start <= req_start
            and cached_end >= req_end
        )

        # ── Mode 1: read-only ────────────────────────────────────────────
        if not refresh:
            if not covers:
                cached_bounds = (cached_start, cached_end) if cached_start is not None else None
                raise self.CacheMissError(internal_cusip, (range_start, range_end), cached_bounds)
            logger.info(
                "Cache hit (read-only): %s [%s, %s] covers [%s, %s]",
                internal_cusip, cached_start.date(), cached_end.date(), range_start, range_end,
            )
            return cached_df.loc[req_start:req_end]

        # ── Mode 2: refresh — fetch full range, insert new version ───────
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
        try:
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
        except RuntimeError:
            pass  # already logged in _call_write

        return fetched.loc[req_start:req_end]
