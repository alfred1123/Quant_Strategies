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
    from quant.trade.brokers.ccxt.routing import KeyRouter

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


def _factory_for(
    preset: CcxtExchangePreset, key_router: KeyRouter | None
) -> AdapterFactory:
    from quant.trade.brokers.ccxt.adapter import create_ccxt_adapter

    def factory(**kwargs: Any) -> TradeAdapter:
        return create_ccxt_adapter(preset=preset, key_router=key_router, **kwargs)

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


def build_default_registry(
    refdata: RedisRefData, *, key_router: KeyRouter | None = None
) -> AdapterRegistry:
    """Register built-in ccxt adapters. Called at API startup.

    ``key_router`` picks each keyed session's egress route; without one every
    session goes direct.
    """
    registry = AdapterRegistry()
    for app_id, preset in ccxt_apps(refdata):
        registry.register(app_id, _factory_for(preset, key_router))
    return registry


def preset_for_app(app_id: int, *, refdata: RedisRefData) -> CcxtExchangePreset | None:
    """Preset behind a ``REFDATA.APP`` id, or ``None`` if that app is not a broker.

    Market data has to reach the same venue the orders go to. The ccxt
    default type is the instrument's ``ISSUE_TYPE``, read from the instrument
    cache when the bars are fetched, through the same preset map the order
    session uses.
    """
    for candidate_id, preset in ccxt_apps(refdata):
        if candidate_id == app_id:
            return preset
    return None


def exchange_id_for_app(app_id: int, *, refdata: RedisRefData) -> str | None:
    """ccxt exchange id behind a ``REFDATA.APP`` id, or ``None`` if not a broker."""
    preset = preset_for_app(app_id, refdata=refdata)
    return None if preset is None else preset.exchange_id
