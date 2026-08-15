"""Integration test for the MARKET_DATA price bar stored procedures.

Exercises ``SP_INS_PRICE_BAR`` / ``SP_GET_PRICE_BAR_COVERAGE`` /
``SP_GET_PRICE_BAR`` against a real PostgreSQL instance.

Unit tests assert the CALL argument count matches the DDL on disk, which
catches a stale signature but not a *deployed* one: Postgres resolves a
changed parameter list to a different overload rather than failing, so only a
real call proves the repo is talking to the procedure it thinks it is.

Skipped automatically when QUANTDB_URL is not set or the DB is unreachable
(e.g. CI without a database).
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

psycopg = pytest.importorskip("psycopg")

from quant.market_data.repo import PriceBarRepo  # noqa: E402
from quant.market_data.service import PriceBarService  # noqa: E402
from quant.shared.db import ProcedureError  # noqa: E402


def _resolve_db_url() -> str | None:
    url = os.environ.get("QUANTDB_URL")
    if not url:
        return None
    try:
        with psycopg.connect(url, connect_timeout=2) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:
        return None
    return url


DB_URL = _resolve_db_url()

INTERVAL_1H = 2
APP_ID = 1  # yahoo — must already exist in REFDATA.APP
BAR_HOURS = (9, 10, 11)


def _ts(hour: int) -> datetime:
    return datetime(2026, 8, 1, hour, 0, tzinfo=UTC)


class FakeRefData:
    """read_bars needs no REFDATA; this only satisfies the constructor."""

    def get_interval_period(self, tm_interval_id):
        return timedelta(hours=1)


@pytest.fixture
def cusip():
    """A throwaway instrument key, hard-deleted afterwards (test data only)."""
    key = f"itest_{uuid.uuid4().hex[:8]}.x"
    yield key
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM MARKET_DATA.PRICE_BAR WHERE INTERNAL_CUSIP = %s", (key,)
        )
        conn.commit()


@pytest.fixture
def repo():
    instance = PriceBarRepo(DB_URL, user_id="pytest")
    yield instance
    instance.close()


def _seed(repo, cusip, hours=BAR_HOURS, source_app_id=APP_ID, px_offset=0):
    for hour in hours:
        repo.ins_bar(
            internal_cusip=cusip,
            tm_interval_id=INTERVAL_1H,
            source_app_id=source_app_id,
            bar_timestamp=_ts(hour),
            open_px=Decimal("100") + hour + px_offset,
            high_px=Decimal("110") + hour + px_offset,
            low_px=Decimal("95") + hour + px_offset,
            close_px=Decimal("105") + hour + px_offset,
            volume=Decimal("12.5"),
        )


@pytest.mark.skipif(DB_URL is None, reason="QUANTDB_URL not set or DB unreachable")
class TestPriceBarStoredProcedures:
    def test_coverage_is_empty_before_any_insert(self, repo, cusip):
        assert (
            repo.get_coverage(
                internal_cusip=cusip, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID
            )
            is None
        )

    def test_insert_then_coverage_reports_the_bounds(self, repo, cusip):
        _seed(repo, cusip)
        coverage = repo.get_coverage(
            internal_cusip=cusip, tm_interval_id=INTERVAL_1H, source_app_id=APP_ID
        )
        assert coverage["min_bar_timestamp"] == _ts(9)
        assert coverage["max_bar_timestamp"] == _ts(11)

    def test_range_read_returns_bars_oldest_first(self, repo, cusip):
        _seed(repo, cusip)
        rows = repo.get_bars(
            internal_cusip=cusip,
            tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID,
            range_start=_ts(9),
            range_end=_ts(11),
        )
        assert [r["bar_timestamp"] for r in rows] == [_ts(9), _ts(10), _ts(11)]
        assert rows[0]["close_px"] == Decimal("114")
        assert rows[0]["source_app_id"] == APP_ID

    def test_range_read_bounds_are_inclusive(self, repo, cusip):
        _seed(repo, cusip)
        rows = repo.get_bars(
            internal_cusip=cusip,
            tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID,
            range_start=_ts(10),
            range_end=_ts(10),
        )
        assert [r["bar_timestamp"] for r in rows] == [_ts(10)]

    def test_other_intervals_are_not_returned(self, repo, cusip):
        _seed(repo, cusip)
        rows = repo.get_bars(
            internal_cusip=cusip,
            tm_interval_id=1,
            source_app_id=APP_ID,
            range_start=_ts(9),
            range_end=_ts(11),
        )
        assert rows == []

    def test_duplicate_bar_fails_loud(self, repo, cusip):
        """The SP reports the conflict; it does not swallow it.

        Absorbing a concurrent writer is `PriceBarService`'s decision, made on
        this SQLSTATE. The repo stays honest so the service can tell a lost
        race apart from a real constraint failure.
        """
        _seed(repo, cusip, hours=(9,))
        with pytest.raises(ProcedureError) as exc:
            _seed(repo, cusip, hours=(9,))
        assert exc.value.sqlstate == "23505"

    def test_two_venues_hold_the_same_timestamp_independently(self, repo, cusip):
        """The point of the wide key: Bybit and Binance share one INTERNAL_CUSIP
        (decision #21) and quote different prices for the same bar."""
        _seed(repo, cusip, hours=(9,), source_app_id=34)
        _seed(repo, cusip, hours=(9,), source_app_id=35, px_offset=1000)

        bybit = repo.get_bars(
            internal_cusip=cusip, tm_interval_id=INTERVAL_1H, source_app_id=34,
            range_start=_ts(9), range_end=_ts(9),
        )
        binance = repo.get_bars(
            internal_cusip=cusip, tm_interval_id=INTERVAL_1H, source_app_id=35,
            range_start=_ts(9), range_end=_ts(9),
        )

        assert [r["close_px"] for r in bybit] == [Decimal("114")]
        assert [r["close_px"] for r in binance] == [Decimal("1114")]

    def test_coverage_of_one_venue_ignores_another(self, repo, cusip):
        """Otherwise the second venue reads as fresh and never fetches its own bars."""
        _seed(repo, cusip, source_app_id=34)

        assert (
            repo.get_coverage(
                internal_cusip=cusip, tm_interval_id=INTERVAL_1H, source_app_id=35
            )
            is None
        )

    def test_service_read_bars_returns_the_pipeline_shape(self, repo, cusip):
        _seed(repo, cusip)
        service = PriceBarService(repo, FakeRefData(), instruments=None, fetcher=None)
        df = service.read_bars(
            internal_cusip=cusip,
            tm_interval_id=INTERVAL_1H,
            source_app_id=APP_ID,
            start=_ts(9),
            end=_ts(11),
        )
        assert list(df.columns) == [
            "price", "factor", "Open", "High", "Low", "Close", "Volume",
        ]
        assert str(df.index.tz) == "UTC"
        assert list(df.index) == [_ts(9), _ts(10), _ts(11)]
        assert list(df["price"]) == [114.0, 115.0, 116.0]
