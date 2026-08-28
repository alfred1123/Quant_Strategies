"""Unit tests for :mod:`quant.trade.scheduler.warm` — mocked repo, no DB, no ccxt."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from quant.market_data.service import SyncResult
from quant.trade.scheduler.warm import DEFAULT_SETTLE_S, DEFAULT_WARM_LOOKBACK, BarWarmer

FIXED_NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)

DAILY = 1
HOURLY = 2
BYBIT = 34
BINANCE = 35


def _row(tm_interval_id=DAILY, internal_cusip="btcusdt.crypto", app_id=BYBIT):
    return {
        "tm_interval_id": tm_interval_id,
        "internal_cusip": internal_cusip,
        "app_id": app_id,
    }


def _sync_result(instruments=1, inserted=1, failures=None):
    return SyncResult(
        instruments=instruments, inserted=inserted, failures=failures or {}
    )


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def factory():
    """PriceBarServiceFactory whose every venue returns a fresh mock service."""
    made: dict[int, MagicMock] = {}

    def for_app(app_id):
        service = made.setdefault(app_id, MagicMock())
        service.sync.return_value = _sync_result()
        return service

    mock = MagicMock()
    mock.for_app.side_effect = for_app
    mock.services = made
    return mock


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Never actually wait in tests; record the requested delay instead."""
    calls: list[float] = []
    monkeypatch.setattr(
        "quant.trade.scheduler.warm.time.sleep", lambda s: calls.append(s)
    )
    return calls


class TestNothingScheduled:
    def test_empty_report_when_no_rows(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = []

        report = BarWarmer(repo, factory).run(now=FIXED_NOW)

        assert report.results == []
        assert (report.instruments, report.inserted, report.failed) == (0, 0, 0)
        factory.for_app.assert_not_called()


class TestGrouping:
    def test_one_sync_per_interval_and_venue(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [
            _row(DAILY, "btcusdt.crypto", BYBIT),
            _row(DAILY, "ethusdt.crypto", BYBIT),
            _row(HOURLY, "btcusdt.crypto", BYBIT),
            _row(DAILY, "btcusdt.crypto", BINANCE),
        ]

        report = BarWarmer(repo, factory).run(now=FIXED_NOW)

        # (DAILY, Bybit), (DAILY, Binance), (HOURLY, Bybit) — same instrument on
        # two venues is two groups, because they are separate order books.
        assert len(report.results) == 3
        assert {(r.tm_interval_id, r.app_id) for r in report.results} == {
            (DAILY, BYBIT),
            (DAILY, BINANCE),
            (HOURLY, BYBIT),
        }

    def test_instruments_of_one_group_go_in_a_single_call(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [
            _row(DAILY, "btcusdt.crypto", BYBIT),
            _row(DAILY, "ethusdt.crypto", BYBIT),
        ]

        BarWarmer(repo, factory).run(now=FIXED_NOW)

        service = factory.services[BYBIT]
        service.sync.assert_called_once()
        kwargs = service.sync.call_args.kwargs
        assert kwargs["tm_interval_id"] == DAILY
        assert sorted(kwargs["instruments"]) == [
            ("btcusdt.crypto", BYBIT),
            ("ethusdt.crypto", BYBIT),
        ]

    def test_passes_lookback_and_now_through(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [_row()]

        BarWarmer(repo, factory, lookback=123).run(now=FIXED_NOW)

        kwargs = factory.services[BYBIT].sync.call_args.kwargs
        assert kwargs["lookback"] == 123
        assert kwargs["now"] == FIXED_NOW

    def test_default_lookback_is_the_live_rule(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [_row()]

        BarWarmer(repo, factory).run(now=FIXED_NOW)

        assert factory.services[BYBIT].sync.call_args.kwargs["lookback"] == (
            DEFAULT_WARM_LOOKBACK
        )


class TestTotals:
    def test_sums_across_groups(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [
            _row(DAILY, "btcusdt.crypto", BYBIT),
            _row(HOURLY, "btcusdt.crypto", BYBIT),
        ]

        def sync(**kwargs):
            return _sync_result(instruments=2, inserted=5, failures={"x": "boom"})

        service = factory.for_app(BYBIT)
        service.sync.side_effect = sync

        report = BarWarmer(repo, factory).run(now=FIXED_NOW)

        assert report.instruments == 4
        assert report.inserted == 10
        assert report.failed == 2


class TestFailuresAreAbsorbed:
    def test_unmapped_venue_is_reported_not_raised(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [
            _row(DAILY, "btcusdt.crypto", BINANCE),
        ]
        factory.for_app.side_effect = RuntimeError("no market data venue")

        report = BarWarmer(repo, factory).run(now=FIXED_NOW)

        assert report.inserted == 0
        assert report.failed == 1
        assert "no market data venue" in report.results[0].failures["btcusdt.crypto"]

    def test_one_bad_venue_does_not_stop_the_others(self, repo, factory):
        repo.sp_get_scheduled_instruments.return_value = [
            _row(DAILY, "btcusdt.crypto", BYBIT),
            _row(DAILY, "ethusdt.crypto", BINANCE),
        ]
        good = MagicMock()
        good.sync.return_value = _sync_result(inserted=7)

        def for_app(app_id):
            if app_id == BINANCE:
                raise RuntimeError("no market data venue")
            return good

        factory.for_app.side_effect = for_app

        report = BarWarmer(repo, factory).run(now=FIXED_NOW)

        assert report.inserted == 7
        assert report.failed == 1


class TestBoundarySettle:
    """The schedule fires on the boundary, so the clock is read after a pause."""

    def test_default_settle_matches_scheduler_config(self):
        assert DEFAULT_SETTLE_S == 10.0

    def test_sleeps_then_reads_the_clock_when_now_is_not_given(
        self, repo, factory, no_sleep
    ):
        repo.sp_get_scheduled_instruments.return_value = [_row()]
        before = datetime.now(UTC)

        BarWarmer(repo, factory, settle_s=2.0).run()

        assert no_sleep == [2.0]
        used = factory.services[BYBIT].sync.call_args.kwargs["now"]
        assert used is not None and used >= before

    def test_injected_now_does_not_wait(self, repo, factory, no_sleep):
        repo.sp_get_scheduled_instruments.return_value = [_row()]

        BarWarmer(repo, factory).run(now=FIXED_NOW)

        assert no_sleep == []
