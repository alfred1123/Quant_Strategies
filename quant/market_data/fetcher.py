"""Fetch OHLCV bars from an exchange.

Bars are public data, so this deliberately does not go through
``CcxtTradeGateway``: market data must not depend on a user's API credentials
or on an authenticated trading session being up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import ccxt

from quant.shared.intervals import ccxt_timeframe

logger = logging.getLogger(__name__)

# ccxt caps a single OHLCV response; ask for a full page and paginate.
_PAGE_LIMIT = 1000

#: Market types left out of :meth:`CcxtBarFetcher.venue_symbols`.
#:
#: Bybit lists 2,212 options against 1,425 of everything else, so including
#: them makes the venue's own tickers the minority of any list built from it.
#: They are also not what an instrument row names: a strike-and-expiry contract
#: expires, and the platform's identity for one would be stale within weeks.
_UNLISTABLE_MARKET_TYPES = frozenset({"option"})


class BarFetchError(RuntimeError):
    """The exchange could not be reached, or returned unusable bars."""


@dataclass(frozen=True)
class OhlcvBar:
    """One closed bar, timestamped by its open time in UTC."""

    bar_timestamp: datetime
    open_px: float
    high_px: float
    low_px: float
    close_px: float
    volume: float


@dataclass(frozen=True)
class VenueMarket:
    """One ticker a venue prints, spelled the way an xref has to store it.

    Keyed on the raw exchange id rather than ccxt's unified symbol because
    ``INST.PRODUCT_XREF.VENDOR_SYMBOL`` holds the raw form — ``BTCUSDT``, not
    ``BTC/USDT:USDT`` — and that is the only string capture and execution can
    send to the venue.
    """

    vendor_symbol: str
    base: str | None
    quote: str | None
    #: Every market the venue serves under this one id. Usually one, but Bybit
    #: prints ``BTCUSDT`` for both the spot pair and the perpetual, and the
    #: xref cannot tell them apart — so the ambiguity is reported rather than
    #: resolved by picking one.
    market_types: tuple[str, ...]


class BarFetcher(Protocol):
    """The slice of an exchange client that :class:`PriceBarService` needs."""

    def fetch_bars(
        self,
        *,
        vendor_symbol: str,
        period: timedelta,
        since: datetime,
        until: datetime,
    ) -> list[OhlcvBar]: ...

    def earliest_bar(
        self, *, vendor_symbol: str, period: timedelta
    ) -> datetime | None: ...

    def venue_symbols(self) -> list[VenueMarket]: ...


class CcxtBarFetcher:
    """Public OHLCV reads over ccxt, paginated across the requested window."""

    def __init__(self, exchange_id: str, *, exchange=None) -> None:
        self._exchange_id = exchange_id
        self._exchange = exchange

    @property
    def exchange(self):
        if self._exchange is None:
            exchange_cls = getattr(ccxt, self._exchange_id, None)
            if exchange_cls is None:
                raise BarFetchError(f"ccxt has no exchange class {self._exchange_id!r}")
            self._exchange = exchange_cls({"enableRateLimit": True})
        return self._exchange

    def venue_symbols(self) -> list[VenueMarket]:
        """Every ticker this venue currently prints, so a form can offer them.

        Answering from the venue matters because a vendor symbol is the one
        field on an instrument nothing else can check. The cusip has a shape to
        validate and the venue comes from a dropdown, but the symbol is free
        text that only the exchange can confirm, and a typo in it produces a
        product that looks created and captures no bar — the xref exists, so
        every venue-scoped list shows it, and the failure surfaces later as a
        ``BadSymbol`` from a warmer nobody is watching.

        Delisted markets are dropped. They are still in ``load_markets`` and
        still tradable in history, but offering one for a *new* instrument
        could only produce a series that ends before it starts.

        Costs one ``load_markets`` per venue per process — ccxt caches the
        symbol table on the client, which is the same table
        :meth:`_listing_ms` already needs, so a venue asked for depth has
        paid for this and vice versa.
        """
        try:
            markets = self.exchange.load_markets()
        except ccxt.BaseError as exc:
            raise BarFetchError(
                f"could not list markets on {self._exchange_id}: {exc}"
            ) from exc

        by_id: dict[str, list[dict]] = {}
        for market in markets.values():
            if not market.get("active"):
                continue
            if market.get("type") in _UNLISTABLE_MARKET_TYPES:
                continue
            raw = market.get("id")
            if raw:
                by_id.setdefault(raw, []).append(market)

        listed = [
            VenueMarket(
                vendor_symbol=raw,
                base=group[0].get("base"),
                quote=group[0].get("quote"),
                market_types=tuple(
                    sorted({m["type"] for m in group if m.get("type")})
                ),
            )
            for raw, group in sorted(by_id.items())
        ]
        logger.info(
            "%s lists %d symbol(s) across %d market(s)",
            self._exchange_id, len(listed), len(markets),
        )
        return listed

    def fetch_bars(
        self,
        *,
        vendor_symbol: str,
        period: timedelta,
        since: datetime,
        until: datetime,
    ) -> list[OhlcvBar]:
        """Bars with an open time in ``[since, until]``, oldest first.

        ``until`` is expected to be the last closed boundary; anything the
        exchange returns beyond it is dropped rather than stored, since the
        bar covering "now" is still forming.
        """
        if since > until:
            return []

        timeframe = ccxt_timeframe(period)
        step_ms = int(period.total_seconds() * 1000)
        until_ms = int(until.timestamp() * 1000)
        cursor_ms = int(since.timestamp() * 1000)

        bars: list[OhlcvBar] = []
        while cursor_ms <= until_ms:
            batch = self._fetch_page(vendor_symbol, timeframe, cursor_ms)
            if not batch:
                break

            for row in batch:
                ts_ms = int(row[0])
                if ts_ms < cursor_ms or ts_ms > until_ms:
                    continue
                bars.append(
                    OhlcvBar(
                        bar_timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                        open_px=float(row[1]),
                        high_px=float(row[2]),
                        low_px=float(row[3]),
                        close_px=float(row[4]),
                        volume=float(row[5]),
                    )
                )

            newest_ms = int(batch[-1][0])
            if newest_ms < cursor_ms:
                # The exchange ignored `since` and replayed older bars; advancing
                # anyway would spin forever on the same page.
                logger.warning(
                    "%s returned bars before the requested cursor for %s — stopping",
                    self._exchange_id,
                    vendor_symbol,
                )
                break
            cursor_ms = newest_ms + step_ms

        logger.info(
            "Fetched %d %s bar(s) for %s in [%s, %s]",
            len(bars), timeframe, vendor_symbol, since, until,
        )
        return bars

    def earliest_bar(
        self, *, vendor_symbol: str, period: timedelta
    ) -> datetime | None:
        """Open time of the oldest bar this venue still serves, or ``None``.

        Asking beats guessing. A capture target is otherwise a date somebody
        typed, and one before the pair listed can never be satisfied — the page
        then reports a permanent shortfall against history that was never
        obtainable rather than against anything a backfill could fix.

        Reading it takes a deliberate two steps, because the obvious one step
        silently lies. ``since=0`` does **not** mean "from the beginning": it is
        falsy, so no start reaches the venue, and Bybit answers with the *newest*
        page — asked that way for daily BTCUSDT it reports today, which would
        make every series look as though it began this morning. So anchor on the
        listing time ccxt normalises into ``market['created']`` and let the venue
        clamp forward from there.

        The listing time is the anchor, never the answer: Bybit lists BTCUSDT at
        2020-03-15 and prints its first daily bar on 2020-03-25. Retention also
        differs per timeframe, and is far shallower below daily, so the bar has
        to be read per ``(symbol, period)``.

        ``None`` when the venue publishes no listing time. Guessing an anchor
        old enough to clamp — a fixed date predating every exchange — would work
        until it did not, and a wrong floor is worse than an absent one: it puts
        a date in front of the user carrying none of the authority the rest of
        this answer has. Callers treat ``None`` as "unknown", not "no bars".
        """
        listing_ms = self._listing_ms(vendor_symbol)
        if listing_ms is None:
            logger.warning(
                "%s publishes no listing time for %s — cannot read its earliest bar",
                self._exchange_id, vendor_symbol,
            )
            return None

        timeframe = ccxt_timeframe(period)
        batch = self._fetch_page(vendor_symbol, timeframe, listing_ms, limit=1)
        if not batch:
            logger.warning(
                "%s served no %s bars at all for %s",
                self._exchange_id, timeframe, vendor_symbol,
            )
            return None
        return datetime.fromtimestamp(int(batch[0][0]) / 1000, tz=UTC)

    def _listing_ms(self, vendor_symbol: str) -> int | None:
        """When the venue says this pair listed, in epoch ms.

        ``load_markets`` first because ``market()`` raises until the symbol
        table is populated — ccxt caches it on the client, so the cost is once
        per venue per process, not once per lookup.
        """
        try:
            self.exchange.load_markets()
            created = self.exchange.market(vendor_symbol).get("created")
        except Exception as exc:
            logger.debug("no listing time for %s: %s", vendor_symbol, exc)
            return None
        return int(created) if created else None

    def _fetch_page(
        self, vendor_symbol: str, timeframe: str, since_ms: int, *, limit: int = _PAGE_LIMIT
    ) -> list:
        try:
            return self.exchange.fetch_ohlcv(
                vendor_symbol, timeframe, since=since_ms, limit=limit
            )
        except ccxt.BadSymbol as exc:
            raise BarFetchError(f"unknown symbol {vendor_symbol!r}: {exc}") from exc
        except ccxt.BaseError as exc:
            raise BarFetchError(f"fetch_ohlcv failed for {vendor_symbol!r}: {exc}") from exc
