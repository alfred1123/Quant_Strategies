"""When to seed / reset ``DEPLOYMENT_SCHEDULE_STATUS.SCHEDULED_TS`` (before close)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from quant.refdata.reader import RedisRefData
from quant.schemas.deployments import DeploymentRow, DeploymentStatus, UpdateDeploymentRequest
from quant.shared.intervals import next_apply_slot, next_session_apply_slot


def should_realign_schedule(
    current: DeploymentRow, req: UpdateDeploymentRequest
) -> bool:
    """Whether this PATCH should seed a fresh bar-close-aligned ``SCHEDULED_TS``."""
    if "schedule_tm_interval_id" in req.model_fields_set:
        new_interval = req.schedule_tm_interval_id
        if new_interval != current.schedule_tm_interval_id and new_interval is not None:
            return True
    scheduled = current.schedule_tm_interval_id is not None
    if req.enabled is True and current.is_enabled_ind != "Y" and scheduled:
        return True
    if (
        req.deployment_status == DeploymentStatus.ACTIVE
        and current.deployment_status == DeploymentStatus.PAUSED
        and scheduled
    ):
        return True
    return False


def compute_initial_scheduled_ts(
    *,
    refdata: RedisRefData,
    app_id: int,
    schedule_tm_interval_id: int,
    listing_exchange: str | None = None,
    after: datetime | None = None,
) -> datetime:
    """Next apply: ``EXECUTE_OFFSET`` before the bar (or session) closes.

    A continuous market (``MARKET_CLOSE_TIME`` null — crypto) uses the epoch
    bar boundary. A listed daily session uses that venue's close, so the order
    is in before the bell instead of waiting for a bar that only exists after
    the market has shut.
    """
    moment = after or datetime.now(UTC)
    period = refdata.get_interval_period(schedule_tm_interval_id)
    offset = refdata.get_execute_offset(app_id, schedule_tm_interval_id)
    calendar = refdata.get_market_calendar(listing_exchange=listing_exchange)
    close = calendar["market_close_time"]
    if close is not None and period >= timedelta(days=1):
        return next_session_apply_slot(
            moment,
            close_time=close,
            timezone=str(calendar["bar_timezone"]),
            offset=offset,
        )
    return next_apply_slot(moment, period, offset)
