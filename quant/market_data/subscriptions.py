"""Standing requests to keep a bar series warm, with no deployment behind them.

Capture used to be a side effect of trading: the warmer read
``TRADE.SP_GET_SCHEDULED_INSTRUMENTS``, so history for a product only began
accruing once a strategy was already deployed against it — after the decision
the history was supposed to inform. A subscription is the second answer to
*which instruments matter*, and it needs no credential, no strategy and no
quantity, because bars are public and ``PriceBarService`` already knows how to
fetch and store them.

Subscriptions are **platform-wide**, not per user. A bar is a shared fact, so
one row per series is the honest model: whoever subscribes captures for
everybody, and the list is visible to everybody. Disabling one therefore stops
the capture for all of them — accepted, and the reason the row and its version
history are not hidden behind an owner.

What is deliberately **not** here is any background crawler. ``BACKFILL_FROM_TS``
records how far back history is wanted; filling toward it stays an explicit call
that reports what it could not get.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from uuid import UUID

from quant.market_data.service import (
    MAX_BACKFILL_BARS,
    BackfillResult,
    BarServiceFactory,
)
from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)

_OPEN_ROW_UNIQUE_VIOLATION = "23505"


class SubscriptionError(ValueError):
    """The subscription cannot be honoured — the caller has to change it."""


def _require(value, name: str) -> None:
    if value is None:
        raise ValueError(f"{name} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} is required")


class BarSubscriptionRepo(DbGateway):
    """SP wrappers for ``MARKET_DATA.BAR_SUBSCRIPTION``."""

    def sp_ins_bar_subscription(
        self,
        *,
        bar_subscription_id: UUID,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        is_enabled_ind: str,
        backfill_from_ts: datetime | None = None,
    ) -> dict:
        """Append a version — create, enable, disable or retarget — and read it back.

        Read-back rather than OUT columns, matching ``TradeRepo.write_deployment``:
        the caller wants the row as the UI will see it, including the VID the
        procedure chose.
        """
        _require(bar_subscription_id, "bar_subscription_id")
        _require(internal_cusip, "internal_cusip")
        _require(tm_interval_id, "tm_interval_id")
        _require(source_app_id, "source_app_id")
        if is_enabled_ind not in ("Y", "N"):
            raise ValueError(f"is_enabled_ind must be Y or N, got {is_enabled_ind!r}")

        self._call_write(
            "CALL market_data.sp_ins_bar_subscription("
            "%s::uuid, %s::text, %s::integer, %s::integer,"
            " %s::char(1), %s::timestamptz, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(bar_subscription_id),
                internal_cusip,
                tm_interval_id,
                source_app_id,
                is_enabled_ind,
                backfill_from_ts,
                self.user_id,
            ),
        )
        rows = self.sp_get_bar_subscription(bar_subscription_id=bar_subscription_id)
        if not rows:
            raise RuntimeError(
                "SP_INS_BAR_SUBSCRIPTION succeeded but SP_GET returned no row: "
                f"{bar_subscription_id}"
            )
        return rows[0]

    def sp_get_bar_subscription(
        self, *, bar_subscription_id: UUID | None = None
    ) -> list[dict]:
        """Current rows, disabled ones included."""
        return self._call_get(
            "CALL market_data.sp_get_bar_subscription("
            "%s::uuid,"
            " NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (str(bar_subscription_id) if bar_subscription_id else None,),
        )

    def sp_get_active_bar_subscriptions(self) -> list[dict]:
        """Enabled (tm_interval_id, internal_cusip, app_id) rows, for the warmer."""
        return self._call_get(
            "CALL market_data.sp_get_active_bar_subscriptions("
            "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (),
        )


class SubscriptionInstrumentSource:
    """The subscribed half of the warmer's instrument list."""

    def __init__(self, repo: BarSubscriptionRepo) -> None:
        self._repo = repo

    def instruments(self) -> list[dict]:
        return self._repo.sp_get_active_bar_subscriptions()


