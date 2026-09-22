"""Resolve REFDATA.APP → broker adapter factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from quant.trade.adapters.base import TradeAdapter
from quant.trade.brokers.ccxt.config import CCXT_PRESETS, CcxtExchangePreset
from quant.trade.errors import AdapterNotFoundError

if TYPE_CHECKING:
    from quant.refdata.reader import RedisRefData

logger = logging.getLogger(__name__)

AdapterFactory = Callable[..., TradeAdapter]


class AdapterRegistry:
    """Maps ``app_id`` to adapter constructor."""

    def __init__(self) -> None:
        self._by_app_id: dict[int, AdapterFactory] = {}

    def register(self, app_id: int, factory: AdapterFactory) -> None:
        self._by_app_id[app_id] = factory
        logger.debug("registered adapter for app_id=%s", app_id)

    def create(self, app_id: int, **kwargs: Any) -> TradeAdapter:
        factory = self._by_app_id.get(app_id)
        if factory is None:
            raise AdapterNotFoundError(f"no adapter registered for app_id={app_id}")
        return factory(**kwargs)

    def has_adapter(self, app_id: int) -> bool:
        return app_id in self._by_app_id


def _factory_for(preset: CcxtExchangePreset) -> AdapterFactory:
    from quant.trade.brokers.ccxt.adapter import create_ccxt_adapter

    def factory(**kwargs: Any) -> TradeAdapter:
        return create_ccxt_adapter(preset=preset, **kwargs)

    return factory


def ccxt_apps(refdata: RedisRefData) -> list[tuple[int, CcxtExchangePreset]]:
    """``(app_id, preset)`` for every ccxt broker REFDATA knows about.

    The join between ``CCXT_PRESETS`` (code) and ``REFDATA.APP`` (Postgres →
    Redis) lives here alone, so the registry, the price-bar source, and the
    venue-limits publisher cannot disagree about which apps are brokers.
    """
    apps: list[tuple[int, CcxtExchangePreset]] = []
    for app_name, preset in CCXT_PRESETS.items():
        app_id = refdata.resolve_app_id(app_name)
        if app_id is None:
            logger.warning("REFDATA.APP has no row for name=%r", app_name)
            continue
        apps.append((app_id, preset))
    return apps


def build_default_registry(refdata: RedisRefData) -> AdapterRegistry:
    """Register built-in ccxt adapters. Called at API startup."""
    registry = AdapterRegistry()
    for app_id, preset in ccxt_apps(refdata):
        registry.register(app_id, _factory_for(preset))
    return registry


def exchange_id_for_app(app_id: int, *, refdata: RedisRefData) -> str | None:
    """ccxt exchange id behind a ``REFDATA.APP`` id, or ``None`` if not a broker.

    Market data has to reach the same venue the orders go to, so the mapping is
    read back out of ``CCXT_PRESETS`` rather than restated next to the price-bar
    code where it could drift.
    """
    for candidate_id, preset in ccxt_apps(refdata):
        if candidate_id == app_id:
            return preset.exchange_id
    return None
