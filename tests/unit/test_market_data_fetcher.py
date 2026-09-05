"""Unit tests for :mod:`quant.market_data.fetcher`."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import ccxt
import pytest

from quant.market_data.fetcher import BarFetchError, CcxtBarFetcher

HOUR = timedelta(hours=1)


def _ts(hour: int) -> datetime:
    return datetime(2026, 8, 1, hour, 0, tzinfo=UTC)


def _ms(hour: int) -> int:
    return int(_ts(hour).timestamp() * 1000)


def _row(hour: int, close: float = 105.0) -> list:
    return [_ms(hour), 100.0, 110.0, 95.0, close, 12.5]


@pytest.fixture
def exchange():
    return MagicMock()


@pytest.fixture
def fetcher(exchange):
    return CcxtBarFetcher("bybit", exchange=exchange)


class TestFetchBars:
    def test_maps_rows_onto_bars(self, fetcher, exchange):
        exchange.fetch_ohlcv.return_value = [_row(9)]
        bars = fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(9)
        )
        assert len(bars) == 1
        bar = bars[0]
        assert bar.bar_timestamp == _ts(9)
        assert (bar.open_px, bar.high_px, bar.low_px, bar.close_px) == (100.0, 110.0, 95.0, 105.0)
        assert bar.volume == 12.5

    def test_passes_the_derived_timeframe_and_since(self, fetcher, exchange):
        exchange.fetch_ohlcv.return_value = [_row(9)]
        fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(9)
        )
        args, kwargs = exchange.fetch_ohlcv.call_args
        assert args[0] == "BTCUSDT"
        assert args[1] == "1h"
        assert kwargs["since"] == _ms(9)

    def test_drops_bars_past_the_last_closed_boundary(self, fetcher, exchange):
        """The bar covering `now` is still forming and must never be stored."""
        exchange.fetch_ohlcv.return_value = [_row(9), _row(10), _row(11)]
        bars = fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(10)
        )
        assert [b.bar_timestamp for b in bars] == [_ts(9), _ts(10)]

    def test_paginates_until_the_window_is_covered(self, fetcher, exchange):
        exchange.fetch_ohlcv.side_effect = [
            [_row(9), _row(10)],
            [_row(11), _row(12)],
        ]
        bars = fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(12)
        )
        assert [b.bar_timestamp for b in bars] == [_ts(9), _ts(10), _ts(11), _ts(12)]
        assert exchange.fetch_ohlcv.call_count == 2

    def test_stops_on_an_empty_page(self, fetcher, exchange):
        exchange.fetch_ohlcv.side_effect = [[_row(9)], []]
        bars = fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(12)
        )
        assert [b.bar_timestamp for b in bars] == [_ts(9)]
        assert exchange.fetch_ohlcv.call_count == 2

    def test_stops_when_the_exchange_ignores_since(self, fetcher, exchange):
        """Replaying older bars would otherwise spin on the same page forever."""
        exchange.fetch_ohlcv.side_effect = [[_row(9), _row(10)], [_row(9)]]
        bars = fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(20)
        )
        assert [b.bar_timestamp for b in bars] == [_ts(9), _ts(10)]
        assert exchange.fetch_ohlcv.call_count == 2

    def test_empty_window_short_circuits(self, fetcher, exchange):
        assert fetcher.fetch_bars(
            vendor_symbol="BTCUSDT", period=HOUR, since=_ts(12), until=_ts(9)
        ) == []
        exchange.fetch_ohlcv.assert_not_called()


class TestEarliestBar:
    """The floor on any capture target, read from the venue rather than typed."""

    def test_anchors_on_the_listing_time_and_takes_one_bar(self, fetcher, exchange):
        exchange.market.return_value = {"created": _ms(3)}
        exchange.fetch_ohlcv.return_value = [_row(5)]

        assert fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR) == _ts(5)

        args, kwargs = exchange.fetch_ohlcv.call_args
        assert (args[0], args[1]) == ("BTCUSDT", "1h")
        assert kwargs["since"] == _ms(3)
        assert kwargs["limit"] == 1

    def test_loads_markets_before_reading_the_listing_time(self, fetcher, exchange):
        """``market()`` raises until the symbol table is populated.

        Without this the lookup fails, the anchor is lost, and every series
        silently reports an unknown floor.
        """
        exchange.market.return_value = {"created": _ms(3)}
        exchange.fetch_ohlcv.return_value = [_row(5)]

        fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR)

        exchange.load_markets.assert_called_once()

    def test_never_sends_a_zero_since(self, fetcher, exchange):
        """Zero is falsy, so ccxt drops it and the venue answers with *today*.

        Guarding the regression directly: asked that way, every series would
        report that it began this morning.
        """
        exchange.market.return_value = {"created": _ms(3)}
        exchange.fetch_ohlcv.return_value = [_row(5)]

        fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR)

        assert exchange.fetch_ohlcv.call_args.kwargs["since"] > 0

    def test_listing_time_is_the_anchor_not_the_answer(self, fetcher, exchange):
        """Bybit lists BTCUSDT on 2020-03-15 but prints its first daily bar later."""
        exchange.market.return_value = {"created": _ms(3)}
        exchange.fetch_ohlcv.return_value = [_row(9)]

        assert fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR) == _ts(9)

    @pytest.mark.parametrize(
        "market",
        [{"created": None}, {}],
        ids=["null listing time", "no listing time key"],
    )
    def test_no_listing_time_means_unknown_rather_than_a_guessed_anchor(
        self, fetcher, exchange, market
    ):
        """A wrong floor is worse than an absent one — it looks authoritative."""
        exchange.market.return_value = market

        assert fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR) is None
        exchange.fetch_ohlcv.assert_not_called()

    def test_an_unknown_market_is_unknown_depth_not_an_error(self, fetcher, exchange):
        exchange.market.side_effect = KeyError("no such market")

        assert fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR) is None
        exchange.fetch_ohlcv.assert_not_called()

    def test_no_bars_at_all_is_none_not_an_error(self, fetcher, exchange):
        """A venue that serves nothing is an answer: there is nothing to capture."""
        exchange.market.return_value = {"created": _ms(3)}
        exchange.fetch_ohlcv.return_value = []

        assert fetcher.earliest_bar(vendor_symbol="BTCUSDT", period=HOUR) is None


def _market(
    raw: str, symbol: str, mtype: str, base: str, quote: str, *, active: bool = True
) -> dict:
    return {
        "id": raw,
        "symbol": symbol,
        "type": mtype,
        "base": base,
        "quote": quote,
        "active": active,
    }


class TestVenueSymbols:
    """The set a new instrument's vendor symbol can be chosen from."""

    def test_reports_the_raw_id_the_xref_has_to_store(self, fetcher, exchange):
        # ccxt keys its table by the unified symbol, but BTC/USDT:USDT is not
        # what INST.PRODUCT_XREF holds and not what the venue would accept.
        exchange.load_markets.return_value = {
            "BTC/USDT:USDT": _market("BTCUSDT", "BTC/USDT:USDT", "swap", "BTC", "USDT"),
        }

        listed = fetcher.venue_symbols()

        assert [m.vendor_symbol for m in listed] == ["BTCUSDT"]
        assert (listed[0].base, listed[0].quote) == ("BTC", "USDT")

    def test_one_id_meaning_two_markets_reports_both(self, fetcher, exchange):
        """Bybit prints BTCUSDT for the spot pair and the perpetual alike.

        The xref stores one string for both, so which was meant cannot be
        recorded — collapsing to whichever ccxt listed first would hide a
        genuine ambiguity behind an arbitrary choice.
        """
        exchange.load_markets.return_value = {
            "BTC/USDT": _market("BTCUSDT", "BTC/USDT", "spot", "BTC", "USDT"),
            "BTC/USDT:USDT": _market("BTCUSDT", "BTC/USDT:USDT", "swap", "BTC", "USDT"),
        }

        listed = fetcher.venue_symbols()

        assert len(listed) == 1
        assert listed[0].market_types == ("spot", "swap")

    def test_options_are_left_out(self, fetcher, exchange):
        # Bybit lists 2,212 of them against 1,425 of everything else, and a
        # strike-and-expiry contract is not an instrument the platform names.
        exchange.load_markets.return_value = {
            "BTC/USDT": _market("BTCUSDT", "BTC/USDT", "spot", "BTC", "USDT"),
            "BTC/USDC:USDC-260925-60000-C": _market(
                "BTC-26SEP26-60000-C", "BTC/USDC:USDC-260925-60000-C",
                "option", "BTC", "USDC",
            ),
        }

        assert [m.vendor_symbol for m in fetcher.venue_symbols()] == ["BTCUSDT"]

    def test_delisted_markets_are_left_out(self, fetcher, exchange):
        """Offering one could only create a series that ends before it starts."""
        exchange.load_markets.return_value = {
            "BTC/USDT": _market("BTCUSDT", "BTC/USDT", "spot", "BTC", "USDT"),
            "LUNA/USDT": _market(
                "LUNAUSDT", "LUNA/USDT", "spot", "LUNA", "USDT", active=False
            ),
        }

        assert [m.vendor_symbol for m in fetcher.venue_symbols()] == ["BTCUSDT"]

    def test_sorted_so_the_list_is_predictable(self, fetcher, exchange):
        exchange.load_markets.return_value = {
            "SOL/USDT": _market("SOLUSDT", "SOL/USDT", "spot", "SOL", "USDT"),
            "BTC/USDT": _market("BTCUSDT", "BTC/USDT", "spot", "BTC", "USDT"),
            "ETH/USDT": _market("ETHUSDT", "ETH/USDT", "spot", "ETH", "USDT"),
        }

        assert [m.vendor_symbol for m in fetcher.venue_symbols()] == [
            "BTCUSDT", "ETHUSDT", "SOLUSDT",
        ]

    def test_an_unreachable_venue_is_wrapped(self, fetcher, exchange):
        exchange.load_markets.side_effect = ccxt.NetworkError("timeout")

        with pytest.raises(BarFetchError, match="could not list markets"):
            fetcher.venue_symbols()