class BarSubscriptionService:
    """Subscribe, list with coverage, and fill history on request."""

    def __init__(
        self,
        repo: BarSubscriptionRepo,
        instruments,
        bar_services: BarServiceFactory,
    ) -> None:
        self._repo = repo
        self._instruments = instruments
        self._bar_services = bar_services

    def subscribe(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        is_enabled_ind: str = "Y",
        backfill_from_ts: datetime | None = None,
        bar_subscription_id: UUID | None = None,
    ) -> dict:
        """Create a subscription, or version an existing one.

        Validation happens here rather than at warm time. A series is only
        warmable if the venue resolves to an exchange this platform can read and
        the product maps to a symbol that exchange knows; leaving both to the
        warmer turns one immediate, fixable error into a silent failure repeated
        every tick, in a log nobody is watching.
        """
        self._reject_unwarmable(
            internal_cusip=internal_cusip, source_app_id=source_app_id
        )
        try:
            return self._repo.sp_ins_bar_subscription(
                bar_subscription_id=bar_subscription_id or uuid.uuid4(),
                internal_cusip=internal_cusip,
                tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
                is_enabled_ind=is_enabled_ind,
                backfill_from_ts=backfill_from_ts,
            )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) != _OPEN_ROW_UNIQUE_VIOLATION:
                raise
            # The partial unique index caught a second open row for this series.
            # Reached by subscribing to something already being captured — and
            # since subscriptions are shared, that may be somebody else's row.
            raise SubscriptionError(
                f"{internal_cusip} on interval {tm_interval_id} from app "
                f"{source_app_id} is already being captured — edit that "
                f"subscription instead of creating a second one"
            ) from exc

    def list_subscriptions(self) -> list[dict]:
        """Every subscription, each with what has actually been captured.

        The question the page has to answer is not "am I subscribed" but "do I
        have enough continuous history to backtest this", so every row carries
        its coverage. Coverage is two index probes per row, not a scan.

        Each row also carries the **vendor symbol**, resolved the same way the
        fetcher resolves it. An internal CUSIP alone cannot be checked against
        anything: `btcusdt.crypto` on Bybit is `BTCUSDT`, and the ticker a venue
        actually prints is the one worth reading beside a venue name.
        """
        rows = self._repo.sp_get_bar_subscription()
        return [
            row | {
                "coverage": self._coverage(row),
                "vendor_symbol": self.vendor_symbol(
                    internal_cusip=row["internal_cusip"],
                    source_app_id=int(row["source_app_id"]),
                ),
            }
            for row in rows
        ]

    def vendor_symbol(self, *, internal_cusip: str, source_app_id: int) -> str | None:
        """What the venue calls this product, or ``None`` if it no longer maps.

        A cache lookup, not a query — the same `InstrumentCache` the fetcher
        uses, so the page cannot disagree with what gets requested. ``None``
        rather than an error: an xref withdrawn after subscribing breaks capture
        but must not blank the list that shows you why.
        """
        return self._instruments.resolve_internal_cusip(internal_cusip, source_app_id)

    def coverage(
        self, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> dict:
        """First bar, last bar and gap count for one series."""
        return self._coverage(
            {
                "internal_cusip": internal_cusip,
                "tm_interval_id": tm_interval_id,
                "source_app_id": source_app_id,
            }
        )

    def venue_depth(
        self, *, internal_cusip: str, tm_interval_id: int, source_app_id: int
    ) -> dict:
        """What the exchange will serve, and whether one fill could take it.

        The page asks this before offering a date, so the target it defaults to
        is the venue's own floor rather than a guess. ``bars_available`` is what
        makes the interval's cost visible: the same six years is ~2,200 daily
        bars and ~3.4 million 1-minute ones, and only one of those is a fill.
        """
        earliest, bars_available = self._bar_service(source_app_id).venue_depth(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
        return {
            "earliest": earliest,
            "bars_available": bars_available,
            "max_backfill_bars": MAX_BACKFILL_BARS,
        }

    def backfill(
        self,
        *,
        internal_cusip: str,
        tm_interval_id: int,
        source_app_id: int,
        start: datetime,
        end: datetime | None = None,
    ) -> BackfillResult:
        """Fill an explicit range, reporting whatever the venue would not serve.

        Depth is bounded by the exchange, not by us: how far ``fetch_ohlcv``
        reaches varies by venue and timeframe, and deep intraday history is
        often unavailable at any price. Subscribing today does not retroactively
        create history — it starts a series and lets you fill backward as far as
        the venue will go.
        """
        service = self._bar_service(source_app_id)
        return service.backfill(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=start,
            end=end,
        )

    def _coverage(self, row: dict) -> dict:
        """Stored bounds and hole count, or empty bounds when nothing is stored."""
        internal_cusip = row["internal_cusip"]
        tm_interval_id = int(row["tm_interval_id"])
        source_app_id = int(row["source_app_id"])
        try:
            service = self._bar_service(source_app_id)
            bounds = service.stored_bounds(
                internal_cusip=internal_cusip,
                tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
            )
        except Exception as exc:
            # A page listing ten series must still render when one venue has
            # gone away; the row says why instead of the request failing.
            logger.warning(
                "coverage unavailable for %s interval=%s app=%s: %s",
                internal_cusip, tm_interval_id, source_app_id, exc,
            )
            return {"first_bar": None, "last_bar": None, "gaps": None, "error": str(exc)}

        if bounds is None:
            return {"first_bar": None, "last_bar": None, "gaps": None, "error": None}

        first_bar, last_bar = bounds
        gaps = service.find_gaps(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
            start=first_bar,
            end=last_bar,
        )
        return {
            "first_bar": first_bar,
            "last_bar": last_bar,
            "gaps": len(gaps),
            "error": None,
        }

    def _bar_service(self, source_app_id: int):
        try:
            return self._bar_services.for_app(source_app_id)
        except Exception as exc:
            raise SubscriptionError(
                f"app {source_app_id} is not an exchange this platform can read "
                f"bars from"
            ) from exc

    def _reject_unwarmable(self, *, internal_cusip: str, source_app_id: int) -> None:
        self._bar_service(source_app_id)
        vendor_symbol = self._instruments.resolve_internal_cusip(
            internal_cusip, source_app_id
        )
        if vendor_symbol is None:
            raise SubscriptionError(
                f"no INST.PRODUCT_XREF row maps {internal_cusip!r} to a symbol on "
                f"app {source_app_id} — the venue would be asked for a symbol it "
                f"does not know"
            )
