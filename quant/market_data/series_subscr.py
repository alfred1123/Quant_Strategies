"""Standing requests to keep one source of a product.

Every source is a row in ``MARKET_DATA.SERIES_SUBSCR``. A venue's bars
have a null metric. A provider series names its metric. The Data tab reads
:meth:`SeriesSubscrRepo.sp_get_series_subscr`. Capture writes a venue
row through the same insert.

This is the only wrapper over the table's procedures. The venue view
(:class:`~quant.market_data.subscriptions.BarSubscriptionService`) and the
warmer inject this repo rather than calling the procedures themselves.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from quant.shared.db import DbGateway

INS_SQL = (
    "CALL market_data.sp_ins_series_subscr("
    "%s::uuid, %s::text, %s::integer, %s::integer, %s::integer,"
    " %s::char(1), %s::timestamptz, %s::text,"
    " NULL::text, NULL::text, NULL::text)"
)

GET_SQL = (
    "CALL market_data.sp_get_series_subscr("
    "NULL::refcursor, NULL::text, NULL::text, NULL::text)"
)


def _require(value, name: str) -> None:
    if value is None:
        raise ValueError(f"{name} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} is required")


class SeriesSubscrRepo(DbGateway):
    """SP wrapper for ``MARKET_DATA.SERIES_SUBSCR``."""

    def sp_ins_series_subscr(
        self,
        *,
        series_subscr_id: UUID,
        internal_cusip: str,
        app_id: int,
        app_metric_id: int | None,
        tm_interval_id: int,
        is_enabled_ind: str,
        backfill_from_ts: datetime | None = None,
    ) -> dict:
        """Append a version of this id — create, enable, disable or retarget.

        The id is the row the system writes. A null metric is a venue's bars.
        """
        _require(series_subscr_id, "series_subscr_id")
        _require(internal_cusip, "internal_cusip")
        _require(app_id, "app_id")
        _require(tm_interval_id, "tm_interval_id")
        if is_enabled_ind not in ("Y", "N"):
            raise ValueError(f"is_enabled_ind must be Y or N, got {is_enabled_ind!r}")

        self._call_write(
            INS_SQL,
            (
                str(series_subscr_id),
                internal_cusip,
                app_id,
                app_metric_id,
                tm_interval_id,
                is_enabled_ind,
                backfill_from_ts,
                self.user_id,
            ),
        )
        wanted = str(series_subscr_id)
        rows = [
            row
            for row in self.sp_get_series_subscr()
            if str(row.get("series_subscr_id")) == wanted
        ]
        if not rows:
            raise RuntimeError(
                "SP_INS_SERIES_SUBSCR succeeded but SP_GET returned no row "
                f"for {wanted}"
            )
        return rows[0]

    def subscribe(
        self,
        *,
        internal_cusip: str,
        app_id: int,
        app_metric_id: int,
        tm_interval_id: int,
        is_enabled_ind: str,
        backfill_from_ts: datetime | None = None,
        series_subscr_id: UUID | None = None,
    ) -> dict:
        """Create a provider series, or version the open row for that series.

        The table's open row is unique on the id, not on the series. A second
        subscribe for the same source, metric, interval and product reuses
        the id already open so the list does not grow a duplicate.
        """
        _require(app_metric_id, "app_metric_id")
        chosen = series_subscr_id or self._open_provider_id(
            internal_cusip=internal_cusip,
            app_id=app_id,
            app_metric_id=app_metric_id,
            tm_interval_id=tm_interval_id,
        )
        return self.sp_ins_series_subscr(
            series_subscr_id=chosen or uuid.uuid4(),
            internal_cusip=internal_cusip,
            app_id=app_id,
            app_metric_id=app_metric_id,
            tm_interval_id=tm_interval_id,
            is_enabled_ind=is_enabled_ind,
            backfill_from_ts=backfill_from_ts,
        )

    def _open_provider_id(
        self,
        *,
        internal_cusip: str,
        app_id: int,
        app_metric_id: int,
        tm_interval_id: int,
    ) -> UUID | None:
        for row in self.sp_get_series_subscr():
            if row.get("app_metric_id") is None:
                continue
            if (
                row["internal_cusip"] == internal_cusip
                and int(row["app_id"]) == int(app_id)
                and int(row["app_metric_id"]) == int(app_metric_id)
                and int(row["tm_interval_id"]) == int(tm_interval_id)
            ):
                return UUID(str(row["series_subscr_id"]))
        return None

    def sp_get_series_subscr(self) -> list[dict]:
        """Current rows, including one whose window is not stored yet."""
        return self._call_get(GET_SQL, ())

    def sp_get_active_bar_subscriptions(self) -> list[dict]:
        """Enabled venue ``(tm_interval_id, internal_cusip, app_id)`` rows, for the warmer."""
        return self._call_get(
            "CALL market_data.sp_get_active_bar_subscriptions("
            "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (),
        )

