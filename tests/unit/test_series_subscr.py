"""Provider subscribe reuses the open series instead of minting a second id."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from quant.market_data.series_subscr import SeriesSubscrRepo

CUSIP = "btcusdt.crypto"
OPEN = uuid4()


def _row(**overrides):
    base = {
        "series_subscr_id": str(OPEN),
        "series_subscr_vid": 1,
        "app_id": 2,
        "app_metric_id": 11,
        "tm_interval_id": 1,
        "internal_cusip": CUSIP,
        "is_enabled_ind": "Y",
        "backfill_from_ts": None,
        "transact_from_ts": datetime(2026, 10, 1, tzinfo=UTC),
        "range_start_ts": None,
        "range_end_ts": None,
        "has_payload_ind": None,
    }
    base.update(overrides)
    return base


def test_second_subscribe_versions_the_open_row():
    repo = SeriesSubscrRepo("postgresql://test", user_id="alice")
    with (
        patch.object(repo, "_call_get", return_value=[_row()]),
        patch.object(repo, "_call_write") as write,
    ):
        got = repo.subscribe(
            internal_cusip=CUSIP,
            app_id=2,
            app_metric_id=11,
            tm_interval_id=1,
            is_enabled_ind="Y",
        )

    assert got["series_subscr_id"] == str(OPEN)
    sent = write.call_args.args[1]
    assert UUID(sent[0]) == OPEN


def test_a_new_series_is_a_new_id():
    repo = SeriesSubscrRepo("postgresql://test", user_id="alice")
    created: dict[str, str] = {}

    def write(_sql, params):
        created["id"] = params[0]

    def get(_sql, _params):
        if "id" not in created:
            return []
        return [_row(series_subscr_id=created["id"])]

    with (
        patch.object(repo, "_call_get", side_effect=get),
        patch.object(repo, "_call_write", side_effect=write),
    ):
        got = repo.subscribe(
            internal_cusip=CUSIP,
            app_id=2,
            app_metric_id=11,
            tm_interval_id=1,
            is_enabled_ind="Y",
        )

    assert UUID(created["id"]) != OPEN
    assert got["series_subscr_id"] == created["id"]
