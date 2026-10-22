"""Conftest snapshots of the #129 seeds stay equal to those seed files.

``SETTING_ROWS``, ``QUEUE_PRIORITY_ROWS``, and ``SCHEDULE_STATUS_ROWS`` are
what the unit tests read instead of the constants that release deleted. They
are a second copy of ``db/liquidbase/config/data/SETTING.sql`` and the two
REFDATA seeds. A change to one side and not the other is the drift this file
fails on.

No INSERT parser lives in the repo (``tests/unit/liquibase_sources.py`` reads
procedure signatures, and the seed tests match call text). The scanner below
is the same ``re`` plus a quote-aware walk those checks already need for a
description that contains a comma.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import QUEUE_PRIORITY_ROWS, SCHEDULE_STATUS_ROWS, SETTING_ROWS

ROOT = Path(__file__).resolve().parents[2]
_LIQUIBASE = ROOT / "db" / "liquidbase"

_SETTING_SQL = _LIQUIBASE / "config" / "data" / "SETTING.sql"
_QUEUE_PRIORITY_SQL = _LIQUIBASE / "refdata" / "data" / "QUEUE_PRIORITY.sql"
_SCHEDULE_STATUS_SQL = _LIQUIBASE / "refdata" / "data" / "SCHEDULE_STATUS.sql"

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+[A-Z0-9_.]+\s*\((.*?)\)\s*VALUES\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)


def _strip_sql_comments(text: str) -> str:
    """Drop ``--`` comments that sit outside a quoted string."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "'" and i + 1 < n and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            if ch == "'":
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            i += 2
            while i < n and text[i] not in "\n\r":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _unquote(text: str) -> str:
    if len(text) < 2 or text[0] != "'" or text[-1] != "'":
        raise ValueError(f"not a quoted SQL string: {text!r}")
    return text[1:-1].replace("''", "'")


def _parse_value(raw: str) -> object:
    text = raw.strip()
    if text.upper() == "NULL":
        return None
    if text.startswith("'"):
        return _unquote(text)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    if not text:
        raise ValueError("empty SQL value")
    return text


