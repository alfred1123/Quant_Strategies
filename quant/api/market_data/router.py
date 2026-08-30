"""Market data router — /api/v1/market-data.

Two kinds of caller. ``price-bars/sync`` is scheduled maintenance driven by the
``price_bar_sync`` Lambda, so the router-level gate admits the service token as
well as a signed-in user. Everything else here is a human action, and each one
adds ``require_user`` on top: a service token must not be able to subscribe or
backfill, because both spend exchange rate limit on behalf of somebody who did
not ask. The router gate is a floor, not a ceiling.

Subscriptions are not scoped to the caller. Bars are shared facts, so a
subscription is a platform-wide request that any signed-in user can see and
edit — including disable, which cools the series for everyone. Being signed in
is what these routes check; ownership is not a thing a bar series has.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request

from quant.api.auth.dependencies import require_user, require_user_or_service
from quant.api.auth.models import CurrentUser
from quant.market_data.subscriptions import (
    BarSubscriptionRepo,
    BarSubscriptionService,
    SubscriptionInstrumentSource,
)
from quant.market_data.warm import BarWarmer
from quant.queue.repo import BtQueueRepo
from quant.schemas.market_data import (
    BackfillPlan,
    BackfillReport,
    BackfillRequest,
    BarSubscriptionRow,
    Coverage,
    SubscribeRequest,
    VenueDepth,
)
from quant.trade.bar_source import DeploymentInstrumentSource
from quant.trade.db_repo import TradeRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


def _subscription_repo(request: Request) -> BarSubscriptionRepo:
    return BarSubscriptionRepo(request.app.state.db_conninfo, user_id="system")


def _get_bar_warmer(request: Request) -> BarWarmer:
    """The warmer over both answers to "which instruments matter".

    Deployments and subscriptions are unioned rather than kept in step, so a
    series stays warm while either side wants it and cools when neither does.
    """
    conninfo = request.app.state.db_conninfo
    bt = BtQueueRepo(conninfo, user_id="system")
    trade = TradeRepo(conninfo, bt=bt, user_id="system")
    return BarWarmer(
        [
            DeploymentInstrumentSource(trade),
            SubscriptionInstrumentSource(_subscription_repo(request)),
        ],
        # Application-scoped: the factory holds a long-lived bar repo connection
        # and a ccxt client per venue, so it must not be rebuilt per request.
        request.app.state.price_bars,
    )


def _get_subscriptions(request: Request) -> BarSubscriptionService:
    return BarSubscriptionService(
        _subscription_repo(request),
        request.app.state.data_caches.instrument_cache,
        request.app.state.price_bars,
    )


@router.post("/price-bars/sync")
def sync_price_bars(
    caller: str = Depends(require_user_or_service),
    warmer: BarWarmer = Depends(_get_bar_warmer),
) -> dict:
    """Pre-fetch bars for every series a deployment or a subscription wants.

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


@router.get("/subscriptions", response_model=list[BarSubscriptionRow])
def list_subscriptions(
    _user: CurrentUser = Depends(require_user),
    svc: BarSubscriptionService = Depends(_get_subscriptions),
) -> list[BarSubscriptionRow]:
    """Every subscription, each with what has been captured so far."""
    return [BarSubscriptionRow(**row) for row in svc.list_subscriptions()]


@router.post("/subscriptions", response_model=BarSubscriptionRow)
def subscribe(
    req: SubscribeRequest,
    _user: CurrentUser = Depends(require_user),
    svc: BarSubscriptionService = Depends(_get_subscriptions),
) -> BarSubscriptionRow:
    """Create a subscription, or version one that already exists.

    Not 201: the same route enables, disables and retargets, and only one of
    those creates anything. Subscribing does not fetch — it makes the series
    eligible for the next warm pass, and history comes from backfill.
    """
    row = svc.subscribe(
        internal_cusip=req.internal_cusip,
        tm_interval_id=req.tm_interval_id,
        source_app_id=req.source_app_id,
        is_enabled_ind=req.is_enabled_ind,
        backfill_from_ts=req.backfill_from_ts,
        bar_subscription_id=req.bar_subscription_id,
    )
    return BarSubscriptionRow(
        **row,
        vendor_symbol=svc.vendor_symbol(
            internal_cusip=req.internal_cusip, source_app_id=req.source_app_id
        ),
        coverage=Coverage(
            **svc.coverage(
                internal_cusip=req.internal_cusip,
                tm_interval_id=req.tm_interval_id,
                source_app_id=req.source_app_id,
            )
        ),
    )


