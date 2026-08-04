"""Bind a deployment's broker to the price bars its signal is computed from.

Composition only — `quant/market_data/` knows nothing about deployments, and
`quant/trade/` knows nothing about ccxt pagination. This is where the two meet:
an ``APP_ID`` picks the venue, and the venue picks the fetcher.
"""

from __future__ import annotations

import logging

from quant.market_data.fetcher import CcxtBarFetcher
from quant.market_data.repo import PriceBarRepo
from quant.market_data.service import PriceBarService
from quant.refdata.bundle import DataCaches
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
