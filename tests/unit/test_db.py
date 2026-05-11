"""Unit tests for ``DbGateway`` helpers."""

from unittest.mock import MagicMock, patch

import pytest

from db import DbGateway


class TestCallWrite:
    @patch("db.psycopg.connect")
    def test_status_only_returns_empty_tail(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "", "")

        gw = DbGateway("postgresql://test")
        assert gw._call_write("CALL x", ()) == ()
        mock_cur.execute.assert_called_once_with("CALL x", ())

    @patch("db.psycopg.connect")
    def test_extra_outs_after_triplet(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "", "", 42, "extra")

        gw = DbGateway("postgresql://test")
        assert gw._call_write("CALL x", ()) == (42, "extra")

    @patch("db.psycopg.connect")
    def test_raises_on_sqlstate(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("23505", "msg", "detail")

        gw = DbGateway("postgresql://test")
        with pytest.raises(RuntimeError, match="23505"):
            gw._call_write("CALL x", ())
        mock_conn.commit.assert_not_called()

    @patch("db.psycopg.connect")
    def test_raises_on_short_row(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "")

        gw = DbGateway("postgresql://test")
        with pytest.raises(RuntimeError, match="invalid OUT shape"):
            gw._call_write("CALL x", ())

    @patch("db.psycopg.connect")
    def test_raises_on_none_row(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        gw = DbGateway("postgresql://test")
        with pytest.raises(RuntimeError, match="invalid OUT shape"):
            gw._call_write("CALL x", ())
