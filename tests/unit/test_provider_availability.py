"""The Data tab lists provider subscriptions joined on PROVIDER_SUBSCR_ID."""

from pathlib import Path
from unittest.mock import MagicMock

from quant.market_data.provider_subscr import ProviderSubscrRepo

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "db" / "liquidbase" / "market_data" / "procedures" / "SP_GET_PROVIDER_SUBSCR.sql"
TABLE = ROOT / "db" / "liquidbase" / "market_data" / "tables" / "PROVIDER_SUBSCR.sql"
WINDOW = ROOT / "db" / "liquidbase" / "bt" / "tables" / "API_REQUEST_PROVIDER_SUBSCR.sql"


def test_list_current_calls_the_subscription_procedure():
    repo = ProviderSubscrRepo.__new__(ProviderSubscrRepo)
    repo._call_get = MagicMock(return_value=[{"internal_cusip": "btcusdt.crypto"}])

    rows = repo.list_current()

    repo._call_get.assert_called_once_with(
        "CALL market_data.sp_get_provider_subscr("
        "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
        (),
    )
    assert rows == [{"internal_cusip": "btcusdt.crypto"}]


def test_the_list_joins_on_the_subscription_id():
    text = PROC.read_text()
    assert "ON r.PROVIDER_SUBSCR_ID = s.PROVIDER_SUBSCR_ID" in text
    assert "r.INTERNAL_CUSIP" not in text
    assert "r.APP_METRIC_ID" not in text


def test_provider_subscr_indexes_the_id():
    table = TABLE.read_text()
    window = WINDOW.read_text()
    assert "UQ_PROVIDER_SUBSCR_ID_OPEN" in table
    assert "UQ_PROVIDER_SUBSCR_OPEN" in table
    assert "PRIMARY KEY (PROVIDER_SUBSCR_ID, PROVIDER_SUBSCR_VID)" in table
    assert "UQ_API_REQUEST_SUBSCR_OPEN" in window
    assert "ADD COLUMN PROVIDER_SUBSCR_ID UUID" in window
