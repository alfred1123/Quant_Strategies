"""Unit tests for src/jobs.py — BacktestJobRepo."""

import sys
import os
import json
import uuid
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jobs import BacktestJobRepo, QueueRow, _to_row


# ── helpers ────────────────────────────────────────────────────────────

QUEUE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
STRATEGY_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
_CONNINFO = "postgresql://test:test@localhost/test"


def make_repo() -> BacktestJobRepo:
    with patch.dict("os.environ", {"DATABASE_URL": _CONNINFO}):
        return BacktestJobRepo(_CONNINFO, user_id="test_user")


def _queue_row_tuple(status="QUEUED", terminal="N"):
    return (
        QUEUE_ID, 1, STRATEGY_ID, 1,
        status, terminal,
        100, None, "test_user", "2024-01-01T00:00:00",
    )


# ── _to_row ────────────────────────────────────────────────────────────

class TestToRow:
    def test_maps_all_fields(self):
        t = _queue_row_tuple()
        row = _to_row(t)
        assert row.queue_id == QUEUE_ID
        assert row.queue_vid == 1
        assert row.strategy_id == STRATEGY_ID
        assert row.strategy_vid == 1
        assert row.status_name == "QUEUED"
        assert row.is_terminal is False
        assert row.priority == 100
        assert row.error_text is None
        assert row.user_id == "test_user"

    def test_terminal_flag_y(self):
        row = _to_row(_queue_row_tuple(status="COMPLETED", terminal="Y"))
        assert row.is_terminal is True

    def test_terminal_flag_n(self):
        row = _to_row(_queue_row_tuple(status="QUEUED", terminal="N"))
        assert row.is_terminal is False


# ── ins_queue ──────────────────────────────────────────────────────────

class TestInsQueue:
    def test_calls_write_with_correct_params(self):
        repo = make_repo()
        with patch.object(repo, "_call_write") as mock_write:
            repo.ins_queue(QUEUE_ID, STRATEGY_ID, 1, 10, 100)
            mock_write.assert_called_once()
            sql, params = mock_write.call_args[0]
            assert "BT.SP_INS_QUEUE" in sql
            assert params[0] == str(QUEUE_ID)
            assert params[1] == str(STRATEGY_ID)
            assert params[2] == 1    # strategy_vid
            assert params[3] == 10   # queue_status_id
            assert params[4] == 100  # priority

    def test_uses_provided_user_id(self):
        repo = make_repo()
        with patch.object(repo, "_call_write") as mock_write:
            repo.ins_queue(QUEUE_ID, STRATEGY_ID, 1, 10, 100, user_id="alice")
            _, params = mock_write.call_args[0]
            assert params[6] == "alice"

    def test_falls_back_to_self_user_id(self):
        repo = make_repo()
        with patch.object(repo, "_call_write") as mock_write:
            repo.ins_queue(QUEUE_ID, STRATEGY_ID, 1, 10, 100)
            _, params = mock_write.call_args[0]
            assert params[6] == "test_user"


# ── get_status_id ──────────────────────────────────────────────────────

class TestGetStatusId:
    def test_returns_id_for_known_name(self):
        repo = make_repo()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (7,)

        with patch("jobs.psycopg.connect", return_value=mock_conn):
            result = repo.get_status_id("QUEUED")

        assert result == 7

    def test_raises_for_unknown_name(self):
        repo = make_repo()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        with patch("jobs.psycopg.connect", return_value=mock_conn):
            with pytest.raises(ValueError, match="REFDATA.QUEUE_STATUS missing"):
                repo.get_status_id("BOGUS")


# ── insert_result ──────────────────────────────────────────────────────

class TestInsertResult:
    def test_returns_result_id(self):
        repo = make_repo()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (42,)

        with patch("jobs.psycopg.connect", return_value=mock_conn):
            result = repo.insert_result(QUEUE_ID, {"key": "val"})

        assert result == 42
        mock_conn.commit.assert_called_once()

    def test_raises_if_no_row_returned(self):
        repo = make_repo()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        with patch("jobs.psycopg.connect", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="RESULT_ID"):
                repo.insert_result(QUEUE_ID, {})

    def test_serialises_payload_as_json(self):
        repo = make_repo()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (1,)

        with patch("jobs.psycopg.connect", return_value=mock_conn):
            repo.insert_result(QUEUE_ID, {"sharpe": 1.5})

        args = mock_cur.execute.call_args[0][1]
        assert json.loads(args[1]) == {"sharpe": 1.5}


# ── read methods ───────────────────────────────────────────────────────

class TestReadMethods:
    def _mock_conn(self, rows):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = rows[0] if rows else None
        mock_cur.fetchall.return_value = rows
        return mock_conn

    def test_get_returns_row(self):
        repo = make_repo()
        t = _queue_row_tuple()
        with patch("jobs.psycopg.connect", return_value=self._mock_conn([t])):
            row = repo.get(QUEUE_ID)
        assert isinstance(row, QueueRow)
        assert row.queue_id == QUEUE_ID

    def test_get_returns_none_when_not_found(self):
        repo = make_repo()
        with patch("jobs.psycopg.connect", return_value=self._mock_conn([])):
            row = repo.get(QUEUE_ID)
        assert row is None

    def test_list_for_user_returns_list(self):
        repo = make_repo()
        rows = [_queue_row_tuple(), _queue_row_tuple()]
        with patch("jobs.psycopg.connect", return_value=self._mock_conn(rows)):
            result = repo.list_for_user("alice")
        assert len(result) == 2
        assert all(isinstance(r, QueueRow) for r in result)

    def test_list_by_status_returns_list(self):
        repo = make_repo()
        rows = [_queue_row_tuple("RUNNING")]
        with patch("jobs.psycopg.connect", return_value=self._mock_conn(rows)):
            result = repo.list_by_status("RUNNING")
        assert len(result) == 1
        assert result[0].status_name == "RUNNING"

    def test_history_returns_all_vids(self):
        repo = make_repo()
        rows = [_queue_row_tuple("QUEUED"), _queue_row_tuple("RUNNING")]
        with patch("jobs.psycopg.connect", return_value=self._mock_conn(rows)):
            result = repo.history(QUEUE_ID)
        assert len(result) == 2
