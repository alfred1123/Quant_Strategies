"""Unit tests for BtQueueRepo.sp_get_queued_count OUT-row parsing."""

from unittest.mock import MagicMock, patch

import pytest

from quant.queue.repo import BtQueueRepo
from quant.shared.db import ProcedureError


@pytest.fixture
def repo():
    return BtQueueRepo("postgresql://test")


class TestSpGetQueuedCount:
    def test_zero_count_not_misread_as_sqlstate(self, repo):
        """Count 0 must not be parsed as SQLSTATE 0 with SQLMSG 50."""
        cur = MagicMock()
        cur.fetchone.return_value = (0, "00000", "50", "Stored Procedure completed successfully")

        def fake_run(fn):
            return fn(cur), None

        with patch.object(repo, "_run", side_effect=fake_run):
            assert repo.sp_get_queued_count("alice", 1) == 0

    def test_nonzero_count(self, repo):
        cur = MagicMock()
        cur.fetchone.return_value = (3, "00000", "50", "ok")

        def fake_run(fn):
            return fn(cur), None

        with patch.object(repo, "_run", side_effect=fake_run):
            assert repo.sp_get_queued_count("alice", 1) == 3

    def test_proc_error_raises(self, repo):
        cur = MagicMock()
        cur.fetchone.return_value = (None, "P0001", "50", "boom")

        def fake_run(fn):
            return fn(cur), None

        with patch.object(repo, "_run", side_effect=fake_run):
            with pytest.raises(ProcedureError) as exc_info:
                repo.sp_get_queued_count("alice", 1)
            assert exc_info.value.sqlstate == "P0001"
            assert exc_info.value.proc == "bt.sp_get_queued_count"
            assert exc_info.value.message == "boom"
