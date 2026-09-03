"""Unit tests for :mod:`quant.market_data.service`."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from quant.market_data.fetcher import OhlcvBar
from quant.market_data.service import (
    MAX_BACKFILL_BARS,
    BackfillTooLargeError,
    PriceBarService,
    StaleBarsError,
)
from quant.shared.db import ProcedureError

CUSIP = "btcusdt.crypto"
INTERVAL_1H = 2
APP_ID = 10
# 10:37 → 10:00 is still forming, so 09:00 is the newest closed bar.
NOW = datetime(2026, 8, 1, 10, 37, tzinfo=UTC)


def _ts(hour: int) -> datetime:
    return datetime(2026, 8, 1, hour, 0, tzinfo=UTC)


def _bar(hour: int, close: float = 105.0) -> OhlcvBar:
    return OhlcvBar(
        bar_timestamp=_ts(hour),
        open_px=100.0,
        high_px=110.0,
        low_px=95.0,
        close_px=close,
        volume=12.5,
    )


class FakeRefData:
    """Stands in for RedisRefData — only the interval resolver is used here."""

    def get_interval_period(self, tm_interval_id):
        return {1: timedelta(days=1), 2: timedelta(hours=1)}[tm_interval_id]


class FakeFetcher:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def fetch_bars(self, *, vendor_symbol, period, since, until):
        self.calls.append(
            {"vendor_symbol": vendor_symbol, "period": period, "since": since, "until": until}
        )
        return [b for b in self.bars if since <= b.bar_timestamp <= until]

    def earliest_bar(self, *, vendor_symbol, period):
        self.earliest_calls = getattr(self, "earliest_calls", [])
        self.earliest_calls.append({"vendor_symbol": vendor_symbol, "period": period})
        return self.bars[0].bar_timestamp if self.bars else None


def build_service(*, stored_bars=(), coverage_max=None, coverage_min=None, exchange_bars=()):
    repo = MagicMock()
    repo.get_coverage.return_value = (
        {"min_bar_timestamp": coverage_min or _ts(0), "max_bar_timestamp": coverage_max}
        if coverage_max
        else None
    )
    repo.get_bars.return_value = [{"bar_timestamp": ts} for ts in stored_bars]
    instruments = MagicMock()
    instruments.resolve_internal_cusip.return_value = "BTCUSDT"
    fetcher = FakeFetcher(list(exchange_bars))
    service = PriceBarService(repo, FakeRefData(), instruments, fetcher)
    return service, repo, fetcher


def _ensure(service, lookback=3):
    return service.ensure_fresh(
        internal_cusip=CUSIP,
        tm_interval_id=INTERVAL_1H,
        source_app_id=APP_ID,
        lookback=lookback,
        now=NOW,
    )


def _inserted_timestamps(repo):
    return [c.kwargs["bar_timestamp"] for c in repo.ins_bar.call_args_list]


def _backfill(service, start, end=None, **kwargs):
    return service.backfill(
        internal_cusip=CUSIP,
        tm_interval_id=INTERVAL_1H,
        source_app_id=APP_ID,
        start=start,
        end=end,
        **kwargs,
    )


class TestFindGaps:
    """Continuity as a read — no fetching, no writing."""

    def test_reports_the_boundaries_with_no_stored_row(self):
        service, repo, _fetcher = build_service()
        repo.get_bars.return_value = [{"bar_timestamp": _ts(h)} for h in (5, 6, 9)]

        gaps = service.find_gaps(
            internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID, start=_ts(5), end=_ts(9),
        )

        assert gaps == [_ts(7), _ts(8)]

    def test_a_continuous_range_has_no_gaps(self):
        service, repo, _fetcher = build_service()
        repo.get_bars.return_value = [{"bar_timestamp": _ts(h)} for h in (5, 6, 7)]

        gaps = service.find_gaps(
            internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID, start=_ts(5), end=_ts(7),
        )

        assert gaps == []

    def test_does_not_touch_the_exchange(self):
        service, repo, fetcher = build_service()
        repo.get_bars.return_value = []

        service.find_gaps(
            internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID, start=_ts(5), end=_ts(7),
        )

        assert fetcher.calls == []
        repo.ins_bar.assert_not_called()


class TestBackfill:
    """Continuity repair over an explicit range — the part `ensure_fresh` cannot do.

    A host down longer than the live lookback leaves bars older than the window
    missing for good, because `ensure_fresh` never asks for them again.
    """

    def test_fills_holes_older_than_any_live_lookback(self):
        service, repo, fetcher = build_service(
            exchange_bars=[_bar(h) for h in (5, 6, 7, 8, 9)]
        )
        repo.get_bars.return_value = [{"bar_timestamp": _ts(h)} for h in (5, 9)]

        report = _backfill(service, _ts(5), _ts(9))

        assert _inserted_timestamps(repo) == [_ts(6), _ts(7), _ts(8)]
        assert report.inserted == 3
        assert report.missing == 3
        assert report.expected == 5
        assert report.is_continuous

    def test_a_continuous_range_does_not_hit_the_exchange(self):
        service, repo, fetcher = build_service()
        repo.get_bars.return_value = [{"bar_timestamp": _ts(h)} for h in (5, 6, 7)]

        report = _backfill(service, _ts(5), _ts(7))

        assert fetcher.calls == []
        assert report.inserted == 0
        assert report.is_continuous

    def test_fetches_from_the_oldest_hole_not_the_range_start(self):
        service, repo, fetcher = build_service(exchange_bars=[_bar(9)])
        repo.get_bars.return_value = [{"bar_timestamp": _ts(h)} for h in (5, 6, 7, 8)]

        _backfill(service, _ts(5), _ts(9))

        assert fetcher.calls[0]["since"] == _ts(9)

    def test_reports_what_the_exchange_could_not_supply(self):
        """A range reaching past the listing, or past what the venue retains."""
        service, repo, _fetcher = build_service(exchange_bars=[_bar(8), _bar(9)])
        repo.get_bars.return_value = []

        report = _backfill(service, _ts(6), _ts(9))

        assert report.inserted == 2
        assert report.unfilled == (_ts(6), _ts(7))
        assert report.oldest_unfilled == _ts(6)
        assert not report.is_continuous

    def test_keeps_what_it_could_recover_rather_than_failing_closed(self):
        """Unlike the trade path: aborting would discard recoverable bars."""
        service, repo, _fetcher = build_service(exchange_bars=[_bar(9)])
        repo.get_bars.return_value = []

        report = _backfill(service, _ts(6), _ts(9))

        assert _inserted_timestamps(repo) == [_ts(9)]
        assert report.inserted == 1

    def test_end_defaults_to_the_newest_closed_bar(self):
        service, repo, _fetcher = build_service(exchange_bars=[_bar(9)])
        repo.get_bars.return_value = []

        report = _backfill(service, _ts(9), now=NOW)

        assert report.end == _ts(9)  # 10:00 is still forming

    def test_inverted_range_is_rejected(self):
        service, _repo, _fetcher = build_service()
        with pytest.raises(ValueError, match="after end"):
            _backfill(service, _ts(9), _ts(5))

    def test_writes_oldest_first_so_a_crash_resumes_cleanly(self):
        service, repo, _fetcher = build_service(
            exchange_bars=[_bar(h) for h in (5, 6, 7)]
        )
        repo.get_bars.return_value = []

        _backfill(service, _ts(5), _ts(7))

        assert _inserted_timestamps(repo) == [_ts(5), _ts(6), _ts(7)]

    def test_scoped_to_one_source(self):
        service, repo, _fetcher = build_service(exchange_bars=[_bar(9)])
        repo.get_bars.return_value = []

        service.backfill(
            internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H,
            source_app_id=35, start=_ts(9), end=_ts(9),
        )

        assert repo.get_bars.call_args.kwargs["source_app_id"] == 35
        assert repo.ins_bar.call_args.kwargs["source_app_id"] == 35


class TestVenueDepth:
    """What the exchange holds, as distinct from what we have stored."""

    def test_reports_the_venue_floor_and_how_many_bars_that_is(self):
        service, _repo, fetcher = build_service(exchange_bars=[_bar(7), _bar(8)])

        earliest, bars = service.venue_depth(
            internal_cusip=CUSIP,
            tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID,
            now=NOW,
        )

        assert earliest == _ts(7)
        # 07:00 through 10:00 inclusive, at one bar an hour.
        assert bars == 4
        assert fetcher.earliest_calls == [
            {"vendor_symbol": "BTCUSDT", "period": timedelta(hours=1)}
        ]

    def test_counts_in_bars_so_the_intervals_cost_is_visible(self):
        """The same span is a few daily bars or a great many hourly ones."""
        service, _repo, _fetcher = build_service(exchange_bars=[_bar(0)])

        _, hourly = service.venue_depth(
            internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID, now=NOW,
        )
        _, daily = service.venue_depth(
            internal_cusip=CUSIP, tm_interval_id=1, source_app_id=APP_ID, now=NOW,
        )

        assert hourly == 11
        assert daily == 1

    def test_a_venue_serving_nothing_reports_no_depth(self):
        service, _repo, _fetcher = build_service(exchange_bars=[])

        assert service.venue_depth(
            internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID, now=NOW,
        ) == (None, None)

    def test_an_unmapped_symbol_refuses_rather_than_asking_the_venue(self):
        service, _repo, _fetcher = build_service(exchange_bars=[_bar(7)])
        service._instruments.resolve_internal_cusip.return_value = None

        with pytest.raises(StaleBarsError, match="no INST.PRODUCT_XREF mapping"):
            service.venue_depth(
                internal_cusip=CUSIP, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID,
            )


def _plan(service, target, **kwargs):
    return service.plan_backfill(
        internal_cusip=CUSIP,
        tm_interval_id=INTERVAL_1H,
        source_app_id=APP_ID,
        target=target,
        now=NOW,
        **kwargs,
    )


#: 10:37 is still forming, so 09:00 is the newest closed hourly bar.
LAST_CLOSED = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


class TestBackfillPlan:
    """Deep history is reached in stages, each pass ending where coverage begins.

    The ceiling alone made intraday history unreachable rather than slow: every
    fill ran to the last closed bar, so for a series already holding a year no
    start both reached further back and stayed under the limit.
    """

    def test_an_empty_series_anchors_on_the_newest_closed_bar(self):
        """Not on the target — the first pass should yield tradeable bars."""
        service, _repo, _fetcher = build_service()

        plan = _plan(service, LAST_CLOSED - timedelta(hours=25_000))

        assert plan.end == LAST_CLOSED
        assert plan.start == LAST_CLOSED - timedelta(hours=MAX_BACKFILL_BARS - 1)
        assert plan.bars == MAX_BACKFILL_BARS

    def test_a_pass_stops_where_coverage_begins(self):
        """The span counts only absent bars, never ones already stored."""
        first_stored = _ts(0)
        service, _repo, _fetcher = build_service(
            coverage_max=LAST_CLOSED, coverage_min=first_stored,
        )

        plan = _plan(service, first_stored - timedelta(hours=500))

        assert plan.end == first_stored - timedelta(hours=1)
        assert plan.bars == 500

    def test_a_reachable_target_is_one_pass(self):
        first_stored = _ts(0)
        service, _repo, _fetcher = build_service(
            coverage_max=LAST_CLOSED, coverage_min=first_stored,
        )
        target = first_stored - timedelta(hours=500)

        plan = _plan(service, target)

        assert plan.start == target
        assert plan.passes_remaining == 1

    def test_it_says_how_many_passes_remain(self):
        service, _repo, _fetcher = build_service()

        plan = _plan(service, LAST_CLOSED - timedelta(hours=25_000))

        # 25,001 outstanding boundaries over a 10,000 ceiling.
        assert plan.passes_remaining == 3

    def test_a_target_already_reached_has_nothing_to_run(self):
        first_stored = _ts(0)
        service, _repo, _fetcher = build_service(
            coverage_max=LAST_CLOSED, coverage_min=first_stored,
        )

        plan = _plan(service, first_stored)

        assert plan.is_complete
        assert plan.start is None
        assert plan.passes_remaining == 0

    def test_a_target_in_the_future_has_nothing_to_run(self):
        service, _repo, _fetcher = build_service()

        plan = _plan(service, LAST_CLOSED + timedelta(days=7))

        assert plan.is_complete

    def test_planning_costs_no_exchange_call(self):
        """A dialog re-asks after every fill, so this must stay cheap."""
        service, _repo, fetcher = build_service()

        _plan(service, LAST_CLOSED - timedelta(hours=25_000))

        assert fetcher.calls == []
        assert not hasattr(fetcher, "earliest_calls")

    def test_a_planned_pass_is_never_refused_by_the_guard(self):
        """The plan exists to produce fills the guard accepts."""
        service, _repo, _fetcher = build_service()

        plan = _plan(service, LAST_CLOSED - timedelta(hours=25_000))

        assert plan.bars <= MAX_BACKFILL_BARS

    def test_successive_passes_walk_backwards(self):
        """The second pass resumes exactly where the first stopped."""
        service, repo, _fetcher = build_service(
            coverage_max=LAST_CLOSED, coverage_min=_ts(0),
        )
        target = _ts(0) - timedelta(hours=25_000)

        first = _plan(service, target)
        # What the store looks like once that pass has been applied.
        repo.get_coverage.return_value = {
            "min_bar_timestamp": first.start,
            "max_bar_timestamp": LAST_CLOSED,
        }
        second = _plan(service, target)

        assert second.end == first.start - timedelta(hours=1)
        assert second.passes_remaining == first.passes_remaining - 1

    def test_a_date_only_target_is_treated_as_utc(self):
        """API query params such as ``target=2020-03-25`` arrive without a zone."""
        first_stored = datetime(2025, 10, 1, 0, 0, tzinfo=UTC)
        service, _repo, _fetcher = build_service(
            coverage_max=LAST_CLOSED, coverage_min=first_stored,
        )

        plan = _plan(service, datetime(2020, 3, 25))

        assert plan.start is not None
        assert plan.end == first_stored - timedelta(hours=1)


class TestBackfillSizeGuard:
    """A fill too large to finish is refused before it starts."""

    def test_a_range_over_the_ceiling_is_refused(self):
        service, _repo, fetcher = build_service()
        start = NOW - timedelta(hours=MAX_BACKFILL_BARS + 100)

        with pytest.raises(BackfillTooLargeError, match="over the"):
            _backfill(service, start, NOW)

        assert fetcher.calls == []

    def test_refusal_names_a_range_that_would_fit(self):
        service, _repo, _fetcher = build_service()
        start = NOW - timedelta(hours=MAX_BACKFILL_BARS + 100)

        with pytest.raises(BackfillTooLargeError) as exc:
            _backfill(service, start, NOW)

        affordable = start + timedelta(hours=MAX_BACKFILL_BARS - 1)
        assert str(affordable.date()) in str(exc.value)

    def test_nothing_is_written_by_a_refused_fill(self):
        """The point of refusing early: a fill killed mid-write leaves a mess."""
        service, repo, _fetcher = build_service()

        with pytest.raises(BackfillTooLargeError):
            _backfill(service, NOW - timedelta(hours=MAX_BACKFILL_BARS + 1), NOW)

        repo.ins_bar.assert_not_called()

    def test_a_range_at_the_ceiling_is_allowed(self):
        """The boundary itself passes — the guard refuses beyond it, not at it."""
        service, _repo, _fetcher = build_service()
        start = NOW - timedelta(hours=MAX_BACKFILL_BARS - 1)

        result = _backfill(service, start, NOW)

        assert result.expected <= MAX_BACKFILL_BARS

    def test_the_ceiling_is_counted_in_bars_not_days(self):
        """A daily fill of the same calendar span stays well inside it."""
        service, _repo, _fetcher = build_service()
        span = timedelta(hours=MAX_BACKFILL_BARS + 100)

        with pytest.raises(BackfillTooLargeError):
            _backfill(service, NOW - span, NOW)

        daily = service.backfill(
            internal_cusip=CUSIP, tm_interval_id=1, source_app_id=APP_ID,
            start=NOW - span, end=NOW,
        )
        assert daily.expected < MAX_BACKFILL_BARS


class TestSourceScoping:
    """Every read is scoped to the venue being priced — see decision #47.

    ``btcusdt.crypto`` is one product across Bybit and Binance, so an unscoped
    read would hand a strategy a window blended from two order books, and an
    unscoped freshness probe would let one venue's bars mark another as fresh.
    """

    def test_freshness_probe_is_scoped(self):
        service, repo, _fetcher = build_service(coverage_max=_ts(9))
        _ensure(service)
        assert repo.get_coverage.call_args.kwargs["source_app_id"] == APP_ID

    def test_gap_check_is_scoped(self):
        service, repo, _fetcher = build_service(
            coverage_max=_ts(8), exchange_bars=[_bar(9)]
        )
        _ensure(service)
        assert repo.get_bars.call_args.kwargs["source_app_id"] == APP_ID

    def test_window_read_is_scoped(self):
        service, repo, _fetcher = build_service(coverage_max=_ts(9))
        repo.get_bars.return_value = [
            {
                "bar_timestamp": _ts(h),
                "open_px": Decimal("1"), "high_px": Decimal("1"),
                "low_px": Decimal("1"), "close_px": Decimal("1"),
                "volume": Decimal("1"),
            }
            for h in (7, 8, 9)
        ]

        service.load_window(
            CUSIP, 3, tm_interval_id=INTERVAL_1H, source_app_id=35, now=NOW
        )

        assert repo.get_bars.call_args.kwargs["source_app_id"] == 35

    def test_a_second_venue_fetches_its_own_bars(self):
        """The other venue having stored this bar must not read as fresh."""
        service, repo, fetcher = build_service(exchange_bars=[_bar(h) for h in (7, 8, 9)])
        repo.get_coverage.return_value = None  # nothing under *this* source

        assert _ensure(service) == 3
        assert fetcher.calls, "expected the second venue to fetch its own prints"


class TestFreshnessGate:
    def test_newest_closed_bar_present_skips_the_exchange(self):
        service, repo, fetcher = build_service(coverage_max=_ts(9))
        assert _ensure(service) == 0
        assert fetcher.calls == []
        repo.get_bars.assert_not_called()
        repo.ins_bar.assert_not_called()

    def test_bars_ahead_of_the_boundary_still_count_as_fresh(self):
        service, _repo, fetcher = build_service(coverage_max=_ts(11))
        assert _ensure(service) == 0
        assert fetcher.calls == []

    def test_stale_tail_triggers_a_fetch(self):
        service, repo, fetcher = build_service(
            coverage_max=_ts(8),
            stored_bars=[_ts(7), _ts(8)],
            exchange_bars=[_bar(9)],
        )
        assert _ensure(service) == 1
        assert _inserted_timestamps(repo) == [_ts(9)]
        assert fetcher.calls[0]["since"] == _ts(9)
        assert fetcher.calls[0]["until"] == _ts(9)


class TestGapFilling:
    def test_empty_table_backfills_the_whole_window(self):
        service, repo, fetcher = build_service(
            exchange_bars=[_bar(7), _bar(8), _bar(9)]
        )
        assert _ensure(service) == 3
        assert _inserted_timestamps(repo) == [_ts(7), _ts(8), _ts(9)]
        assert fetcher.calls[0]["since"] == _ts(7)

    def test_only_missing_bars_are_inserted(self):
        """SP_INS_PRICE_BAR is a plain INSERT — a repeat would raise."""
        service, repo, _fetcher = build_service(
            coverage_max=_ts(8),
            stored_bars=[_ts(7), _ts(8)],
            exchange_bars=[_bar(7), _bar(8), _bar(9)],
        )
        assert _ensure(service) == 1
        assert _inserted_timestamps(repo) == [_ts(9)]

    def test_inserts_run_oldest_first(self):
        """A crash part-way leaves MAX short of the target so the next tick resumes."""
        service, repo, _fetcher = build_service(
            exchange_bars=[_bar(9), _bar(7), _bar(8)]
        )
        _ensure(service)
        assert _inserted_timestamps(repo) == [_ts(7), _ts(8), _ts(9)]

    def test_nothing_missing_after_the_range_read(self):
        service, repo, fetcher = build_service(
            coverage_max=_ts(8), stored_bars=[_ts(7), _ts(8), _ts(9)]
        )
        assert _ensure(service) == 0
        assert fetcher.calls == []
        repo.ins_bar.assert_not_called()

    def test_leading_history_before_the_listing_is_tolerated(self):
        """A symbol listed mid-window has no earlier bars — that is not a hole."""
        service, repo, _fetcher = build_service(exchange_bars=[_bar(8), _bar(9)])
        assert _ensure(service) == 2
        assert _inserted_timestamps(repo) == [_ts(8), _ts(9)]


class TestFailClosed:
    def test_missing_newest_bar_raises(self):
        service, repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(8)])
        with pytest.raises(StaleBarsError, match="incomplete window"):
            _ensure(service)
        repo.ins_bar.assert_not_called()

    def test_interior_hole_raises(self):
        service, repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(9)])
        with pytest.raises(StaleBarsError, match="incomplete window"):
            _ensure(service)
        repo.ins_bar.assert_not_called()

    def test_exchange_returning_nothing_raises(self):
        service, _repo, _fetcher = build_service(exchange_bars=[])
        with pytest.raises(StaleBarsError, match="incomplete window"):
            _ensure(service)

    def test_unmapped_symbol_raises(self):
        service, repo, _fetcher = build_service(exchange_bars=[_bar(9)])
        service._instruments.resolve_internal_cusip.return_value = None
        with pytest.raises(StaleBarsError, match="PRODUCT_XREF"):
            _ensure(service)
        repo.ins_bar.assert_not_called()

    def test_lookback_must_be_positive(self):
        service, _repo, _fetcher = build_service()
        with pytest.raises(ValueError, match="lookback"):
            _ensure(service, lookback=0)


class TestConcurrentInsertRace:
    """Deployments sharing an instrument fire at the same boundary."""

    def _losing_repo(self, service):
        service._repo.ins_bar.side_effect = ProcedureError(
            proc="market_data.sp_ins_price_bar",
            sqlstate="23505",
            message="duplicate key value violates unique constraint",
        )

    def test_lost_race_is_not_an_error(self):
        """Another worker storing the same bar first is benign, not a failure."""
        service, repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])
        self._losing_repo(service)
        assert _ensure(service) == 0
        assert repo.ins_bar.call_count == 3

    def test_partial_race_counts_only_what_this_run_stored(self):
        service, repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])
        repo.ins_bar.side_effect = [
            None,
            ProcedureError(proc="p", sqlstate="23505", message="dup"),
            None,
        ]
        assert _ensure(service) == 2

    def test_other_procedure_errors_still_propagate(self):
        """Only the unique violation is benign — a real failure must surface."""
        service, repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])
        repo.ins_bar.side_effect = ProcedureError(
            proc="p", sqlstate="23502", message="null value in column"
        )
        with pytest.raises(ProcedureError):
            _ensure(service)


class TestSync:
    def _sync(self, service, instruments, lookback=3):
        return service.sync(
            instruments=instruments,
            tm_interval_id=INTERVAL_1H,
            lookback=lookback,
            now=NOW,
        )

    def test_duplicate_instruments_are_fetched_once(self):
        """The caller derives the list from deployments, so repeats are expected."""
        service, repo, fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])
        result = self._sync(service, [(CUSIP, APP_ID)] * 4)
        assert result.instruments == 1
        assert len(fetcher.calls) == 1
        assert repo.ins_bar.call_count == 3

    def test_distinct_instruments_each_refresh(self):
        service, _repo, fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])
        result = self._sync(service, [(CUSIP, APP_ID), ("ethusdt.crypto", APP_ID)])
        assert result.instruments == 2
        assert len(fetcher.calls) == 2
        assert result.inserted == 6

    def test_same_cusip_on_a_different_app_is_not_deduped(self):
        service, _repo, fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])
        result = self._sync(service, [(CUSIP, APP_ID), (CUSIP, 99)])
        assert result.instruments == 2
        assert len(fetcher.calls) == 2

    def test_one_bad_instrument_does_not_stop_the_batch(self):
        """Best effort — apply is where an incomplete window stops the world."""
        service, _repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(8)])
        result = self._sync(service, [(CUSIP, APP_ID)])
        assert "incomplete window" in result.failures[CUSIP]
        assert result.inserted == 0

    def test_failures_are_reported_per_instrument(self):
        service, _repo, _fetcher = build_service(exchange_bars=[_bar(7), _bar(8), _bar(9)])

        real = service.ensure_fresh

        def flaky(*, internal_cusip, **kwargs):
            if internal_cusip == "bad.crypto":
                raise StaleBarsError("exchange down")
            return real(internal_cusip=internal_cusip, **kwargs)

        service.ensure_fresh = flaky
        result = self._sync(service, [("bad.crypto", APP_ID), (CUSIP, APP_ID)])
        assert list(result.failures) == ["bad.crypto"]
        assert result.instruments == 2
        assert result.inserted == 3

    def test_empty_instrument_list(self):
        service, _repo, fetcher = build_service()
        result = self._sync(service, [])
        assert (result.instruments, result.inserted, result.failures) == (0, 0, {})
        assert fetcher.calls == []


class TestInsertPayload:
    def test_bar_columns_reach_the_repo(self):
        service, repo, _fetcher = build_service(
            coverage_max=_ts(8), stored_bars=[_ts(7), _ts(8)], exchange_bars=[_bar(9)]
        )
        _ensure(service)
        kwargs = repo.ins_bar.call_args.kwargs
        assert kwargs["internal_cusip"] == CUSIP
        assert kwargs["tm_interval_id"] == INTERVAL_1H
        assert kwargs["source_app_id"] == APP_ID
        assert kwargs["bar_timestamp"] == _ts(9)
        assert (kwargs["open_px"], kwargs["high_px"]) == (100.0, 110.0)
        assert (kwargs["low_px"], kwargs["close_px"]) == (95.0, 105.0)
        assert kwargs["volume"] == 12.5


class TestReadBars:
    def _rows(self):
        return [
            {
                "bar_timestamp": _ts(9),
                "open_px": Decimal("100"),
                "high_px": Decimal("110"),
                "low_px": Decimal("95"),
                "close_px": Decimal("105"),
                "volume": Decimal("12.5"),
            },
            {
                "bar_timestamp": _ts(8),
                "open_px": Decimal("90"),
                "high_px": Decimal("99"),
                "low_px": Decimal("88"),
                "close_px": Decimal("98"),
                "volume": Decimal("3.5"),
            },
        ]

    def _read(self):
        service, repo, _fetcher = build_service()
        repo.get_bars.return_value = self._rows()
        return service.read_bars(
            internal_cusip=CUSIP,
            tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID,
            start=_ts(8),
            end=_ts(9),
        )

    def test_matches_the_pipeline_column_contract(self):
        """Same shape as fetch_df so indicator math needs no branch on source."""
        df = self._read()
        assert list(df.columns) == [
            "price", "factor", "Open", "High", "Low", "Close", "Volume",
        ]
        assert df.index.name == "datetime"
        assert str(df.index.tz) == "UTC"

    def test_sorted_ascending_by_timestamp(self):
        df = self._read()
        assert list(df.index) == [_ts(8), _ts(9)]

    def test_price_and_factor_both_track_close(self):
        df = self._read()
        assert list(df["price"]) == [98.0, 105.0]
        assert list(df["factor"]) == [98.0, 105.0]
        assert list(df["Close"]) == [98.0, 105.0]

    def test_decimals_are_converted_to_float(self):
        df = self._read()
        assert df["Open"].dtype == float
        assert df["Volume"].dtype == float

    def test_no_rows_gives_an_empty_frame(self):
        service, repo, _fetcher = build_service()
        repo.get_bars.return_value = []
        df = service.read_bars(
            internal_cusip=CUSIP,
            tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID,
            start=_ts(8),
            end=_ts(9),
        )
        assert df.empty


class TestLoadWindow:
    """The live-apply entry point: complete the window, then hand it over."""

    def _rows(self, hours):
        return [
            {
                "bar_timestamp": _ts(h),
                "open_px": Decimal("100"),
                "high_px": Decimal("110"),
                "low_px": Decimal("95"),
                "close_px": Decimal("105"),
                "volume": Decimal("12.5"),
            }
            for h in hours
        ]

    def test_reads_exactly_the_lookback_window(self):
        service, repo, _fetcher = build_service(coverage_max=_ts(9))
        repo.get_bars.return_value = self._rows([7, 8, 9])

        df = service.load_window(
            CUSIP, 3, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID, now=NOW
        )

        assert len(df) == 3
        # Newest closed bar back three, not three from `now`.
        assert repo.get_bars.call_args.kwargs["range_start"] == _ts(7)
        assert repo.get_bars.call_args.kwargs["range_end"] == _ts(9)

    def test_fetches_before_reading_when_stale(self):
        service, repo, fetcher = build_service(
            coverage_max=_ts(8), exchange_bars=[_bar(9)]
        )
        # The gap check sees 09:00 missing; the read afterwards sees it stored.
        repo.get_bars.side_effect = [
            self._rows([7, 8]),
            self._rows([7, 8, 9]),
        ]

        df = service.load_window(
            CUSIP, 3, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID, now=NOW
        )

        assert fetcher.calls, "expected the missing bar to be fetched"
        assert _inserted_timestamps(repo) == [_ts(9)]
        assert len(df) == 3

    def test_incomplete_window_raises_instead_of_returning_short(self):
        """Fail closed — a caller must never see a frame with a hole in it."""
        service, _repo, _fetcher = build_service(exchange_bars=[])

        with pytest.raises(StaleBarsError):
            service.load_window(
                CUSIP, 3, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID, now=NOW
            )

    def test_short_history_is_refused_even_though_the_gap_is_tolerated(self):
        """ensure_fresh allows pre-listing gaps; serving a signal does not.

        A newly listed instrument leaves the window legitimately short. The
        indicator would still compute on what arrived — on a fraction of the
        lookback the strategy was fitted on — so the read side draws the line.
        """
        service, repo, _fetcher = build_service(coverage_max=_ts(9))
        repo.get_bars.return_value = self._rows([8, 9])  # 2 of 10 requested

        with pytest.raises(StaleBarsError, match="only 2 of 10"):
            service.load_window(
                CUSIP, 10, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID, now=NOW
            )

    def test_slack_at_the_oldest_edge_is_allowed(self):
        """80% is enough — the newest bar is what the signal turns on."""
        service, repo, _fetcher = build_service(coverage_max=_ts(9))
        repo.get_bars.return_value = self._rows([2, 3, 4, 5, 6, 7, 8, 9])

        df = service.load_window(
            CUSIP, 10, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID, now=NOW
        )

        assert len(df) == 8

    def test_single_bar_lookback_reads_one_boundary(self):
        service, repo, _fetcher = build_service(coverage_max=_ts(9))
        repo.get_bars.return_value = self._rows([9])

        service.load_window(
            CUSIP, 1, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID, now=NOW
        )

        kwargs = repo.get_bars.call_args.kwargs
        assert kwargs["range_start"] == kwargs["range_end"] == _ts(9)


class TestIntervalResolution:
    def test_daily_window_uses_the_refdata_period(self):
        service, repo, fetcher = build_service(
            exchange_bars=[
                OhlcvBar(
                    bar_timestamp=datetime(2026, 7, d, tzinfo=UTC),
                    open_px=1.0, high_px=1.0, low_px=1.0, close_px=1.0, volume=1.0,
                )
                for d in (30, 31)
            ]
        )
        inserted = service.ensure_fresh(
            internal_cusip=CUSIP,
            tm_interval_id=1,
            source_app_id=APP_ID,
            lookback=2,
            now=NOW,
        )
        assert inserted == 2
        assert _inserted_timestamps(repo) == [
            datetime(2026, 7, 30, tzinfo=UTC),
            datetime(2026, 7, 31, tzinfo=UTC),
        ]
        assert fetcher.calls[0]["period"] == timedelta(days=1)
