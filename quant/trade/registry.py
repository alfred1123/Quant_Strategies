"""Resolve REFDATA.APP → broker adapter factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from quant.trade.adapters.base import TradeAdapter
from quant.trade.brokers.ccxt.config import CCXT_PRESETS, CcxtExchangePreset
from quant.trade.errors import AdapterNotFoundError

logger = logging.getLogger(__name__)

AdapterFactory = Callable[..., TradeAdapter]


class AdapterRegistry:
    """Maps ``app_id`` to adapter constructor."""

    def __init__(self) -> None:
        self._by_app_id: dict[int, AdapterFactory] = {}

    def register(self, app_id: int, factory: AdapterFactory) -> None:
        self._by_app_id[app_id] = factory
        logger.debug("registered adapter for app_id=%s", app_id)

    def register_by_name(
        self, app_name: str, factory: AdapterFactory, *, refdata
    ) -> None:
        """Resolve ``app_name`` via REFDATA and register."""
        app_id = refdata.resolve_app_id(app_name)
        if app_id is None:
            raise ValueError(f"REFDATA.APP has no row for name={app_name!r}")
        self.register(app_id, factory)

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


def build_default_registry(refdata) -> AdapterRegistry:
    """Register built-in ccxt adapters. Called at API startup."""
    registry = AdapterRegistry()
    for app_name, preset in CCXT_PRESETS.items():
        registry.register_by_name(app_name, _factory_for(preset), refdata=refdata)
    return registry
