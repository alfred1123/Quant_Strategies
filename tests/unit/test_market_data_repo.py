"""Unit tests for :mod:`quant.market_data.repo`."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from quant.market_data.repo import PriceBarRepo

PROC_DIR = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "liquidbase"
    / "market_data"
    / "procedures"
)

BAR_TS = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def repo():
    """A repo with no connection — PriceBarRepo holds a persistent one."""
    instance = PriceBarRepo.__new__(PriceBarRepo)
    instance.user_id = "tester"
    return instance


def _coverage_kwargs(**overrides):
    base = {"internal_cusip": "btcusdt.crypto", "tm_interval_id": 2, "source_app_id": 34}
    base.update(overrides)
    return base


def _bar_kwargs(**overrides):
    base = {
        "internal_cusip": "btcusdt.crypto",
        "tm_interval_id": 2,
        "source_app_id": 10,
        "bar_timestamp": BAR_TS,
        "open_px": Decimal("100"),
        "high_px": Decimal("110"),
        "low_px": Decimal("95"),
        "close_px": Decimal("105"),
        "volume": Decimal("12.5"),
    }
    base.update(overrides)
    return base


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


class TestCallMatchesProcedureDdl:
    """CALL argument count must track the procedure DDL.

    Postgres treats a changed parameter list as a new overload instead of an
    error, so a stale CALL keeps resolving to the old signature and the
    mismatch surfaces as missing data rather than a failure.
    """

    @patch.object(PriceBarRepo, "_call_get", return_value=[])
    def test_get_coverage(self, mock_get, repo):
        repo.get_coverage(**_coverage_kwargs())
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_GET_PRICE_BAR_COVERAGE.sql")

    @patch.object(PriceBarRepo, "_call_get", return_value=[])
    def test_get_bars(self, mock_get, repo):
        repo.get_bars(
            internal_cusip="btcusdt.crypto",
            tm_interval_id=2,
            source_app_id=34,
            range_start=BAR_TS,
            range_end=BAR_TS,
        )
        sql = mock_get.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_GET_PRICE_BAR.sql")

    @patch.object(PriceBarRepo, "_call_write")
    def test_ins_bar(self, mock_write, repo):
        repo.ins_bar(**_bar_kwargs())
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_INS_PRICE_BAR.sql")

    @patch.object(PriceBarRepo, "_call_write")
    def test_ins_bar_sends_the_gateway_user(self, mock_write, repo):
        """USER_ID is NOT NULL on PRICE_BAR — the repo must always supply one."""
        repo.ins_bar(**_bar_kwargs())
        assert mock_write.call_args.args[1][-1] == "tester"


class TestGetCoverage:
    @patch.object(PriceBarRepo, "_call_get", return_value=[])
    def test_no_rows_is_none(self, _get, repo):
        assert repo.get_coverage(**_coverage_kwargs()) is None

    @patch.object(
        PriceBarRepo,
        "_call_get",
        return_value=[{"min_bar_timestamp": None, "max_bar_timestamp": None}],
    )
    def test_empty_table_returns_none_not_a_row_of_nulls(self, _get, repo):
        """The coverage SP always returns one row; nulls mean nothing is stored."""
        assert repo.get_coverage(**_coverage_kwargs()) is None

    @patch.object(
        PriceBarRepo,
        "_call_get",
        return_value=[{"min_bar_timestamp": BAR_TS, "max_bar_timestamp": BAR_TS}],
    )
    def test_returns_bounds(self, _get, repo):
        assert repo.get_coverage(**_coverage_kwargs())["max_bar_timestamp"] == BAR_TS

    @patch.object(PriceBarRepo, "_call_get", return_value=[])
    def test_scopes_freshness_to_one_source(self, mock_get, repo):
        """Another venue's bars say nothing about this venue's freshness."""
        repo.get_coverage(**_coverage_kwargs(source_app_id=35))
        assert 35 in mock_get.call_args.args[1]


class TestSourceScoping:
    """A window must come from one venue — see decision #47."""

    @patch.object(PriceBarRepo, "_call_get", return_value=[])
    def test_reads_pass_the_source_to_the_procedure(self, mock_get, repo):
        repo.get_bars(
            internal_cusip="btcusdt.crypto",
            tm_interval_id=2,
            source_app_id=35,
            range_start=BAR_TS,
            range_end=BAR_TS,
        )
        assert 35 in mock_get.call_args.args[1]

    @pytest.mark.parametrize(
        "proc_file", ["SP_GET_PRICE_BAR.sql", "SP_GET_PRICE_BAR_COVERAGE.sql"]
    )
    def test_read_procedures_filter_on_source(self, proc_file):
        """Guards the SQL itself: a parameter that is accepted and then ignored
        would leave every read blended while the call-site tests still pass."""
        txt = (PROC_DIR / proc_file).read_text()
        assert "SOURCE_APP_ID  = IN_SOURCE_APP_ID" in txt

    def test_source_is_part_of_the_primary_key(self):
        ddl = (PROC_DIR.parent / "tables" / "PRICE_BAR.sql").read_text()
        pk = re.search(r"PRIMARY KEY \((.*?)\)", ddl, re.S)
        assert pk and "SOURCE_APP_ID" in pk.group(1)


class TestValidation:
    @pytest.mark.parametrize(
        "field", ["internal_cusip", "tm_interval_id", "source_app_id"]
    )
    def test_coverage_requires_key(self, repo, field):
        with pytest.raises(ValueError, match=field):
            repo.get_coverage(**_coverage_kwargs(**{field: None}))

    @pytest.mark.parametrize(
        "field",
        ["internal_cusip", "tm_interval_id", "source_app_id", "bar_timestamp",
         "open_px", "high_px", "low_px", "close_px", "volume"],
    )
    def test_insert_requires_every_column(self, repo, field):
        with pytest.raises(ValueError, match=field):
            repo.ins_bar(**_bar_kwargs(**{field: None}))

    def test_blank_cusip_rejected(self, repo):
        with pytest.raises(ValueError, match="internal_cusip"):
            repo.ins_bar(**_bar_kwargs(internal_cusip="   "))
