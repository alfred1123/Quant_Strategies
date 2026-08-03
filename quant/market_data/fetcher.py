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

    def _fetch_page(self, vendor_symbol: str, timeframe: str, since_ms: int) -> list:
        try:
            return self.exchange.fetch_ohlcv(
                vendor_symbol, timeframe, since=since_ms, limit=_PAGE_LIMIT
            )
        except ccxt.BadSymbol as exc:
            raise BarFetchError(f"unknown symbol {vendor_symbol!r}: {exc}") from exc
        except ccxt.BaseError as exc:
            raise BarFetchError(f"fetch_ohlcv failed for {vendor_symbol!r}: {exc}") from exc
