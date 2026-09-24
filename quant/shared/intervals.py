"""Interval arithmetic driven by ``REFDATA.TM_INTERVAL``.

Bar boundaries and scheduler ticks are both derived from ``PERIOD_LENGTH``, so
the arithmetic lives here rather than being reimplemented on each side. No
interval name is hardcoded — callers pass the period they read from REFDATA,
per the REFDATA single-source-of-truth decision.

Pure arithmetic, no I/O: the REFDATA lookup itself is
``RedisRefData.get_interval_period``, alongside the other resolvers.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# str(timedelta) — "1 day, 0:00:00", "1:00:00", "-1 day, 23:00:00"
_TIMEDELTA_TEXT = re.compile(
    r"^\s*(?:(?P<days>-?\d+)\s+days?,?\s*)?"
    r"(?P<hours>-?\d+):(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2})"
    r"(?:\.(?P<micros>\d+))?\s*$"
)


def parse_period(value: timedelta | str) -> timedelta:
    """Coerce a REFDATA ``PERIOD_LENGTH`` into a ``timedelta``.

    psycopg hands back a ``timedelta``, but the REFDATA publisher serialises
    rows with ``json.dumps(default=str)``, so anything that reached the caller
    through Redis arrives as ``"1 day, 0:00:00"`` instead. Accept both rather
    than making every caller remember which side it came from.
    """
    if isinstance(value, timedelta):
        period = value
    elif isinstance(value, str):
        match = _TIMEDELTA_TEXT.match(value)
        if match is None:
            raise ValueError(f"unrecognised PERIOD_LENGTH: {value!r}")
        parts = match.groupdict()
        micros = parts["micros"] or ""
        period = timedelta(
            days=int(parts["days"] or 0),
            hours=int(parts["hours"]),
            minutes=int(parts["minutes"]),
            seconds=int(parts["seconds"]),
            microseconds=int(micros.ljust(6, "0")[:6]) if micros else 0,
        )
    else:
        raise TypeError(f"PERIOD_LENGTH must be a timedelta or str, got {type(value).__name__}")

    if period <= timedelta(0):
        raise ValueError(f"PERIOD_LENGTH must be positive, got {period}")
    return period


def floor_to_period(ts: datetime, period: timedelta) -> datetime:
    """Round ``ts`` down to the boundary that opened the period containing it.

    Binning runs from the Unix epoch, which puts daily boundaries at 00:00 UTC
    and hourly ones at the top of the hour.
    """
    _require_utc(ts)
    elapsed = ts - _EPOCH
    return _EPOCH + (elapsed // period) * period


def last_closed_bar(now: datetime, period: timedelta) -> datetime:
    """Open time of the newest bar that has finished forming.

    The bar covering ``now`` is still open, so the newest usable one starts a
    full period earlier. Only closed bars may be persisted or traded on.
    """
    return floor_to_period(now, period) - period


def next_run_at(after: datetime, period: timedelta) -> datetime:
    """Next interval boundary strictly after ``after`` — for display only.

    Scheduler due-ness comes from ``SP_GET_MISSED_DUE_DEPLOYMENTS``; this is
    what the UI shows as "next run". Does not include ``EXECUTE_OFFSET`` from
    REFDATA — use :func:`next_apply_slot` for the poller cursor.
    """
    return floor_to_period(after, period) + period


def next_apply_slot(after: datetime, period: timedelta, offset: timedelta) -> datetime:
    """Next scheduled apply: ``offset`` before the bar that contains ``after`` closes.

    Continuous markets (crypto) close on the epoch boundary — midnight UTC for
    a daily bar. Applying after that close is the next session on a listed
    market, so the fill is no longer the bar the signal was read from.
    ``offset`` comes from ``REFDATA.APP_APPLY_TIMING`` (typically 5 minutes
    *before* close). If that instant is still ahead, use it; otherwise the
    same lead on the following bar.
    """
    if not timedelta(0) <= offset < period:
        raise ValueError(f"EXECUTE_OFFSET must be in [0, {period}), got {offset}")
    after = as_utc(after)
    close = floor_to_period(after, period) + period
    candidate = close - offset
    if candidate > after:
        return candidate
    return candidate + period


def next_session_apply_slot(
    after: datetime,
    *,
    close_time: time,
    timezone: str,
    offset: timedelta,
) -> datetime:
    """Next apply before a listed session's close, skipping Saturday and Sunday.

    ``close_time`` is wall-clock in ``timezone`` (``REFDATA.MARKET_CALENDAR``).
    Holidays are not on that table, so a holiday still produces a slot.
    """
    if offset < timedelta(0):
        raise ValueError(f"EXECUTE_OFFSET must be >= 0, got {offset}")
    zone = ZoneInfo(timezone)
    cursor = as_utc(after).astimezone(zone)
    day = cursor.date()
    for _ in range(10):
        if day.weekday() >= 5:
            day += timedelta(days=1)
            continue
        close_local = datetime.combine(day, close_time, tzinfo=zone)
        candidate = close_local - offset
        if candidate > cursor:
            return candidate.astimezone(UTC)
        day += timedelta(days=1)
    raise ValueError(f"no session close within 10 days of {after} in {timezone}")


def bar_starts(start: datetime, end: datetime, period: timedelta) -> list[datetime]:
    """Every bar open time in ``[start, end]``, aligned to period boundaries."""
    _require_utc(start)
    _require_utc(end)
    current = floor_to_period(start, period)
    if current < start:
        current += period
    out: list[datetime] = []
    while current <= end:
        out.append(current)
        current += period
    return out


def ccxt_timeframe(period: timedelta) -> str:
    """Render a period as a ccxt timeframe string (``1h``, ``1d``, ``15m``)."""
    seconds = int(period.total_seconds())
    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    raise ValueError(f"no ccxt timeframe for period {period}")


def as_utc(ts: datetime) -> datetime:
    """Coerce a timestamp to timezone-aware UTC.

    Naive values are treated as UTC. Bar boundaries are always UTC, and API
    query params such as ``target=2020-03-25`` arrive without a zone — there
    is no other timezone they could mean.
    """
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _require_utc(ts: datetime) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware UTC, got naive {ts!r}")
