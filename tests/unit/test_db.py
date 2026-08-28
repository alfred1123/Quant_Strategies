"""Unit tests for ``DbGateway`` helpers."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from quant.shared.db import DbGateway, ProcedureError, _redact

# Shape of a real Fernet token: the 0x80 version byte base64-encodes to "gAAAAA".
_CIPHERTEXT = "gAAAAABqkYSOK9y-7-avVAadofsaAWhCOziTPCcZxFE5u1bq5LnAWYuZ"


class TestRedact:
    """Encrypted exchange keys must not reach a log sink."""

    def test_replaces_a_fernet_token_with_its_length(self):
        assert _redact((_CIPHERTEXT,)) == (f"<encrypted:{len(_CIPHERTEXT)} chars>",)

    def test_keeps_ordinary_params_readable(self):
        """Redacting everything would make the log useless for debugging."""
        params = ("btcusdt.crypto", 34, None, 0.001)
        assert _redact(params) == params

    def test_redacts_only_the_encrypted_positions(self):
        params = ("user-1", _CIPHERTEXT, 34, _CIPHERTEXT, "label")
        got = _redact(params)
        assert got[0] == "user-1" and got[2] == 34 and got[4] == "label"
        assert _CIPHERTEXT not in got

    def test_matches_on_format_not_position(self):
        """Any proc may carry an encrypted column, so position cannot be assumed."""
        assert _redact((1, 2, _CIPHERTEXT))[2].startswith("<encrypted:")

    def test_leaves_a_string_that_merely_starts_similarly(self):
        assert _redact(("gAAAA",)) == ("gAAAA",)


class TestWriteLoggingRedaction:
    @patch("quant.shared.db.psycopg.connect")
    def test_commit_log_carries_no_ciphertext(self, mock_connect, caplog):
        """The credential insert logged its ciphertext at INFO before this."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "", "")

        gw = DbGateway("postgresql://test")
        with caplog.at_level(logging.INFO, logger="quant.shared.db"):
            gw._call_write("CALL core_admin.sp_ins_api_credential(%s)", (_CIPHERTEXT,))

        assert _CIPHERTEXT not in caplog.text
        assert "<encrypted:" in caplog.text

    @patch("quant.shared.db.psycopg.connect")
    def test_failure_log_carries_no_ciphertext(self, mock_connect, caplog):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("23505", "msg", "detail")

        gw = DbGateway("postgresql://test")
        with caplog.at_level(logging.ERROR, logger="quant.shared.db"):
            with pytest.raises(ProcedureError):
                gw._call_write("CALL x(%s)", (_CIPHERTEXT,))

        assert _CIPHERTEXT not in caplog.text

    @patch("quant.shared.db.psycopg.connect")
    def test_the_real_parameters_still_reach_the_database(self, mock_connect):
        """Redaction is a logging concern only — the proc gets the ciphertext."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "", "")

        gw = DbGateway("postgresql://test")
        gw._call_write("CALL x(%s)", (_CIPHERTEXT,))
        mock_cur.execute.assert_called_once_with("CALL x(%s)", (_CIPHERTEXT,))


class TestCallWrite:
    @patch("quant.shared.db.psycopg.connect")
    def test_status_only_returns_empty_tail(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "", "")

        gw = DbGateway("postgresql://test")
        assert gw._call_write("CALL x", ()) == ()
        mock_cur.execute.assert_called_once_with("CALL x", ())

    @patch("quant.shared.db.psycopg.connect")
    def test_extra_outs_after_triplet(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "", "", 42, "extra")

        gw = DbGateway("postgresql://test")
        assert gw._call_write("CALL x", ()) == (42, "extra")

    @patch("quant.shared.db.psycopg.connect")
    def test_raises_on_sqlstate(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("23505", "msg", "detail")

        gw = DbGateway("postgresql://test")
        with pytest.raises(ProcedureError) as exc_info:
            gw._call_write("CALL x(%s)", ())
        assert exc_info.value.sqlstate == "23505"
        assert exc_info.value.message == "detail"
        assert exc_info.value.proc == "x"
        mock_conn.commit.assert_not_called()

    @patch("quant.shared.db.psycopg.connect")
    def test_raises_on_short_row(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = ("00000", "")

        gw = DbGateway("postgresql://test")
        with pytest.raises(RuntimeError, match="invalid OUT shape"):
            gw._call_write("CALL x", ())

    @patch("quant.shared.db.psycopg.connect")
    def test_raises_on_none_row(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        gw = DbGateway("postgresql://test")
        with pytest.raises(RuntimeError, match="invalid OUT shape"):
            gw._call_write("CALL x", ())


class TestQuery:
    @patch("quant.shared.db.psycopg.connect")
    def test_returns_list_of_dicts(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [MagicMock(name="a"), MagicMock(name="b")]
        mock_cur.description[0].name = "a"
        mock_cur.description[1].name = "b"
        mock_cur.fetchall.return_value = [(1, "x"), (2, "y")]

        gw = DbGateway("postgresql://test")
        rows = gw._query("SELECT a, b FROM t")
        assert rows == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        mock_cur.execute.assert_called_once_with("SELECT a, b FROM t", ())

    @patch("quant.shared.db.psycopg.connect")
    def test_empty_result(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = None
        mock_cur.fetchall.return_value = []

        gw = DbGateway("postgresql://test")
        assert gw._query("SELECT 1 WHERE FALSE") == []


class TestHealthCheck:
    @patch("quant.shared.db.psycopg.connect")
    def test_ok_returns_none(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        gw = DbGateway("postgresql://test")
        assert gw.health_check() is None
        mock_conn.execute.assert_called_once_with("SELECT 1")

    @patch("quant.shared.db.psycopg.connect", side_effect=RuntimeError("boom"))
    def test_propagates_error(self, _mock_connect):
        gw = DbGateway("postgresql://test")
        with pytest.raises(RuntimeError, match="boom"):
            gw.health_check()
