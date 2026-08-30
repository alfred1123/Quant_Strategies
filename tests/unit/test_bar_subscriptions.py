"""Unit tests for :mod:`quant.market_data.subscriptions` — no DB, no ccxt."""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quant.market_data.service import MAX_BACKFILL_BARS
from quant.market_data.subscriptions import (
    BarSubscriptionRepo,
    BarSubscriptionService,
    SubscriptionInstrumentSource,
    SubscriptionError,
)
from quant.shared.db import ProcedureError

PROC_DIR = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "liquidbase"
    / "market_data"
    / "procedures"
)

DAILY = 1
BYBIT = 34
CUSIP = "btcusdt.crypto"
FIRST_BAR = datetime(2026, 1, 1, tzinfo=UTC)
LAST_BAR = datetime(2026, 8, 1, tzinfo=UTC)


@pytest.fixture
def repo():
    instance = BarSubscriptionRepo.__new__(BarSubscriptionRepo)
    instance.user_id = "tester"
    return instance


def _ddl_param_count(proc_file: str) -> int:
    """Number of IN/OUT parameters declared by a procedure's DDL."""
    txt = (PROC_DIR / proc_file).read_text()
    sig = re.search(
        r"CREATE OR REPLACE PROCEDURE\s+[\w.]+\s*\((.*?)\)\s*LANGUAGE",
        txt,
        re.S | re.I,
    )
    assert sig, f"could not parse a signature out of {proc_file}"
    return len(
        [ln for ln in sig.group(1).splitlines() if re.match(r"\s*(IN|OUT)\s+\w+", ln)]
    )


def _call_arg_count(sql: str) -> int:
    return sql.count("%s") + sql.count("NULL::")


def _ins_kwargs(**overrides):
    base = {
        "bar_subscription_id": uuid.uuid4(),
        "internal_cusip": CUSIP,
        "tm_interval_id": DAILY,
        "source_app_id": BYBIT,
        "is_enabled_ind": "Y",
    }
    base.update(overrides)
    return base


class TestCallMatchesProcedureDdl:
    """CALL argument count must track the procedure DDL.

    Postgres treats a changed parameter list as a new overload instead of an
    error, so a stale CALL keeps resolving to the old signature and the
    mismatch surfaces as missing data rather than a failure.
    """

    @patch.object(BarSubscriptionRepo, "_call_get", return_value=[{"a": 1}])
    @patch.object(BarSubscriptionRepo, "_call_write", return_value=())
    def test_ins(self, mock_write, _get, repo):
        repo.sp_ins_bar_subscription(**_ins_kwargs())
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_INS_BAR_SUBSCRIPTION.sql")

    @patch.object(BarSubscriptionRepo, "_call_get", return_value=[])
    def test_get(self, mock_get, repo):
        repo.sp_get_bar_subscription()
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_GET_BAR_SUBSCRIPTION.sql")

    @patch.object(BarSubscriptionRepo, "_call_get", return_value=[])
    def test_get_active(self, mock_get, repo):
        repo.sp_get_active_bar_subscriptions()
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count(
            "SP_GET_ACTIVE_BAR_SUBSCRIPTIONS.sql"
        )


class TestRepoValidation:
    @pytest.mark.parametrize(
        "field", ["bar_subscription_id", "internal_cusip", "tm_interval_id", "source_app_id"]
    )
    def test_key_fields_are_required(self, repo, field):
        with pytest.raises(ValueError, match=field):
            repo.sp_ins_bar_subscription(**_ins_kwargs(**{field: None}))

    def test_enabled_flag_must_be_y_or_n(self, repo):
        with pytest.raises(ValueError, match="is_enabled_ind"):
            repo.sp_ins_bar_subscription(**_ins_kwargs(is_enabled_ind="true"))

    @patch.object(BarSubscriptionRepo, "_call_get", return_value=[])
    @patch.object(BarSubscriptionRepo, "_call_write", return_value=())
    def test_a_write_that_reads_back_nothing_is_a_bug_not_an_empty_result(
        self, _write, _get, repo
    ):
        with pytest.raises(RuntimeError, match="returned no row"):
            repo.sp_ins_bar_subscription(**_ins_kwargs())


class TestInstrumentSource:
    def test_hands_the_warmer_what_the_procedure_returned(self):
        repo = MagicMock()
        rows = [{"tm_interval_id": DAILY, "internal_cusip": CUSIP, "app_id": BYBIT}]
        repo.sp_get_active_bar_subscriptions.return_value = rows

        assert SubscriptionInstrumentSource(repo).instruments() == rows

    def test_emits_the_same_shape_as_the_deployment_side(self):
        """The union in the warmer is a concatenation only if the keys match."""
        repo = MagicMock()
        repo.sp_get_active_bar_subscriptions.return_value = [
            {"tm_interval_id": DAILY, "internal_cusip": CUSIP, "app_id": BYBIT}
        ]

        row = SubscriptionInstrumentSource(repo).instruments()[0]

        assert set(row) == {"tm_interval_id", "internal_cusip", "app_id"}


