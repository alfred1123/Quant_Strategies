"""Convention checks on how stored procedures time themselves.

Every ``LOG_PROC_DETAIL.DURATION`` written before 2026-08-11 was exactly 0 —
109,985 rows of it. The procedures captured a start with ``CURRENT_TIMESTAMP``
and ``CORE_INS_LOG_PROC`` filled the end in the same way, but in Postgres that
is the *transaction* start: it is fixed for the life of the transaction, so the
subtraction could only ever yield zero. ``statement_timestamp()`` is no better
here, because a ``CALL`` is one top-level statement and the whole body runs
inside it. ``clock_timestamp()`` is the only one that re-reads the clock.

The trap is easy to fall back into, since a new procedure is usually copied
from an existing one, and a zero duration looks like a fast procedure rather
than a broken measurement. Hence these checks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.unit.liquibase_sources import LB_ROOT, is_frozen

LOGGER_SQL = LB_ROOT / "core_admin" / "procedures" / "CORE_INS_LOG_PROC.sql"

CALL_RE = re.compile(r"CORE_ADMIN\.CORE_INS_LOG_PROC\s*\((.*?)\);", re.S)
DECL_RE = re.compile(
    r"^[ \t]*V_LOG_START\s+TIMESTAMPTZ\s*:=\s*clock_timestamp\(\);", re.M
)


def _callers() -> list[Path]:
    """Procedure and function bodies that write an audit log entry.

    Detected by an actual ``CALL``, not by the name appearing anywhere in the
    file: a table DDL whose comment explains *where* its audit trail is written
    mentions the procedure without invoking it, and matching prose would demand
    a ``V_LOG_START`` of a file that has no body to put one in.

    Frozen files are excluded: they are superseded bodies that no deploy
    re-applies, so retrofitting the timing fix into them would change nothing
    in the database while breaking the checksum of the archived changeset that
    still points at them.
    """
    return sorted(
        p
        for p in LB_ROOT.rglob("*.sql")
        if p != LOGGER_SQL
        and CALL_RE.search(p.read_text())
        and not is_frozen(p)
    )


CALLERS = _callers()


def _name(path: Path) -> str:
    return str(path.relative_to(LB_ROOT))


def test_callers_were_discovered():
    """Guard against the glob silently finding nothing."""
    assert CALLERS, "no procedures calling CORE_INS_LOG_PROC — is the walk broken?"


@pytest.mark.parametrize("path", CALLERS, ids=_name)
def test_caller_declares_a_wall_clock_start(path):
    assert DECL_RE.search(path.read_text()), (
        f"{_name(path)}: a procedure that logs needs "
        "V_LOG_START TIMESTAMPTZ := clock_timestamp(); CURRENT_TIMESTAMP is the "
        "transaction start and would record a duration of 0"
    )


@pytest.mark.parametrize("path", CALLERS, ids=_name)
def test_log_call_passes_the_wall_clock_start(path):
    """The third argument is the start instant the duration is measured from.

    ``V_START_TS`` is still legitimate elsewhere — it stamps TRANSACT_FROM_TS /
    TRANSACT_TO_TS, where every row in a transaction *should* share one instant.
    It just cannot be the thing a duration is measured from.
    """
    for args in CALL_RE.findall(path.read_text()):
        start = [a.strip() for a in args.split(",")][2]
        assert start == "V_LOG_START", (
            f"{_name(path)}: log call measures from {start!r}; it must be "
            "V_LOG_START so the duration is wall-clock"
        )


def test_logger_closes_the_interval_with_wall_clock():
    """CORE_INS_LOG_PROC supplies the end instant when the caller passes NULL."""
    body = LOGGER_SQL.read_text()
    fallback = re.search(r"IF\s+IN_END_AT\s+IS\s+NULL\s+THEN\s*(.+?);", body, re.S)
    assert fallback, "CORE_INS_LOG_PROC no longer defaults a NULL end instant"
    assert "clock_timestamp()" in fallback.group(1), (
        "CORE_INS_LOG_PROC must close the interval with clock_timestamp(); "
        f"found: {fallback.group(1).strip()!r}"
    )