@router.get("/price-bars/coverage", response_model=Coverage)
def price_bar_coverage(
    internal_cusip: str,
    tm_interval_id: int,
    source_app_id: int,
    _user: CurrentUser = Depends(require_user),
    svc: BarSubscriptionService = Depends(_get_subscriptions),
) -> Coverage:
    """First bar, last bar and gap count for one series.

    Not scoped to a subscription — coverage is a property of the stored bars,
    which are shared facts, so it answers for a series you have not subscribed
    to as readily as one you have.
    """
    return Coverage(
        **svc.coverage(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
    )


@router.get("/price-bars/venue-depth", response_model=VenueDepth)
def price_bar_venue_depth(
    internal_cusip: str,
    tm_interval_id: int,
    source_app_id: int,
    _user: CurrentUser = Depends(require_user),
    svc: BarSubscriptionService = Depends(_get_subscriptions),
) -> VenueDepth:
    """How far back this venue serves the series, and whether one fill fits.

    Separate from ``/coverage`` because it is a different question with a
    different cost: coverage reads two index probes, this one asks the exchange.
    The dialogs call it to default a capture target to the venue's own floor
    instead of a date the user has to invent — a target older than the listing
    can never be met, and nothing previously said so.
    """
    return VenueDepth(
        **svc.venue_depth(
            internal_cusip=internal_cusip,
            tm_interval_id=tm_interval_id,
            source_app_id=source_app_id,
        )
    )


@router.get("/price-bars/backfill-plan", response_model=BackfillPlan)
def price_bar_backfill_plan(
    internal_cusip: str,
    tm_interval_id: int,
    source_app_id: int,
    target: datetime,
    _user: CurrentUser = Depends(require_user),
    svc: BarSubscriptionService = Depends(_get_subscriptions),
) -> BackfillPlan:
    """The next fill toward ``target``, so deep history can be filled in stages.

    ``target`` is supplied by the caller rather than read from the
    subscription: the page already knows it, having chosen between the row's
    own target and the venue floor, and re-deriving it here would mean a
    second exchange call for a question this endpoint answers from stored
    bars alone.
    """
    return BackfillPlan(
        **vars(
            svc.plan_backfill(
                internal_cusip=internal_cusip,
                tm_interval_id=tm_interval_id,
                source_app_id=source_app_id,
                target=target,
            )
        )
    )


@router.post("/price-bars/backfill", response_model=BackfillReport)
def backfill_price_bars(
    req: BackfillRequest,
    user: CurrentUser = Depends(require_user),
    svc: BarSubscriptionService = Depends(_get_subscriptions),
) -> BackfillReport:
    """Fill an explicit range, reporting what the venue would not serve.

    Synchronous, and it can be slow: a long range is many paginated exchange
    calls. That is the deliberate shape — a background filler would need
    progress tracking, and the honest alternative is a caller who waits and is
    told exactly what arrived.
    """
    result = svc.backfill(
        internal_cusip=req.internal_cusip,
        tm_interval_id=req.tm_interval_id,
        source_app_id=req.source_app_id,
        start=req.start,
        end=req.end,
    )
    logger.info(
        "price-bars/backfill %s interval=%s app=%s: %d inserted, %d unfilled, caller=%s",
        req.internal_cusip, req.tm_interval_id, req.source_app_id,
        result.inserted, len(result.unfilled), user.app_user_id,
    )
    return BackfillReport(
        start=result.start,
        end=result.end,
        expected=result.expected,
        missing=result.missing,
        inserted=result.inserted,
        unfilled=list(result.unfilled),
        is_continuous=result.is_continuous,
    )
