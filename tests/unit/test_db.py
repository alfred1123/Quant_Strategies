"""Unit tests for ``DbGateway`` helpers and the process pool."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from quant.shared.db import (
    ConnectionPool,
    DbGateway,
    ProcedureError,
    _pool_kwargs,
    _redact,
    close_pools,
    open_pool,
    pool_for,
)

_CIPHERTEXT = "gAAAAABqkYSOK9y-7-avVAadofsaAWhCOziTPCcZxFE5u1bq5LnAWYuZ"


@pytest.fixture(autouse=True)
def _reset_pools():
    yield
    close_pools()


@pytest.fixture
def gateway():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    with patch("quant.shared.db.pool_for", return_value=mock_pool):
        yield DbGateway("postgresql://test"), mock_conn, mock_cur, mock_pool


class TestRedact:
    def test_replaces_a_fernet_token_with_its_length(self):
        assert _redact((_CIPHERTEXT,)) == (f"<encrypted:{len(_CIPHERTEXT)} chars>",)

    def test_keeps_ordinary_params_readable(self):
        params = ("btcusdt.crypto", 34, None, 0.001)
        assert _redact(params) == params

    def test_redacts_only_the_encrypted_positions(self):
        params = ("user-1", _CIPHERTEXT, 34, _CIPHERTEXT, "label")
        got = _redact(params)
        assert got[0] == "user-1" and got[2] == 34 and got[4] == "label"
        assert _CIPHERTEXT not in got

    def test_matches_on_format_not_position(self):
        assert _redact((1, 2, _CIPHERTEXT))[2].startswith("<encrypted:")

    def test_leaves_a_string_that_merely_starts_similarly(self):
        assert _redact(("gAAAA",)) == ("gAAAA",)

    def test_truncates_a_bulk_payload(self):
        payload = "x" * 5000
        (got,) = _redact((payload,))
        assert len(got) < 300
        assert got.startswith("xxx")
        assert "5000 chars total" in got

    def test_keeps_a_short_string_verbatim(self):
        assert _redact(("btcusdt.crypto",)) == ("btcusdt.crypto",)


class TestWriteLoggingRedaction:
    def test_commit_log_carries_no_ciphertext(self, gateway, caplog):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("00000", "", "")
        with caplog.at_level(logging.INFO, logger="quant.shared.db"):
            gw._call_write("CALL core_admin.sp_ins_api_credential(%s)", (_CIPHERTEXT,))
        assert _CIPHERTEXT not in caplog.text
        assert "<encrypted:" in caplog.text

    def test_failure_log_carries_no_ciphertext(self, gateway, caplog):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("23505", "msg", "detail")
        with caplog.at_level(logging.ERROR, logger="quant.shared.db"):
            with pytest.raises(ProcedureError):
                gw._call_write("CALL x(%s)", (_CIPHERTEXT,))
        assert _CIPHERTEXT not in caplog.text

    def test_the_real_parameters_still_reach_the_database(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("00000", "", "")
        gw._call_write("CALL x(%s)", (_CIPHERTEXT,))
        mock_cur.execute.assert_called_once_with("CALL x(%s)", (_CIPHERTEXT,))


class TestCallWrite:
    def test_status_only_returns_empty_tail(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("00000", "", "")
        assert gw._call_write("CALL x", ()) == ()
        mock_cur.execute.assert_called_once_with("CALL x", ())

    def test_extra_outs_after_triplet(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("00000", "", "", 42, "extra")
        assert gw._call_write("CALL x", ()) == (42, "extra")

    def test_raises_on_sqlstate(self, gateway):
        gw, mock_conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("23505", "msg", "detail")
        with pytest.raises(ProcedureError) as exc_info:
            gw._call_write("CALL x(%s)", ())
        assert exc_info.value.sqlstate == "23505"
        assert exc_info.value.message == "detail"
        assert exc_info.value.proc == "x"
        mock_conn.commit.assert_not_called()

    def test_raises_on_short_row(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = ("00000", "")
        with pytest.raises(RuntimeError, match="invalid OUT shape"):
            gw._call_write("CALL x", ())

    def test_raises_on_none_row(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.fetchone.return_value = None
        with pytest.raises(RuntimeError, match="invalid OUT shape"):
            gw._call_write("CALL x", ())


class TestQuery:
    def test_returns_list_of_dicts(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.description = [MagicMock(name="a"), MagicMock(name="b")]
        mock_cur.description[0].name = "a"
        mock_cur.description[1].name = "b"
        mock_cur.fetchall.return_value = [(1, "x"), (2, "y")]
        assert gw._query("SELECT a, b FROM t") == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        mock_cur.execute.assert_called_once_with("SELECT a, b FROM t", ())

    def test_empty_result(self, gateway):
        gw, _conn, mock_cur, _pool = gateway
        mock_cur.description = None
        mock_cur.fetchall.return_value = []
        assert gw._query("SELECT 1 WHERE FALSE") == []


class TestHealthCheck:
    def test_ok_returns_none(self, gateway):
        gw, mock_conn, _cur, mock_pool = gateway
        assert gw.health_check() is None
        mock_pool.connection.assert_called_once_with(timeout=3)
        mock_conn.execute.assert_called_once_with("SELECT 1")

    def test_propagates_error(self):
        mock_pool = MagicMock()
        mock_pool.connection.side_effect = RuntimeError("boom")
        with patch("quant.shared.db.pool_for", return_value=mock_pool):
            with pytest.raises(RuntimeError, match="boom"):
                DbGateway("postgresql://test").health_check()


class TestProcessPool:
    def test_reuses_one_pool_per_conninfo(self):
        held = MagicMock(closed=False)
        with patch("quant.shared.db.ConnectionPool", return_value=held) as ctor:
            assert pool_for("postgresql://a") is held
            assert pool_for("postgresql://a") is held
            ctor.assert_called_once()

    def test_distinct_conninfo_gets_its_own_pool(self):
        pools = [MagicMock(closed=False), MagicMock(closed=False)]
        with patch("quant.shared.db.ConnectionPool", side_effect=pools):
            assert pool_for("postgresql://a") is pools[0]
            assert pool_for("postgresql://b") is pools[1]

    def test_close_pools_forgets_so_the_next_call_opens_fresh(self):
        first = MagicMock(closed=False)
        with patch("quant.shared.db.ConnectionPool", return_value=first):
            pool_for("postgresql://a")
        close_pools()
        first.close.assert_called_once()
        second = MagicMock(closed=False)
        with patch("quant.shared.db.ConnectionPool", return_value=second):
            assert pool_for("postgresql://a") is second

    def test_open_pool_waits_until_ready(self):
        held = MagicMock(closed=False)
        with patch("quant.shared.db.ConnectionPool", return_value=held):
            assert open_pool("postgresql://a", timeout=5) is held
        held.wait.assert_called_once_with(timeout=5)

    def test_pool_checks_stale_connections_on_checkout(self):
        kwargs = _pool_kwargs()
        assert kwargs["check"] is ConnectionPool.check_connection
        assert kwargs["min_size"] == 2
        assert kwargs["max_size"] == 10
        assert kwargs["max_lifetime"] == 1800.0

    def test_inverted_sizes_are_refused(self, monkeypatch):
        monkeypatch.setenv("DB_POOL_MIN", "8")
        monkeypatch.setenv("DB_POOL_MAX", "2")
        with pytest.raises(ValueError, match="DB_POOL_MAX"):
            _pool_kwargs()

    def test_run_returns_the_connection_to_the_pool(self, gateway):
        gw, _conn, mock_cur, mock_pool = gateway
        mock_cur.fetchone.return_value = ("00000", "", "")
        gw._call_write("CALL x", ())
        mock_pool.connection.return_value.__exit__.assert_called()
