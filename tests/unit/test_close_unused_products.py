"""The close seed uses SP_UPD_PRODUCT_IS_CURRENT."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "db" / "liquidbase" / "inst" / "data" / "CLOSE_UNUSED_PRODUCTS.sql"
PROC = ROOT / "db" / "liquidbase" / "inst" / "procedures" / "SP_UPD_PRODUCT_IS_CURRENT.sql"

KEPT = ("btcusdt.crypto", "ethusdt.crypto", "bnbusdt.crypto")


def test_seed_keeps_the_traded_pairs_and_calls_the_procedure():
    text = SEED.read_text()
    for cusip in KEPT:
        assert f"'{cusip}'" in text
    assert "UPDATE INST.PRODUCT" not in text
    assert "DELETE FROM" not in text.upper()
    call = re.search(
        r"CALL INST\.SP_UPD_PRODUCT_IS_CURRENT\((.*?)\);",
        text,
        re.S,
    )
    assert call, "seed does not call SP_UPD_PRODUCT_IS_CURRENT"
    args = [part.strip() for part in call.group(1).split(",") if part.strip()]
    assert args == [
        "R.INTERNAL_CUSIP",
        "'liquibase'",
        "V_SQLSTATE",
        "V_SQLMSG",
        "V_SQLERRMC",
    ]


def test_procedure_closes_the_current_row_and_its_xrefs():
    text = PROC.read_text()
    assert "CREATE OR REPLACE PROCEDURE INST.SP_UPD_PRODUCT_IS_CURRENT(" in text
    assert "SET IS_CURRENT_IND = 'N'" in text
    assert "SET TRANSACT_TO_TS = V_START_TS" in text
    assert "INSERT INTO INST.PRODUCT" not in text
    assert "clock_timestamp()" in text
    assert "V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP" in text
