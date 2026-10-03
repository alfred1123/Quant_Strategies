"""Parse and compare saved Glassnode HTTP responses.

This module does not open a socket and does not read an API key. The live
client remains ``Glassnode.get_historical_price`` in ``quant/data/sources.py``.
The harness under ``scripts/glassnode_local_harness.py`` uses these functions
on files that were saved earlier.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Headers that move on every call and are not part of the series.
TRANSPORT_HEADERS = frozenset({
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
})

# Quota advertisement. A change is reported on its own, separate from a
# rewrite of a historical point.
QUOTA_HEADERS = frozenset({
    "x-rate-limit-limit",
})

_COPY_FILES = ("request.json", "response.meta.json", "response.body")


@dataclass(frozen=True)
class RequestIdentity:
    """The request a saved body answers."""

    metric_path: str
    asset: str
    interval: str
    since: int
    until: int


@dataclass(frozen=True)
class Point:
    """One series element. ``v`` is the JSON number literal, not a binary float."""

    t: int
    v: str


@dataclass(frozen=True)
class RateLimitHeaders:
    """Short-window headers. Any field is ``None`` when the copy did not retain it."""

    limit: str | None
    remaining: str | None
    reset: str | None


@dataclass(frozen=True)
class ParsedResponse:
    """A saved status line, headers, and body."""

    status: int
    content_type: str | None
    headers: Mapping[str, str]
    body: bytes
    points: tuple[Point, ...] | None
    error_text: str | None
    is_json_array: bool
    object_keys: tuple[str, ...]
    unexpected_point_keys: tuple[str, ...]

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def rate_limit(self) -> RateLimitHeaders:
        return rate_limit_from_headers(self.headers)


@dataclass(frozen=True)
class SavedCopy:
    """One on-disk response plus the request it belongs to."""

    request: RequestIdentity
    parsed: ParsedResponse
    captured_at: str | None
    directory: Path


@dataclass(frozen=True)
class ValueChange:
    t: int
    earlier_v: str
    later_v: str


@dataclass(frozen=True)
class RevisionReport:
    """Difference between two copies of the same request.

    ``value_changes`` and the timestamp sets are a rewrite of history.
    Transport headers may differ. No field here is filled from a guessed
    revision: both sides are caller-supplied copies.
    """

    request_mismatch: str | None
    value_changes: tuple[ValueChange, ...]
    timestamps_only_earlier: tuple[int, ...]
    timestamps_only_later: tuple[int, ...]
    duplicate_timestamps_earlier: tuple[int, ...]
    duplicate_timestamps_later: tuple[int, ...]
    error_text_earlier: str | None
    error_text_later: str | None
    status_earlier: int
    status_later: int
    content_type_earlier: str | None
    content_type_later: str | None
    body_sha256_earlier: str
    body_sha256_later: str
    quota_changes: tuple[tuple[str, str | None, str | None], ...]
    transport_changes: tuple[tuple[str, str | None, str | None], ...]
    other_header_changes: tuple[tuple[str, str | None, str | None], ...]

    @property
    def value_revision(self) -> bool:
        if self.request_mismatch:
            return False
        return bool(
            self.value_changes
            or self.timestamps_only_earlier
            or self.timestamps_only_later
            or self.duplicate_timestamps_earlier
            or self.duplicate_timestamps_later
            or self.error_text_earlier != self.error_text_later
        )

    @property
    def status_changed(self) -> bool:
        return self.status_earlier != self.status_later

    @property
    def content_type_changed(self) -> bool:
        return self.content_type_earlier != self.content_type_later


def rate_limit_from_headers(headers: Mapping[str, str]) -> RateLimitHeaders:
    """Read the three short-window headers. Names are matched case-insensitively."""
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    return RateLimitHeaders(
        limit=lower.get("x-rate-limit-limit"),
        remaining=lower.get("x-rate-limit-remaining"),
        reset=lower.get("x-rate-limit-reset"),
    )


def media_type(content_type: str | None) -> str | None:
    """Drop parameters such as ``charset`` so two copies of the same type match."""
    if content_type is None:
        return None
    base = content_type.split(";", 1)[0].strip().lower()
    return base or None


def parse_response(*, status: int, headers: Mapping[str, str], body: bytes) -> ParsedResponse:
    """Turn one saved HTTP response into points, or into an error string.

    A ``text/*`` body is not parsed as JSON. That is how the plain-text
    ``400`` for an unknown asset stays an error. A JSON list of objects with
    ``t`` and ``v`` becomes points. ``v`` stays the number literal from the
    file so a later copy can be compared without a float round-trip.
    """
    norm_headers = {str(k).lower(): str(v) for k, v in headers.items()}
    ctype = media_type(norm_headers.get("content-type"))
    if ctype is not None and ctype.startswith("text/"):
        return _error_response(status, ctype, norm_headers, body, body.decode("utf-8"))

    text = body.decode("utf-8")
    stripped = text.lstrip()
    if not stripped:
        return _error_response(status, ctype, norm_headers, body, text)

    if stripped[0] not in "[{":
        return _error_response(status, ctype, norm_headers, body, text)

    try:
        data = json.loads(text, parse_int=str, parse_float=str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"body is not valid JSON: {exc}") from exc

    if isinstance(data, dict):
        return ParsedResponse(
            status=status,
            content_type=ctype,
            headers=norm_headers,
            body=body,
            points=None,
            error_text=None,
            is_json_array=False,
            object_keys=tuple(data.keys()),
            unexpected_point_keys=(),
        )

    if not isinstance(data, list):
        raise TypeError(f"JSON body must be a list or object, got {type(data).__name__}")

    points: list[Point] = []
    unexpected: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise TypeError(f"point {i} is not an object")
        keys = set(item)
        extra = keys - {"t", "v"}
        if extra:
            unexpected.extend(sorted(extra))
        if "t" not in item or "v" not in item:
            raise ValueError(f"point {i} is missing t or v")
        if not isinstance(item["t"], str) or not item["t"].isdigit():
            raise ValueError(f"point {i} t is not an integer literal")
        if not isinstance(item["v"], str):
            raise TypeError(f"point {i} v is not a JSON number")
        points.append(Point(t=int(item["t"]), v=item["v"]))

    return ParsedResponse(
        status=status,
        content_type=ctype,
        headers=norm_headers,
        body=body,
        points=tuple(points),
        error_text=None,
        is_json_array=True,
        object_keys=(),
        unexpected_point_keys=tuple(dict.fromkeys(unexpected)),
    )


def load_saved_copy(directory: Path) -> SavedCopy:
    """Load ``request.json``, ``response.meta.json``, and ``response.body``.

    Raises ``FileNotFoundError`` if any of the three is absent.
    """
    directory = Path(directory)
    missing = [name for name in _COPY_FILES if not (directory / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing {', '.join(missing)} in {directory}")

    request_doc = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    meta = json.loads((directory / "response.meta.json").read_text(encoding="utf-8"))
    body = (directory / "response.body").read_bytes()
    headers = meta.get("headers") or {}
    if not isinstance(headers, dict):
        raise TypeError(f"{directory / 'response.meta.json'} headers must be an object")

    identity = RequestIdentity(
        metric_path=str(request_doc["metric_path"]),
        asset=str(request_doc["asset"]),
        interval=str(request_doc["interval"]),
        since=int(request_doc["since"]),
        until=int(request_doc["until"]),
    )
    parsed = parse_response(status=int(meta["status"]), headers=headers, body=body)
    captured = request_doc.get("captured_at")
    logger.debug(
        "loaded glassnode copy %s %s %s status=%s points=%s",
        identity.metric_path,
        identity.asset,
        identity.interval,
        parsed.status,
        None if parsed.points is None else len(parsed.points),
    )
    return SavedCopy(
        request=identity,
        parsed=parsed,
        captured_at=None if captured is None else str(captured),
        directory=directory,
    )


def compare_copies(earlier: SavedCopy, later: SavedCopy) -> RevisionReport:
    """Compare two saved copies.

    The request identity has to match. A different asset or window is not a
    revision of history. ``captured_at`` is stored and not compared.
    """
    mismatch = _request_mismatch(earlier.request, later.request)
    quota, transport, other = _header_diffs(earlier.parsed.headers, later.parsed.headers)
    if mismatch is not None:
        return _revision_report(
            earlier, later,
            request_mismatch=mismatch,
            value_changes=(),
            timestamps_only_earlier=(),
            timestamps_only_later=(),
            duplicate_timestamps_earlier=(),
            duplicate_timestamps_later=(),
            quota_changes=quota,
            transport_changes=transport,
            other_header_changes=other,
        )

    earlier_idx, earlier_dups = _index_points(earlier.parsed.points)
    later_idx, later_dups = _index_points(later.parsed.points)
    only_earlier = tuple(sorted(set(earlier_idx) - set(later_idx)))
    only_later = tuple(sorted(set(later_idx) - set(earlier_idx)))
    changes = tuple(
        ValueChange(t=t, earlier_v=earlier_idx[t], later_v=later_idx[t])
        for t in sorted(set(earlier_idx) & set(later_idx))
        if earlier_idx[t] != later_idx[t]
    )
    return _revision_report(
        earlier, later,
        request_mismatch=None,
        value_changes=changes,
        timestamps_only_earlier=only_earlier,
        timestamps_only_later=only_later,
        duplicate_timestamps_earlier=earlier_dups,
        duplicate_timestamps_later=later_dups,
        quota_changes=quota,
        transport_changes=transport,
        other_header_changes=other,
    )


def _revision_report(
    earlier: SavedCopy,
    later: SavedCopy,
    *,
    request_mismatch: str | None,
    value_changes: tuple[ValueChange, ...],
    timestamps_only_earlier: tuple[int, ...],
    timestamps_only_later: tuple[int, ...],
    duplicate_timestamps_earlier: tuple[int, ...],
    duplicate_timestamps_later: tuple[int, ...],
    quota_changes: tuple[tuple[str, str | None, str | None], ...],
    transport_changes: tuple[tuple[str, str | None, str | None], ...],
    other_header_changes: tuple[tuple[str, str | None, str | None], ...],
) -> RevisionReport:
    return RevisionReport(
        request_mismatch=request_mismatch,
        value_changes=value_changes,
        timestamps_only_earlier=timestamps_only_earlier,
        timestamps_only_later=timestamps_only_later,
        duplicate_timestamps_earlier=duplicate_timestamps_earlier,
        duplicate_timestamps_later=duplicate_timestamps_later,
        error_text_earlier=earlier.parsed.error_text,
        error_text_later=later.parsed.error_text,
        status_earlier=earlier.parsed.status,
        status_later=later.parsed.status,
        content_type_earlier=earlier.parsed.content_type,
        content_type_later=later.parsed.content_type,
        body_sha256_earlier=earlier.parsed.body_sha256,
        body_sha256_later=later.parsed.body_sha256,
        quota_changes=quota_changes,
        transport_changes=transport_changes,
        other_header_changes=other_header_changes,
    )


def _error_response(status, ctype, headers, body, text: str) -> ParsedResponse:
    return ParsedResponse(
        status=status,
        content_type=ctype,
        headers=headers,
        body=body,
        points=None,
        error_text=text,
        is_json_array=False,
        object_keys=(),
        unexpected_point_keys=(),
    )


def _request_mismatch(earlier: RequestIdentity, later: RequestIdentity) -> str | None:
    fields = ("metric_path", "asset", "interval", "since", "until")
    diffs = [
        f"{name} {getattr(earlier, name)!r} -> {getattr(later, name)!r}"
        for name in fields
        if getattr(earlier, name) != getattr(later, name)
    ]
    if not diffs:
        return None
    return "request identity differs: " + ", ".join(diffs)


def _index_points(points: tuple[Point, ...] | None) -> tuple[dict[int, str], tuple[int, ...]]:
    if points is None:
        return {}, ()
    index: dict[int, str] = {}
    dups: list[int] = []
    for point in points:
        if point.t in index:
            dups.append(point.t)
        index[point.t] = point.v
    return index, tuple(dups)


def _header_diffs(
    earlier: Mapping[str, str],
    later: Mapping[str, str],
) -> tuple[
    tuple[tuple[str, str | None, str | None], ...],
    tuple[tuple[str, str | None, str | None], ...],
    tuple[tuple[str, str | None, str | None], ...],
]:
    skip = {"content-type"}
    names = sorted((set(earlier) | set(later)) - skip)
    quota: list[tuple[str, str | None, str | None]] = []
    transport: list[tuple[str, str | None, str | None]] = []
    other: list[tuple[str, str | None, str | None]] = []
    for name in names:
        ev = earlier.get(name)
        lv = later.get(name)
        if ev == lv:
            continue
        row = (name, ev, lv)
        if name in QUOTA_HEADERS:
            quota.append(row)
        elif name in TRANSPORT_HEADERS:
            transport.append(row)
        else:
            other.append(row)
    return tuple(quota), tuple(transport), tuple(other)
