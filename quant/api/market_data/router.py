"""Market data router — /api/v1/market-data.

Scheduled maintenance of ``MARKET_DATA.PRICE_BAR``. Driven by the scheduler
Lambda (``price_bar_sync``), so its gate admits the service token as well as a
signed-in user.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from quant.api.auth.dependencies import require_user_or_service
from quant.queue.repo import BtQueueRepo
from quant.trade.db_repo import TradeRepo
from quant.trade.scheduler.warm import BarWarmer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


def _get_bar_warmer(request: Request) -> BarWarmer:
    conninfo = request.app.state.db_conninfo
    bt = BtQueueRepo(conninfo, user_id="system")
    repo = TradeRepo(conninfo, bt=bt, user_id="system")
    # Application-scoped: the factory holds a long-lived bar repo connection and
    # a ccxt client per venue, so it must not be rebuilt per request.
    return BarWarmer(repo, request.app.state.price_bars)


@router.post("/price-bars/sync")
def sync_price_bars(
    caller: str = Depends(require_user_or_service),
    warmer: BarWarmer = Depends(_get_bar_warmer),
) -> dict:
    """Pre-fetch bars for every instrument a scheduled deployment will trade.

    Always 200, even when individual instruments fail: this is a best-effort
    warm-up and the apply path re-checks and fails closed on its own. Reporting
    a partial failure as an error would make the Lambda log the whole pass as
    failed when it did most of its work.
    """
    report = warmer.run()
    logger.info(
        "price-bars/sync: %d instrument(s), %d inserted, %d failed, caller=%s",
        report.instruments, report.inserted, report.failed, caller,
    )
    return {
        "instruments": report.instruments,
        "inserted": report.inserted,
        "failed": report.failed,
        "groups": [
            {
                "tm_interval_id": r.tm_interval_id,
                "app_id": r.app_id,
                "instruments": r.instruments,
                "inserted": r.inserted,
                "failures": r.failures,
            }
            for r in report.results
        ],
    }
