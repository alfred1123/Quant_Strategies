"""Unit tests for :mod:`quant.api.admin.repo` connection maintenance."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from quant.api.admin.models import StaleConnectionSweep
from quant.api.admin.repo import ConnectionMaintenanceRepo, DEFAULT_STALE_IDLE_SECONDS

PROC_DIR = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "liquidbase"
    / "core_admin"
    / "procedures"
)


@pytest.fixture
def repo():
    instance = ConnectionMaintenanceRepo.__new__(ConnectionMaintenanceRepo)
    instance.user_id = "system"
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
    @patch.object(ConnectionMaintenanceRepo, "_call_write", return_value=(2, 2))
    def test_terminate_stale_connections_arg_count(self, mock_write, repo):
        repo.terminate_stale_connections()
        sql = mock_write.call_args.args[0]
        assert _call_arg_count(sql) == _ddl_param_count("SP_TERM_STALE_CONNECTIONS.sql")


class TestTerminateStaleConnections:
    @patch.object(ConnectionMaintenanceRepo, "_call_write", return_value=(2, 2))
    def test_returns_sweep(self, mock_write, repo):
        assert repo.terminate_stale_connections(idle_seconds=3600) == StaleConnectionSweep(
            stale=2, terminated=2,
        )

    @patch.object(ConnectionMaintenanceRepo, "_call_write", return_value=())
    def test_returns_zeros_on_empty_tail(self, mock_write, repo):
        assert repo.terminate_stale_connections() == StaleConnectionSweep(stale=0, terminated=0)

    @patch.object(ConnectionMaintenanceRepo, "_call_write", return_value=(1, 0))
    def test_passes_user_id_and_idle_seconds(self, mock_write, repo):
        repo.terminate_stale_connections(idle_seconds=7200)
        params = mock_write.call_args.args[1]
        assert params == ("system", 7200)

    def test_default_idle_seconds_is_one_hour(self):
        assert DEFAULT_STALE_IDLE_SECONDS == 3600