class TestErrors:
    def test_bad_symbol_is_wrapped(self, fetcher, exchange):
        exchange.fetch_ohlcv.side_effect = ccxt.BadSymbol("nope")
        with pytest.raises(BarFetchError, match="unknown symbol"):
            fetcher.fetch_bars(
                vendor_symbol="NOPE", period=HOUR, since=_ts(9), until=_ts(9)
            )

    def test_transport_failure_is_wrapped(self, fetcher, exchange):
        exchange.fetch_ohlcv.side_effect = ccxt.NetworkError("timeout")
        with pytest.raises(BarFetchError, match="fetch_ohlcv failed"):
            fetcher.fetch_bars(
                vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(9)
            )

    def test_unknown_exchange_id(self):
        with pytest.raises(BarFetchError, match="no exchange class"):
            CcxtBarFetcher("not_an_exchange").fetch_bars(
                vendor_symbol="BTCUSDT", period=HOUR, since=_ts(9), until=_ts(9)
            )


class TestExchangeConstruction:
    def test_builds_a_keyless_client(self, monkeypatch):
        """Bars are public — market data must not need trading credentials."""
        built = {}

        def fake_exchange(params):
            built.update(params)
            return MagicMock()

        monkeypatch.setattr(ccxt, "bybit", fake_exchange, raising=False)
        CcxtBarFetcher("bybit").exchange
        assert built == {"enableRateLimit": True}
