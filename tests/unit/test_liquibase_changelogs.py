"""Convention checks on the Liquibase changelogs.

``liquibase validate`` already rejects the structural failures — malformed XML,
an ``<include>`` or ``<sqlFile>`` that does not resolve, duplicate changeset
identifiers — and ``scripts/liquibase-verify.sh --offline`` runs it. What it has
no opinion on is convention: the policy engine (``liquibase checks``) is a Pro
feature, so the rules below are the ones a deploy would happily apply and then
regret.

Only changesets reachable from a ``*-changelog.xml`` via ``<include>`` are
checked. ``releases/archive/`` holds baselines that prod never includes, and a
release drops out of the include list once it has been applied everywhere.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

LB_ROOT = Path(__file__).resolve().parents[2] / "db" / "liquidbase"
NS = {"lb": "http://www.liquibase.org/xml/ns/dbchangelog"}


def _changelogs() -> list[Path]:
    """Master changelog plus one per schema directory."""
    return sorted(LB_ROOT.glob("*-changelog.xml")) + sorted(
        LB_ROOT.glob("*/*-changelog.xml")
    )


def _active_releases() -> list[Path]:
    """Release files a deploy would actually apply, found by walking <include>."""
    seen: set[Path] = set()
    queue = _changelogs()
    while queue:
        current = queue.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        for node in ET.parse(current).getroot().findall("lb:include", NS):
            rel = node.get("file")
            if rel:
                queue.append((current.parent / rel).resolve())
    return sorted(p for p in seen if p.parent.name == "releases")


def _changesets(path: Path) -> list[ET.Element]:
    return ET.parse(path).getroot().findall("lb:changeSet", NS)


def _contexts(changeset: ET.Element) -> set[str]:
    # contextFilter is the 4.24+ spelling; both are accepted on a changeSet.
    raw = changeset.get("context") or changeset.get("contextFilter") or ""
    return {c.strip() for c in raw.split(",") if c.strip()}


ACTIVE_RELEASES = _active_releases()


def _name(path: Path) -> str:
    return str(path.relative_to(LB_ROOT))


def test_active_releases_were_discovered():
    """Guard against the include walk silently finding nothing."""
    assert ACTIVE_RELEASES, "no active release files found — is the walk broken?"


@pytest.mark.parametrize("path", ACTIVE_RELEASES, ids=_name)
def test_every_changeset_declares_a_context(path):
    """A changeset with no context runs under *every* --context-filter.

    The deploy workflow passes --context-filter=prod-deploy so that untagged
    work stays manual. Omitting the attribute does not keep a changeset out of
    that run — it opts it into every one.
    """
    untagged = [cs.get("id") for cs in _changesets(path) if not _contexts(cs)]
    assert not untagged, (
        f"{_name(path)}: changesets without a context are applied by every "
        f"--context-filter, including the automated prod deploy: {untagged}"
    )


@pytest.mark.parametrize("path", ACTIVE_RELEASES, ids=_name)
def test_prod_deploy_is_never_the_only_context(path):
    """prod-deploy is additive and never replaces the schema context.

    Contexts are OR-matched, so dropping the schema name hides the changeset
    from anyone migrating a single schema with its own filter.
    """
    bare = [
        cs.get("id") for cs in _changesets(path) if _contexts(cs) == {"prod-deploy"}
    ]
    assert not bare, (
        f"{_name(path)}: tagged prod-deploy but missing a schema context: {bare}"
    )


def _sql_managed_by_active_releases() -> set[Path]:
    """Procedure/function files an active runOnChange changeset would re-apply."""
    managed: set[Path] = set()
    for release in ACTIVE_RELEASES:
        for changeset in _changesets(release):
            if changeset.get("runOnChange") != "true":
                continue
            for node in changeset.findall("lb:sqlFile", NS):
                rel = node.get("path") or ""
                if "/procedures/" in rel or "/functions/" in rel:
                    managed.add((release.parent / rel).resolve())
    return managed


ALL_PROC_SQL = sorted(LB_ROOT.glob("*/procedures/*.sql")) + sorted(
    LB_ROOT.glob("*/functions/*.sql")
)


@pytest.mark.parametrize("path", ALL_PROC_SQL, ids=_name)
def test_every_procedure_is_still_managed_by_an_active_release(path):
    """Editing a procedure must be enough to redeploy it.

    Whether a procedure is reachable is an emergent property of which releases
    happen to still be included, so archiving an applied release can silently
    orphan one. The failure is invisible — the edit lands in git, the deploy
    goes green, and prod keeps the old body. Archiving every applied release
    would have done exactly this to SP_INS_LOG_PROC_SUMMARY, which is why
    core_admin 1.4.0 is still included.
    """
    assert path.resolve() in _sql_managed_by_active_releases(), (
        f"{_name(path)}: no active release re-applies this file. Add a "
        "runOnChange changeset for it, or keep the release that had one "
        "in the changelog."
    )


ARCHIVED = sorted(LB_ROOT.glob("*/releases/archive/*.xml")) + sorted(
    LB_ROOT.glob("releases/archive/*.xml")
)


@pytest.mark.parametrize("path", ARCHIVED, ids=_name)
def test_archive_holds_no_run_always_changeset(path):
    """runAlways means "every deploy", so archiving it silently stops the work.

    ``1.3.0-grants-refresh`` is the case that matters: it re-applies GRANTS.sql
    on the second core_admin pass, which is what gives quant_app EXECUTE on
    routines created earlier in the same deploy. Archived, new procedures would
    be created without grants and the app would get "permission denied" at
    runtime — long after the deploy went green. Baselines are exempt: prod
    never includes them.
    """
    if path.name.startswith("baseline-"):
        pytest.skip("baselines are reference-only and never included")
    offenders = [
        cs.get("id") for cs in _changesets(path) if cs.get("runAlways") == "true"
    ]
    assert not offenders, (
        f"{_name(path)}: runAlways changesets must stay in the active changelog, "
        f"they do work on every deploy: {offenders}"
    )


@pytest.mark.parametrize("path", ACTIVE_RELEASES, ids=_name)
def test_procedures_are_not_split_on_semicolons(path):
    """splitStatements chops a procedure body apart inside its $$ quotes."""
    offenders = [
        cs.get("id")
        for cs in _changesets(path)
        for node in cs.findall("lb:sqlFile", NS)
        if "/procedures/" in (node.get("path") or "")
        and node.get("splitStatements") != "false"
    ]
    assert not offenders, (
        f'{_name(path)}: procedure changesets need splitStatements="false": '
        f"{offenders}"
    )
