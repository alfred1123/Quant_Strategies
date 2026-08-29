"""Which cadence a deployment may be scheduled on."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from quant.trade.errors import TradeValidationError

if TYPE_CHECKING:
    from quant.refdata.reader import RedisRefData

logger = logging.getLogger(__name__)

#: Bar period every strategy on the platform is fitted on. A period rather than
#: an interval id, so REFDATA stays the only thing that knows what that period
#: is called and numbered — the same way an unscheduled live apply picks its
#: cadence.
FITTED_BAR_PERIOD = timedelta(days=1)


def schedulable_interval_ids(refdata: RedisRefData) -> list[int]:
    """Intervals a live signal can legitimately be computed on."""
    return [refdata.resolve_interval_id(FITTED_BAR_PERIOD)]


def require_fitted_interval(
    schedule_tm_interval_id: int | None,
    *,
    refdata: RedisRefData,
) -> None:
    """Refuse a cadence the strategy's parameters were never fitted on.

    A schedule does not only decide *when* an apply runs — it decides which
    bars the signal is computed from, because ``LiveApplyOrchestrator``
    resolves the deployment's interval straight into ``load_window``. Putting
    a daily-fitted strategy on an hourly schedule therefore feeds hourly bars
    to parameters derived from daily ones, and nothing downstream can notice:
    a 20-bar Bollinger band computes happily over 20 hourly bars and returns a
    position that looks exactly like a real one. That is the failure this
    guard exists for — money moves on a number no backtest ever justified.

    ``None`` is always allowed. Manual apply has no cadence to conflict with
    and already prices off the fitted daily interval.
    """
    if schedule_tm_interval_id is None:
        return
    allowed = schedulable_interval_ids(refdata)
    if schedule_tm_interval_id in allowed:
        return
    wanted = refdata.interval_label(schedule_tm_interval_id)
    fitted = ", ".join(refdata.interval_label(i) for i in allowed)
    raise TradeValidationError(
        f"cannot schedule this deployment on {wanted}: its strategy was fitted "
        f"on {fitted} bars, and the schedule decides which bars the live "
        f"signal is computed from. Use {fitted}, or leave the schedule manual."
    )
