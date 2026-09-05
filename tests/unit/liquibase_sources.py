"""Shared facts about the Liquibase SQL tree, for the test modules that walk it.

Lives here rather than in either test module because both the changelog checks
and the timing checks need to agree on which files are frozen; two copies of
that predicate would eventually disagree.
"""

from __future__ import annotations

import re
from pathlib import Path

LB_ROOT = Path(__file__).resolve().parents[2] / "db" / "liquidbase"

FROZEN_MARKER = "FROZEN at release"

_SIGNATURE_RE = re.compile(
    r"CREATE OR REPLACE PROCEDURE\s+[\w.]+\s*\((.*?)\)\s*LANGUAGE", re.S | re.I
)
_PARAM_RE = re.compile(r"\s*(IN|OUT)\s+\w+")


def procedure_param_count(schema: str, proc_file: str) -> int:
    """How many IN/OUT parameters a procedure's DDL declares.

    Paired with :func:`call_arg_count` to pin a Python ``CALL`` string to the
    procedure it targets. Postgres treats a changed parameter list as a *new
    overload* rather than an error, so a stale CALL keeps resolving to the old
    signature and the mismatch surfaces as missing data instead of a failure —
    which is why the count is asserted rather than trusted.
    """
    path = LB_ROOT / schema / "procedures" / proc_file
    signature = _SIGNATURE_RE.search(path.read_text())
    assert signature, f"could not parse a signature out of {schema}/{proc_file}"
    return len(
        [ln for ln in signature.group(1).splitlines() if _PARAM_RE.match(ln)]
    )


def call_arg_count(sql: str) -> int:
    """How many arguments a Python ``CALL`` string supplies.

    ``%s`` for the values psycopg binds, plus the ``NULL::`` placeholders that
    stand in for OUT columns.
    """
    return sql.count("%s") + sql.count("NULL::")


def is_frozen(path: Path) -> bool:
    """True for a SQL file kept only as the historical body behind a release.

    A frozen file is no longer the live definition of its routine — a later
    release supersedes it under the same name. ``BT.SP_INS_STRATEGY`` is the
    example: ``SP_INS_STRATEGY.sql`` is pinned at 1.6.0 with four OUT
    parameters, while the routine prod actually runs comes from
    ``SP_INS_STRATEGY_VID_BY_NM.sql`` and has five.

    Such a file must not be edited or re-applied. A procedure's OUT list *is*
    its return type, so ``CREATE OR REPLACE`` cannot change it in place — a
    deploy that re-runs the frozen body aborts with "cannot change return type
    of existing function", which is how the 2026-08-16 deploy failed.
    """
    return FROZEN_MARKER in path.read_text()
