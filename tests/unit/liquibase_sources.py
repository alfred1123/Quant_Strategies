"""Shared facts about the Liquibase SQL tree, for the test modules that walk it.

Lives here rather than in either test module because both the changelog checks
and the timing checks need to agree on which files are frozen; two copies of
that predicate would eventually disagree.
"""

from __future__ import annotations

from pathlib import Path

LB_ROOT = Path(__file__).resolve().parents[2] / "db" / "liquidbase"

FROZEN_MARKER = "FROZEN at release"


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