def _split_fields(tuple_body: str) -> list[object]:
    fields: list[object] = []
    buf: list[str] = []
    in_string = False
    i = 0
    n = len(tuple_body)
    while i < n:
        ch = tuple_body[i]
        if in_string:
            buf.append(ch)
            if ch == "'" and i + 1 < n and tuple_body[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            if ch == "'":
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            buf.append(ch)
            i += 1
            continue
        if ch == ",":
            fields.append(_parse_value("".join(buf)))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if in_string:
        raise ValueError("unclosed string in a seed row")
    tail = "".join(buf)
    if tail.strip() or fields:
        fields.append(_parse_value(tail))
    return fields


def _split_tuples(body: str) -> list[str]:
    tuples: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if body[i] != "(":
            raise ValueError(f"expected a row tuple, saw {body[i:i + 20]!r}")
        depth = 0
        in_string = False
        start = i
        while i < n:
            ch = body[i]
            if in_string:
                if ch == "'" and i + 1 < n and body[i + 1] == "'":
                    i += 2
                    continue
                if ch == "'":
                    in_string = False
                i += 1
                continue
            if ch == "'":
                in_string = True
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    tuples.append(body[start + 1:i])
                    i += 1
                    break
            i += 1
        else:
            raise ValueError("unclosed row tuple")
    return tuples


def parse_insert_rows(sql: str) -> list[dict[str, object]]:
    """Rows of one ``INSERT ... VALUES`` statement, comments removed.

    Quoted text keeps its commas. ``NULL`` is ``None``. An unquoted integer
    is an ``int``, which is how ``QUEUE_PRIORITY.PRIORITY`` is seeded and how
    ``QUEUE_PRIORITY_ROWS`` stores it.
    """
    text = _strip_sql_comments(sql).strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    match = _INSERT_RE.search(text)
    if match is None:
        raise ValueError("no INSERT ... VALUES statement")
    columns = [part.strip().lower() for part in match.group(1).split(",")]
    if not columns or any(not column for column in columns):
        raise ValueError("INSERT lists no columns")
    body = match.group(2).strip()
    if not body:
        raise ValueError("INSERT lists no rows")
    tuples = _split_tuples(body)
    if not tuples:
        raise ValueError("INSERT lists no rows")
    rows: list[dict[str, object]] = []
    for tup in tuples:
        values = _split_fields(tup)
        if len(values) != len(columns):
            raise ValueError(
                f"row has {len(values)} values for {len(columns)} columns"
            )
        rows.append(dict(zip(columns, values, strict=True)))
    return rows


def assert_snapshot_matches(
    snapshot: list[dict],
    seed_rows: list[dict[str, object]],
    key: str,
) -> None:
    """The columns the snapshot stores equal the same columns on the seed.

    Audit columns the snapshot does not carry (``user_id``, ``updated_at``)
    stay out of the comparison. A missing key, an extra key, or a changed
    value fails, naming the key.
    """
    assert snapshot, "snapshot is empty"
    assert seed_rows, "seed has no rows"
    keys = list(snapshot[0].keys())
    assert keys, "snapshot row has no columns"
    seed_by_key: dict[object, dict] = {}
    for row in seed_rows:
        assert key in row, f"seed row has no {key}"
        ident = row[key]
        assert ident not in seed_by_key, f"duplicate seed {key}={ident!r}"
        seed_by_key[ident] = {column: row[column] for column in keys}
    snap_by_key: dict[object, dict] = {}
    for row in snapshot:
        assert list(row.keys()) == keys, f"snapshot rows do not share columns: {row!r}"
        ident = row[key]
        assert ident not in snap_by_key, f"duplicate snapshot {key}={ident!r}"
        snap_by_key[ident] = row
    assert set(seed_by_key) == set(snap_by_key), (
        f"only in seed {sorted(set(seed_by_key) - set(snap_by_key))!r}; "
        f"only in snapshot {sorted(set(snap_by_key) - set(seed_by_key))!r}"
    )
    for ident, seed_row in seed_by_key.items():
        assert snap_by_key[ident] == seed_row, (
            f"{key}={ident!r}: snapshot {snap_by_key[ident]!r} != seed {seed_row!r}"
        )


@pytest.mark.parametrize(
    ("snapshot", "path", "key"),
    [
        (SETTING_ROWS, _SETTING_SQL, "setting_nm"),
        (QUEUE_PRIORITY_ROWS, _QUEUE_PRIORITY_SQL, "name"),
        (SCHEDULE_STATUS_ROWS, _SCHEDULE_STATUS_SQL, "name"),
    ],
    ids=["setting", "queue_priority", "schedule_status"],
)
def test_conftest_rows_match_the_seed(snapshot, path: Path, key: str) -> None:
    assert path.is_file(), path
    assert_snapshot_matches(snapshot, parse_insert_rows(path.read_text()), key)


def test_empty_sql_is_not_a_seed() -> None:
    with pytest.raises(ValueError, match="no INSERT"):
        parse_insert_rows("")


def test_insert_with_no_rows_is_rejected() -> None:
    with pytest.raises(ValueError, match="no rows"):
        parse_insert_rows("INSERT INTO CONFIG.SETTING (SETTING_NM) VALUES   ")


def test_null_value_is_none() -> None:
    rows = parse_insert_rows(
        "INSERT INTO CONFIG.SETTING (SETTING_NM, SETTING_VALUE) "
        "VALUES ('x', NULL);"
    )
    assert rows == [{"setting_nm": "x", "setting_value": None}]


def test_null_seed_value_does_not_match_a_string_snapshot() -> None:
    seed = parse_insert_rows(
        "INSERT INTO CONFIG.SETTING (SETTING_NM, SETTING_VALUE) "
        "VALUES ('x', NULL);"
    )
    with pytest.raises(AssertionError, match="setting_value"):
        assert_snapshot_matches(
            [{"setting_nm": "x", "setting_value": "x"}],
            seed,
            "setting_nm",
        )


def test_comma_inside_a_description_stays_one_column() -> None:
    rows = parse_insert_rows(
        "INSERT INTO CONFIG.SETTING (SETTING_NM, SETTING_VALUE, DESCRIPTION) "
        "VALUES ('min_metric_obs', '60', "
        "'below which Sharpe is undefined (decisions #63, #82).');"
    )
    assert len(rows) == 1
    assert rows[0]["description"] == (
        "below which Sharpe is undefined (decisions #63, #82)."
    )


def test_doubled_quote_inside_a_string_is_one_quote() -> None:
    rows = parse_insert_rows("INSERT INTO T (NAME) VALUES ('it''s');")
    assert rows == [{"name": "it's"}]


def test_a_line_comment_does_not_become_a_row() -> None:
    rows = parse_insert_rows(
        "-- ('hidden', '1')\n"
        "INSERT INTO CONFIG.SETTING (SETTING_NM, SETTING_VALUE) VALUES\n"
        "    ('kept', '1');\n"
    )
    assert rows == [{"setting_nm": "kept", "setting_value": "1"}]


def test_empty_snapshot_does_not_match() -> None:
    with pytest.raises(AssertionError, match="snapshot is empty"):
        assert_snapshot_matches(
            [],
            [{"setting_nm": "a", "setting_value": "1"}],
            "setting_nm",
        )


def test_one_row_matches_and_one_extra_seed_row_does_not() -> None:
    one = [{"setting_nm": "a", "setting_value": "1"}]
    assert_snapshot_matches(one, one, "setting_nm")
    with pytest.raises(AssertionError, match="only in seed"):
        assert_snapshot_matches(
            one,
            one + [{"setting_nm": "b", "setting_value": "2"}],
            "setting_nm",
        )


def test_a_changed_value_names_the_key() -> None:
    with pytest.raises(AssertionError, match="min_metric_obs"):
        assert_snapshot_matches(
            [{"setting_nm": "min_metric_obs", "setting_value": "61"}],
            [{"setting_nm": "min_metric_obs", "setting_value": "60"}],
            "setting_nm",
        )
