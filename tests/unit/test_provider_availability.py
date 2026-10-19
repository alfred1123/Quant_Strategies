"""The Data tab lists provider subscriptions joined on PROVIDER_SUBSCR_ID."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quant.market_data.series_subscr import SeriesSubscrRepo
from tests.unit.liquibase_sources import call_arg_count, procedure_param_count

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "db" / "liquidbase" / "market_data" / "procedures" / "SP_GET_SERIES_SUBSCR.sql"
MOVE = ROOT / "db" / "liquidbase" / "market_data" / "tables" / "PROVIDER_SUBSCR_ALL_SOURCES.sql"
INS = ROOT / "db" / "liquidbase" / "market_data" / "procedures" / "SP_INS_SERIES_SUBSCR.sql"
TABLE = ROOT / "db" / "liquidbase" / "market_data" / "tables" / "PROVIDER_SUBSCR.sql"
WINDOW = ROOT / "db" / "liquidbase" / "bt" / "tables" / "API_REQUEST_PROVIDER_SUBSCR.sql"
CUSIP = "btcusdt.crypto"
METRIC = 12
INTERVAL = 1


def test_sp_get_series_subscr_calls_the_procedure():
    repo = SeriesSubscrRepo.__new__(SeriesSubscrRepo)
    repo._call_get = MagicMock(return_value=[{"internal_cusip": "btcusdt.crypto"}])

    rows = repo.sp_get_series_subscr()

    repo._call_get.assert_called_once_with(
        "CALL market_data.sp_get_series_subscr("
        "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
        (),
    )
    assert rows == [{"internal_cusip": "btcusdt.crypto"}]


def test_the_list_joins_on_the_subscription_id():
    text = PROC.read_text()
    assert "LEFT JOIN MARKET_DATA.API_REQUEST r" in text
    assert "ON r.SERIES_SUBSCR_ID = s.SERIES_SUBSCR_ID" in text
    assert "r.INTERNAL_CUSIP" not in text
    assert "r.APP_METRIC_ID" not in text


def test_provider_subscr_indexes_the_id():
    table = TABLE.read_text()
    window = WINDOW.read_text()
    assert "UQ_PROVIDER_SUBSCR_ID_OPEN" in table
    assert "UQ_PROVIDER_SUBSCR_OPEN" in table
    assert "PRIMARY KEY (PROVIDER_SUBSCR_ID, PROVIDER_SUBSCR_VID)" in table
    assert "UQ_API_REQUEST_SUBSCR_OPEN" in window
    assert "ALTER TABLE BT.API_REQUEST SET SCHEMA MARKET_DATA" in window
    assert "ADD COLUMN PROVIDER_SUBSCR_ID UUID" in window
    assert "ON MARKET_DATA.API_REQUEST (PROVIDER_SUBSCR_ID)" in window


def _ins_kwargs(**overrides):
    base = {
        "series_subscr_id": uuid.uuid4(),
        "internal_cusip": CUSIP,
        "app_id": 7,
        "app_metric_id": METRIC,
        "tm_interval_id": INTERVAL,
        "is_enabled_ind": "Y",
    }
    base.update(overrides)
    return base


def test_sp_ins_series_subscr_calls_the_procedure():
    kept = uuid.uuid4()
    repo = SeriesSubscrRepo.__new__(SeriesSubscrRepo)
    repo.user_id = "tester"
    repo._call_write = MagicMock(return_value=())
    repo._call_get = MagicMock(return_value=[{
        "series_subscr_id": kept,
        "internal_cusip": CUSIP,
        "app_id": 7,
        "app_metric_id": METRIC,
        "tm_interval_id": INTERVAL,
    }])

    row = repo.sp_ins_series_subscr(**_ins_kwargs(series_subscr_id=kept))

    sql = repo._call_write.call_args.args[0]
    assert call_arg_count(sql) == procedure_param_count(
        "market_data", "SP_INS_SERIES_SUBSCR.sql"
    )
    params = repo._call_write.call_args.args[1]
    assert params[-1] == "tester"
    assert row["series_subscr_id"] == kept


def test_the_write_versions_the_id():
    text = INS.read_text()
    assert "WHERE SERIES_SUBSCR_ID = IN_SERIES_SUBSCR_ID" in text
    assert "IS NOT DISTINCT FROM" not in text


def test_every_source_lives_in_provider_subscr():
    text = MOVE.read_text()
    active = (
        ROOT / "db" / "liquidbase" / "market_data" / "procedures"
        / "SP_GET_ACTIVE_BAR_SUBSCRIPTIONS.sql"
    ).read_text()
    assert "DROP INDEX MARKET_DATA.UQ_PROVIDER_SUBSCR_OPEN" in text
    assert "CREATE UNIQUE INDEX UQ_PROVIDER_SUBSCR_OPEN" not in text
    assert "FROM MARKET_DATA.BAR_SUBSCRIPTION" in text
    assert "DROP TABLE MARKET_DATA.BAR_SUBSCRIPTION" in text
    assert "RENAME TO SERIES_SUBSCR" in text
    assert "RENAME COLUMN PROVIDER_SUBSCR_ID TO SERIES_SUBSCR_ID" in text
    assert "FROM MARKET_DATA.SERIES_SUBSCR s" in active
    assert "s.APP_METRIC_ID IS NULL" in active


def test_the_write_reads_back_the_id():
    minted = uuid.uuid4()
    other = uuid.uuid4()
    repo = SeriesSubscrRepo.__new__(SeriesSubscrRepo)
    repo.user_id = "tester"
    repo._call_write = MagicMock(return_value=())
    repo._call_get = MagicMock(return_value=[
        {
            "series_subscr_id": other,
            "internal_cusip": CUSIP,
            "app_id": 7,
            "app_metric_id": METRIC,
            "tm_interval_id": INTERVAL,
        },
        {
            "series_subscr_id": minted,
            "internal_cusip": CUSIP,
            "app_id": 7,
            "app_metric_id": METRIC,
            "tm_interval_id": INTERVAL,
            "is_enabled_ind": "N",
        },
    ])

    row = repo.sp_ins_series_subscr(**_ins_kwargs(
        series_subscr_id=minted, is_enabled_ind="N"
    ))

    assert row["series_subscr_id"] == minted


@pytest.mark.parametrize(
    "field",
    ["series_subscr_id", "internal_cusip", "app_id", "tm_interval_id"],
)
def test_key_fields_are_required(field):
    repo = SeriesSubscrRepo.__new__(SeriesSubscrRepo)
    repo.user_id = "tester"
    with pytest.raises(ValueError, match=field):
        repo.sp_ins_series_subscr(**_ins_kwargs(**{field: None}))


def test_enabled_flag_must_be_y_or_n():
    repo = SeriesSubscrRepo.__new__(SeriesSubscrRepo)
    repo.user_id = "tester"
    with pytest.raises(ValueError, match="is_enabled_ind"):
        repo.sp_ins_series_subscr(**_ins_kwargs(is_enabled_ind="true"))


@patch.object(SeriesSubscrRepo, "_call_get", return_value=[])
@patch.object(SeriesSubscrRepo, "_call_write", return_value=())
def test_a_write_that_reads_back_nothing_is_a_bug(_write, _get):
    repo = SeriesSubscrRepo.__new__(SeriesSubscrRepo)
    repo.user_id = "tester"
    with pytest.raises(RuntimeError, match="returned no row"):
        repo.sp_ins_series_subscr(**_ins_kwargs(
            backfill_from_ts=datetime(2020, 1, 1, tzinfo=UTC)
        ))
