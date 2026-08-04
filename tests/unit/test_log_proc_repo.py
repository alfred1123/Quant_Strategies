"""Unit tests for :mod:`quant.api.admin.repo`."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from quant.api.admin.repo import LogProcRepo

PROC_DIR = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "liquidbase"
    / "core_admin"
    / "procedures"
)


@pytest.fixture
def repo():
    instance = LogProcRepo.__new__(LogProcRepo)
    instance.user_id = "tester"
    return instance


def _ddl_param_count(proc_file: str) -> int:
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
    return sql.count("%s") + sql.count("NULL")


class TestCallMatchesProcedureDdl:
    """CALL argument count must track the procedure DDL."""

    @patch.object(LogProcRepo, "_call_write", return_value=(42,))
    def test_summarize_arg_count(self, mock_write, repo):
        repo.summarize()
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_INS_LOG_PROC_SUMMARY.sql")


class TestSummarize:
    @patch.object(LogProcRepo, "_call_write", return_value=(7,))
    def test_returns_rows_affected(self, mock_write, repo):
        assert repo.summarize() == 7

    @patch.object(LogProcRepo, "_call_write", return_value=())
    def test_returns_zero_on_empty_tail(self, mock_write, repo):
        assert repo.summarize() == 0

    @patch.object(LogProcRepo, "_call_write", return_value=(0,))
    def test_passes_user_id(self, mock_write, repo):
        repo.summarize()
        params = mock_write.call_args.args[1]
        assert params[0] == "tester"
