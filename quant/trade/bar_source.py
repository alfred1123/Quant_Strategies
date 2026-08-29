"""Bind a deployment's broker to the price bars its signal is computed from.

Composition only — `quant/market_data/` knows nothing about deployments, and
`quant/trade/` knows nothing about ccxt pagination. This is where the two meet:
an ``APP_ID`` picks the venue, and the venue picks the fetcher.
"""

from __future__ import annotations

import functools
import logging
from datetime import timedelta

from quant.market_data.fetcher import CcxtBarFetcher
from quant.market_data.repo import PriceBarRepo
from quant.market_data.service import PriceBarService
from quant.refdata.bundle import DataCaches
from quant.trade.db_repo import TradeRepo
from quant.trade.errors import TradeValidationError
from quant.trade.registry import exchange_id_for_app

logger = logging.getLogger(__name__)


class PriceBarServiceFactory:
    """One :class:`PriceBarService` per broker, over a shared repo connection.

    Services are cached because building one spins up a ccxt client, and a
    scheduled apply runs on every interval boundary. The repo is deliberately
    *not* per-broker: it is a long-lived connection to one database, and bars
    for every venue land in the same table.
    """

    def __init__(self, conninfo: str, data_caches: DataCaches) -> None:
        self._caches = data_caches
        self._repo = PriceBarRepo(conninfo)
        self._by_app_id: dict[int, PriceBarService] = {}

    def for_app(self, app_id: int) -> PriceBarService:
        """Price bar service reading from the venue behind ``app_id``."""
        service = self._by_app_id.get(app_id)
        if service is not None:
            return service

        exchange_id = exchange_id_for_app(app_id, refdata=self._caches.refdata)
        if exchange_id is None:
            raise TradeValidationError(
                f"no market data venue for app_id={app_id} — cannot price a "
                f"scheduled deployment without bars from the exchange it trades on"
            )
        service = PriceBarService(
            self._repo,
            self._caches.refdata,
            self._caches.instrument_cache,
            CcxtBarFetcher(exchange_id),
        )
        self._by_app_id[app_id] = service
        logger.info("price bar service ready for app_id=%s via %s", app_id, exchange_id)
        return service


def resolve_signal_source(
    *,
    app_id: int,
    schedule_tm_interval_id: int | None,
    data_caches: DataCaches,
    price_bars: PriceBarServiceFactory | None,
    what: str,
):
    """Pick the price series a deployment's signal is computed from, and name it.

    The rule is by venue, not by schedule: a signal reads the bars of the
    exchange it executes on whenever that exchange serves market data. The
    schedule only sets the bar interval — without one the apply is assumed
    daily. The provider path survives solely for brokers with no market-data
    venue (e.g. Futu equities), where the provider series is the only one there
    is.

    Shared by the live apply and the dry run **because they disagreed**: the
    dry run took the provider path unconditionally, so the preview a user
    checked before going live was computed from a different series than the
    order that followed. Near a band edge that is a preview saying HOLD and an
    apply placing a BUY, with neither malfunctioning. One resolver, one answer.

    The label travels onto the report because the two sources are not the same
    numbers, and a divergence is only diagnosable if the input is recorded
    alongside the output.
    """
    venue = exchange_id_for_app(app_id, refdata=data_caches.refdata)
    interval_id = schedule_tm_interval_id
    if interval_id is None:
        if venue is None:
            return None, "provider"
        interval_id = data_caches.refdata.resolve_interval_id(timedelta(days=1))
    if price_bars is None:
        raise TradeValidationError(
            f"{what} needs exchange bars on interval {interval_id} but no price "
            f"bar source is configured"
        )
    # for_app refuses venue-less apps, so a loader implies a named venue.
    loader = functools.partial(
        price_bars.for_app(app_id).load_window,
        tm_interval_id=interval_id,
        source_app_id=app_id,
    )
    return loader, f"price_bar:{venue}"


class DeploymentInstrumentSource:
    """The traded half of the warmer's instrument list.

    The warmer lives in ``quant/market_data/`` and must not read
    ``TRADE.DEPLOYMENT``, so this is the adapter that hands it those rows —
    the same composition this module already performs for bar fetching.

    Stopping a deployment removes its instruments from the warm by
    construction, because the procedure behind this only returns enabled,
    scheduled, unstopped rows. A subscription is independent and survives that;
    keeping the two in step would force a question on every stop that has no
    good answer — was the capture the deployment's, or did the user want it?
    """

    def __init__(self, repo: TradeRepo) -> None:
        self._repo = repo

    def instruments(self) -> list[dict]:
        return self._repo.sp_get_scheduled_instruments()
