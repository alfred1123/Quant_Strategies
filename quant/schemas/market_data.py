"""Pydantic schemas for bar capture — subscriptions, coverage and backfill."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Coverage(BaseModel):
    """What has actually been captured for one series.

    The page's real question is "can I backtest this yet?", which subscription
    state cannot answer — only stored bars can. ``gaps`` counts boundaries with
    no row *between* the bounds, so it says nothing about history older than
    ``first_bar``; that is what backfill is for.
    """

    first_bar: datetime | None = None
    last_bar: datetime | None = None
    gaps: int | None = None
    #: Set when the venue could not be reached to answer. One dead exchange
    #: must not fail the whole list, so the row reports it and the rest render.
    error: str | None = None


class BarSubscriptionRow(BaseModel):
    """One current ``MARKET_DATA.BAR_SUBSCRIPTION`` row with its coverage."""

    bar_subscription_id: UUID
    bar_subscription_vid: int
    internal_cusip: str
    #: The ticker the venue itself prints, e.g. ``BTCUSDT`` for
    #: ``btcusdt.crypto`` on Bybit. ``None`` when the ``INST.PRODUCT_XREF`` row
    #: has been withdrawn since subscribing — which breaks capture, and is worth
    #: showing rather than hiding behind an internal identifier.
    vendor_symbol: str | None = None
    tm_interval_id: int
    source_app_id: int
    is_enabled_ind: Literal["Y", "N"]
    backfill_from_ts: datetime | None = None
    transact_from_ts: datetime
    coverage: Coverage


class SubscribeRequest(BaseModel):
    """Create a subscription, or version an existing one.

    Sending ``bar_subscription_id`` edits that subscription — enable, disable
    or retarget — rather than creating a second one; omitting it creates.
    """

    internal_cusip: str
    tm_interval_id: int
    #: Which venue's prints to capture. Part of the identity of the series, not
    #: a preference: the same instrument on two exchanges is two series.
    source_app_id: int
    is_enabled_ind: Literal["Y", "N"] = "Y"
    #: How far back history is wanted. Intent only — nothing crawls toward it;
    #: it gives the page a target to show and to offer filling toward.
    backfill_from_ts: datetime | None = None
    bar_subscription_id: UUID | None = None


class VenueDepth(BaseModel):
    """How far back a venue will actually serve one series.

    The floor on any capture target. Without it a "history wanted from" is a
    date somebody typed, and one earlier than the pair's listing can never be
    met — leaving the page reporting a shortfall against history that was never
    obtainable rather than against anything a backfill could fix.
    """

    #: ``None`` when the venue would not say — either it served no bars for this
    #: symbol and interval, or it publishes no listing time to anchor the read
    #: on. Deliberately not distinguished: both mean the caller has to supply a
    #: date, and neither justifies putting a guessed one in front of them.
    earliest: datetime | None = None
    #: How many bars separate ``earliest`` from now at this interval, so a
    #: caller can see a fill is impossible before starting one.
    bars_available: int | None = None
    #: Largest number of bars one blocking fill may span.
    max_backfill_bars: int


class BackfillRequest(BaseModel):
    """Fill one series over an explicit range. ``end`` defaults to the last close."""

    internal_cusip: str
    tm_interval_id: int
    source_app_id: int
    start: datetime
    end: datetime | None = None


class BackfillReport(BaseModel):
    """What a fill managed, and what the venue would not serve.

    Reports rather than raises on a hole, inverting the live path's fail-closed
    rule: during a repair a hole is ordinary — the range may predate the listing
    or reach past what the exchange retains — and aborting would discard the
    bars that were recoverable. ``is_continuous`` is the check to make before
    trusting the range in a backtest.
    """

    start: datetime
    end: datetime
    expected: int
    missing: int
    inserted: int
    unfilled: list[datetime] = Field(default_factory=list)
    is_continuous: bool
