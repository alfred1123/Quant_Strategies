"""Which cadence a deployment may be scheduled on."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from quant.trade.errors import TradeValidationError

if TYPE_CHECKING:
    from quant.refdata.reader import RedisRefData

logger = logging.getLogger(__name__)


def fitted_interval_id(config_json: dict | None) -> int:
    """The bar interval a strategy's parameters were fitted on.

    Read from the strategy's own ``CONFIG_JSON.tm_interval_id`` — required since
    #57 — not assumed: a strategy fitted on hourly bars trades hourly, and
    offering it a daily schedule would feed its parameters a series no backtest
    ever produced. There is no fallback: a strategy that names no interval is a
    data error, not a licence to guess one, so it is refused rather than
    silently defaulted.
    """
    interval = (config_json or {}).get("tm_interval_id")
    if interval is None:
        raise TradeValidationError(
            "strategy config has no tm_interval_id — it must name the interval "
            "its parameters were fitted on"
        )
    return int(interval)


def require_fitted_interval(
    schedule_tm_interval_id: int | None,
    *,
    fitted_interval_id: int,
    refdata: RedisRefData,
) -> None:
    """Refuse any cadence but the one the strategy was fitted on.

    A schedule does not only decide *when* an apply runs — it decides which
    bars the signal is computed from, because ``LiveApplyOrchestrator``
    resolves the deployment's interval straight into ``load_window``. Scheduling
    on any other interval feeds parameters derived from one bar length a series
    of another, and nothing downstream can notice: a 20-bar Bollinger band
    computes happily over 20 bars of the wrong length and returns a position
    that looks exactly like a real one. That is the failure this guard exists
    for — money moves on a number no backtest ever justified.

    ``None`` is always allowed. Manual apply prices off the same fitted interval
    and has no cadence to conflict with.
    """
    if schedule_tm_interval_id is None or schedule_tm_interval_id == fitted_interval_id:
        return
    wanted = refdata.interval_label(schedule_tm_interval_id)
    fitted = refdata.interval_label(fitted_interval_id)
    raise TradeValidationError(
        f"cannot schedule this deployment on {wanted}: its strategy was fitted "
        f"on {fitted} bars, and the schedule decides which bars the live "
        f"signal is computed from. Use {fitted}, or leave the schedule manual."
    )
