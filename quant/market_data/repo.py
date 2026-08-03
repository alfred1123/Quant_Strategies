"""``MARKET_DATA.PRICE_BAR`` access — every read and write goes through an SP."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


def _require(value, name: str) -> None:
    if value is None:
        raise ValueError(f"{name} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} is required")


class PriceBarRepo(DbGateway):
    """SP wrappers for the MARKET_DATA schema.

    Holds a long-lived connection like the other data-layer gateways — the
    live apply path calls this on every scheduler tick.
    """

    def __init__(self, conninfo: str, user_id: str = "quant_admin") -> None:
        super().__init__(conninfo, user_id, persistent=True)

    def get_coverage(self, *, internal_cusip: str, tm_interval_id: int) -> dict | None:
        """Oldest and newest stored bar open times, or ``None`` when empty.

        Two index probes rather than a range scan — this is the cheap
        freshness gate, not a way to count what is stored.
        """
        _require(internal_cusip, "internal_cusip")
        _require(tm_interval_id, "tm_interval_id")
        row = self._call_get_one(
            "CALL market_data.sp_get_price_bar_coverage("
            "%s::text, %s::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (internal_cusip, tm_interval_id),
        )
        if row is None or row.get("max_bar_timestamp") is None:
            return None
        return row

    def get_bars(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        range_start: datetime,
        range_end: datetime,
    ) -> list[dict]:
        """Bars in ``[range_start, range_end]`` inclusive, oldest first."""
        _require(internal_cusip, "internal_cusip")
        _require(tm_interval_id, "tm_interval_id")
        _require(range_start, "range_start")
        _require(range_end, "range_end")
        return self._call_get(
            "CALL market_data.sp_get_price_bar("
            "%s::text, %s::integer, %s::timestamptz, %s::timestamptz,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (internal_cusip, tm_interval_id, range_start, range_end),
        )

    def ins_bar(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        bar_timestamp: datetime,
        open_px: Decimal | float,
        high_px: Decimal | float,
        low_px: Decimal | float,
        close_px: Decimal | float,
        volume: Decimal | float,
    ) -> None:
        """Insert one closed bar.

        A plain INSERT — a repeat of an existing bar raises ``unique_violation``
        rather than being absorbed, so the caller is responsible for passing
        only bars it knows are missing.
        """
        _require(internal_cusip, "internal_cusip")
        _require(tm_interval_id, "tm_interval_id")
        _require(source_app_id, "source_app_id")
        _require(bar_timestamp, "bar_timestamp")
        for name, value in (
            ("open_px", open_px),
            ("high_px", high_px),
            ("low_px", low_px),
            ("close_px", close_px),
            ("volume", volume),
        ):
            _require(value, name)

        self._call_write(
            "CALL market_data.sp_ins_price_bar("
            "%s::text, %s::integer, %s::integer, %s::timestamptz,"
            " %s::numeric, %s::numeric, %s::numeric, %s::numeric, %s::numeric,"
            " %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                internal_cusip,
                tm_interval_id,
                source_app_id,
                bar_timestamp,
                open_px,
                high_px,
                low_px,
                close_px,
                volume,
                self.user_id,
            ),
        )
