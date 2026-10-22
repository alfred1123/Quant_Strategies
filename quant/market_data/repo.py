"""``MARKET_DATA.PRICE_BAR`` access — every read and write goes through an SP."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant.shared.db import DbGateway, require_arg

logger = logging.getLogger(__name__)


class PriceBarRepo(DbGateway):
    """SP wrappers for the MARKET_DATA schema.

    MARKET_DATA SP calls go through the process pool via ``DbGateway``.
    """

    def __init__(self, conninfo: str, user_id: str = "quant_admin") -> None:
        super().__init__(conninfo, user_id)

    def get_coverage(
        self, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> dict | None:
        """Oldest and newest stored bar open times, or ``None`` when empty.

        Two index probes rather than a range scan — this is the cheap
        freshness gate, not a way to count what is stored. Scoped to one
        source: another venue's bars say nothing about this one's freshness.
        """
        require_arg(internal_cusip, "internal_cusip")
        require_arg(tm_interval_id, "tm_interval_id")
        require_arg(source_app_id, "source_app_id")
        row = self._call_get_one(
            "CALL market_data.sp_get_price_bar_coverage("
            "%s::text, %s::integer, %s::integer,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (internal_cusip, tm_interval_id, source_app_id),
        )
        if row is None or row.get("max_bar_timestamp") is None:
            return None
        return row

    def get_bars(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        range_start: datetime,
        range_end: datetime,
    ) -> list[dict]:
        """Bars in ``[range_start, range_end]`` inclusive, oldest first.

        One source per call — venues sharing an instrument quote different
        prices, so a blended window is not a series anyone fitted a strategy on.
        """
        require_arg(internal_cusip, "internal_cusip")
        require_arg(tm_interval_id, "tm_interval_id")
        require_arg(source_app_id, "source_app_id")
        require_arg(range_start, "range_start")
        require_arg(range_end, "range_end")
        return self._call_get(
            "CALL market_data.sp_get_price_bar("
            "%s::text, %s::integer, %s::integer, %s::timestamptz, %s::timestamptz,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (internal_cusip, tm_interval_id, source_app_id, range_start, range_end),
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
        require_arg(internal_cusip, "internal_cusip")
        require_arg(tm_interval_id, "tm_interval_id")
        require_arg(source_app_id, "source_app_id")
        require_arg(bar_timestamp, "bar_timestamp")
        for name, value in (
            ("open_px", open_px),
            ("high_px", high_px),
            ("low_px", low_px),
            ("close_px", close_px),
            ("volume", volume),
        ):
            require_arg(value, name)

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