def build_service(*, bounds=(FIRST_BAR, LAST_BAR), gaps=(), vendor_symbol="BTCUSDT"):
    repo = MagicMock()
    instruments = MagicMock()
    instruments.resolve_internal_cusip.return_value = vendor_symbol

    bar_service = MagicMock()
    bar_service.stored_bounds.return_value = bounds
    bar_service.find_gaps.return_value = list(gaps)

    factory = MagicMock()
    factory.for_app.return_value = bar_service

    service = BarSubscriptionService(repo, instruments, factory)
    return service, repo, factory, bar_service


class TestSubscribeValidatesOnWrite:
    """Three silent per-tick warm failures become one immediate error."""

    def test_unknown_venue_is_refused(self):
        service, repo, factory, _bar = build_service()
        factory.for_app.side_effect = RuntimeError("no market data venue")

        with pytest.raises(SubscriptionError, match="not an exchange"):
            service.subscribe(
                internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=99
            )
        repo.sp_ins_bar_subscription.assert_not_called()

    def test_unmapped_symbol_is_refused(self):
        service, repo, _factory, _bar = build_service(vendor_symbol=None)

        with pytest.raises(SubscriptionError, match="PRODUCT_XREF"):
            service.subscribe(
                internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
            )
        repo.sp_ins_bar_subscription.assert_not_called()

    def test_a_valid_series_is_written(self):
        service, repo, _factory, _bar = build_service()

        service.subscribe(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
        )

        kwargs = repo.sp_ins_bar_subscription.call_args.kwargs
        assert kwargs["internal_cusip"] == CUSIP
        assert kwargs["source_app_id"] == BYBIT
        assert kwargs["is_enabled_ind"] == "Y"

    def test_an_id_is_generated_when_none_is_given(self):
        service, repo, _factory, _bar = build_service()

        service.subscribe(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
        )

        assert isinstance(
            repo.sp_ins_bar_subscription.call_args.kwargs["bar_subscription_id"],
            uuid.UUID,
        )

    def test_an_id_that_is_given_versions_that_row(self):
        service, repo, _factory, _bar = build_service()
        existing = uuid.uuid4()

        service.subscribe(
            internal_cusip=CUSIP,
            tm_interval_id=DAILY,
            source_app_id=BYBIT,
            is_enabled_ind="N",
            bar_subscription_id=existing,
        )

        kwargs = repo.sp_ins_bar_subscription.call_args.kwargs
        assert kwargs["bar_subscription_id"] == existing
        assert kwargs["is_enabled_ind"] == "N"


class TestDuplicateSubscription:
    def test_a_second_open_row_reports_the_series_not_the_constraint(self):
        service, repo, _factory, _bar = build_service()
        repo.sp_ins_bar_subscription.side_effect = ProcedureError(
            proc="SP_INS_BAR_SUBSCRIPTION",
            sqlstate="23505",
            message="duplicate key value violates unique constraint",
        )

        with pytest.raises(SubscriptionError, match="already being captured"):
            service.subscribe(
                internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
            )

    def test_any_other_procedure_error_is_not_reinterpreted(self):
        service, repo, _factory, _bar = build_service()
        repo.sp_ins_bar_subscription.side_effect = ProcedureError(
            proc="SP_INS_BAR_SUBSCRIPTION", sqlstate="42883", message="no such function"
        )

        with pytest.raises(ProcedureError):
            service.subscribe(
                internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
            )


class TestCoverage:
    def test_reports_bounds_and_gap_count(self):
        service, _repo, _factory, _bar = build_service(
            gaps=[datetime(2026, 3, 1, tzinfo=UTC)]
        )

        result = service.coverage(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
        )

        assert result == {
            "first_bar": FIRST_BAR,
            "last_bar": LAST_BAR,
            "gaps": 1,
            "error": None,
        }

    def test_nothing_stored_is_empty_rather_than_an_error(self):
        service, _repo, _factory, bar = build_service(bounds=None)

        result = service.coverage(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
        )

        assert result == {
            "first_bar": None,
            "last_bar": None,
            "gaps": None,
            "error": None,
        }
        # No bounds means no range to look for holes in.
        bar.find_gaps.assert_not_called()

    def test_gaps_are_looked_for_only_between_the_bounds(self):
        """History older than the first bar is backfill's job, not a gap."""
        service, _repo, _factory, bar = build_service()

        service.coverage(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT
        )

        kwargs = bar.find_gaps.call_args.kwargs
        assert (kwargs["start"], kwargs["end"]) == (FIRST_BAR, LAST_BAR)

    def test_a_dead_venue_degrades_one_row_instead_of_the_list(self):
        service, repo, factory, _bar = build_service()
        repo.sp_get_bar_subscription.return_value = [
            {
                "internal_cusip": CUSIP,
                "tm_interval_id": DAILY,
                "source_app_id": BYBIT,
            }
        ]
        factory.for_app.side_effect = RuntimeError("venue gone")

        rows = service.list_subscriptions()

        assert len(rows) == 1
        assert rows[0]["coverage"]["error"] is not None
        assert rows[0]["coverage"]["first_bar"] is None


