"""The Glassnode xref seed must call the current SP_INS_PRODUCT_XREF."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "db" / "liquidbase" / "inst" / "data" / "XREF_GLASSNODE_BTC.sql"
PROC = ROOT / "db" / "liquidbase" / "inst" / "procedures" / "SP_INS_PRODUCT_XREF.sql"


def _procedure_param_count() -> int:
    text = PROC.read_text()
    sig = re.search(
        r"CREATE OR REPLACE PROCEDURE\s+[\w.]+\s*\((.*?)\)\s*LANGUAGE",
        text,
        re.S | re.I,
    )
    assert sig, "could not parse SP_INS_PRODUCT_XREF"
    return len(
        [ln for ln in sig.group(1).splitlines() if re.match(r"\s*(IN|OUT)\s+\w+", ln)]
    )


def test_seed_calls_the_current_signature():
    text = SEED.read_text()
    assert "TRUNCATE" not in text.upper()
    assert "'btcusdt.crypto'" in text
    assert "'BTC'" in text
    call = re.search(
        r"CALL INST\.SP_INS_PRODUCT_XREF\((.*?)\);",
        text,
        re.S,
    )
    assert call, "seed does not call SP_INS_PRODUCT_XREF"
    args = [part.strip() for part in call.group(1).split(",") if part.strip()]
    assert len(args) == _procedure_param_count()
    assert args[0] == "NULL"
    assert args[3] == "'BTC'"