class TestListing:
    def test_every_row_carries_its_coverage(self):
        service, repo, _factory, _bar = build_service()
        repo.sp_get_bar_subscription.return_value = [
            {"internal_cusip": CUSIP, "tm_interval_id": DAILY, "source_app_id": BYBIT},
            {"internal_cusip": "ethusdt.crypto", "tm_interval_id": DAILY,
             "source_app_id": BYBIT},
        ]

        rows = service.list_subscriptions()

        assert [r["coverage"]["last_bar"] for r in rows] == [LAST_BAR, LAST_BAR]

    def test_the_read_is_not_scoped_to_a_caller(self):
        """Bars are shared facts, so the list is the platform's, not a user's."""
        service, repo, _factory, _bar = build_service()
        repo.sp_get_bar_subscription.return_value = []

        service.list_subscriptions()

        assert repo.sp_get_bar_subscription.call_args.kwargs == {}


class TestVendorSymbolOnEveryRow:
    """The page shows what the venue calls a product, not only our identifier."""

    def test_each_row_carries_the_symbol_the_venue_prints(self):
        service, repo, _factory, _bar = build_service(vendor_symbol="BTCUSDT")
        repo.sp_get_bar_subscription.return_value = [
            {"internal_cusip": CUSIP, "tm_interval_id": DAILY, "source_app_id": BYBIT}
        ]

        rows = service.list_subscriptions()

        assert rows[0]["vendor_symbol"] == "BTCUSDT"

    def test_resolution_is_scoped_to_the_row_s_own_venue(self):
        """The same product is a different ticker on a different exchange."""
        service, repo, _factory, _bar = build_service()
        repo.sp_get_bar_subscription.return_value = [
            {"internal_cusip": CUSIP, "tm_interval_id": DAILY, "source_app_id": BYBIT}
        ]

        service.list_subscriptions()

        service._instruments.resolve_internal_cusip.assert_any_call(CUSIP, BYBIT)

    def test_a_withdrawn_xref_is_none_rather_than_a_broken_list(self):
        """Capture is broken, and the list is exactly where you would see why."""
        service, repo, _factory, _bar = build_service(vendor_symbol=None)
        repo.sp_get_bar_subscription.return_value = [
            {"internal_cusip": CUSIP, "tm_interval_id": DAILY, "source_app_id": BYBIT}
        ]

        rows = service.list_subscriptions()

        assert rows[0]["vendor_symbol"] is None


class TestBackfillPlan:
    """Routed to the venue's bar service, and costing no exchange call."""

    def test_the_plan_comes_from_the_series_own_venue(self):
        service, _repo, factory, bar_service = build_service()

        service.plan_backfill(
            internal_cusip=CUSIP,
            tm_interval_id=DAILY,
            source_app_id=BYBIT,
            target=FIRST_BAR,
        )

        factory.for_app.assert_called_once_with(BYBIT)
        assert bar_service.plan_backfill.call_args.kwargs == {
            "internal_cusip": CUSIP,
            "tm_interval_id": DAILY,
            "source_app_id": BYBIT,
            "target": FIRST_BAR,
        }

    def test_it_does_not_ask_the_venue_how_deep_it_goes(self):
        """Depth is an exchange call; a plan is stored bars and arithmetic, so
        the dialog can re-ask after every fill."""
        service, _repo, _factory, bar_service = build_service()

        service.plan_backfill(
            internal_cusip=CUSIP,
            tm_interval_id=DAILY,
            source_app_id=BYBIT,
            target=FIRST_BAR,
        )

        bar_service.venue_depth.assert_not_called()


class TestVenueDepth:
    """Passes the venue's floor through, with the ceiling one fill may span."""

    def test_carries_the_fill_ceiling_so_the_page_can_warn_before_the_click(self):
        service, _repo, factory, bar_service = build_service()
        bar_service.venue_depth.return_value = (FIRST_BAR, 2349)

        depth = service.venue_depth(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT,
        )

        assert depth == {
            "earliest": FIRST_BAR,
            "bars_available": 2349,
            "max_backfill_bars": MAX_BACKFILL_BARS,
        }
        factory.for_app.assert_called_once_with(BYBIT)

    def test_a_venue_serving_nothing_still_reports_the_ceiling(self):
        service, _repo, _factory, bar_service = build_service()
        bar_service.venue_depth.return_value = (None, None)

        depth = service.venue_depth(
            internal_cusip=CUSIP, tm_interval_id=DAILY, source_app_id=BYBIT,
        )

        assert depth["earliest"] is None
        assert depth["max_backfill_bars"] == MAX_BACKFILL_BARS


class TestBackfill:
    def test_delegates_to_the_venue_service(self):
        service, _repo, _factory, bar = build_service()
        start = datetime(2025, 1, 1, tzinfo=UTC)

        service.backfill(
            internal_cusip=CUSIP,
            tm_interval_id=DAILY,
            source_app_id=BYBIT,
            start=start,
        )

        kwargs = bar.backfill.call_args.kwargs
        assert kwargs["start"] == start
        assert kwargs["source_app_id"] == BYBIT
