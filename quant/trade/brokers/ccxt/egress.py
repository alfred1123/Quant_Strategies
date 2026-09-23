"""Ways out to a venue: straight from this host, or through a named forward proxy.

Deployment-specific, so the list comes from the environment (SSM in prod), not
from :class:`~quant.trade.brokers.ccxt.config.CcxtExchangePreset`, which stays
static wiring. Which route a given key uses is not configured at all: the key's
own allowlist decides, discovered by :class:`quant.trade.brokers.ccxt.routing.KeyRouter`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EgressRoute:
    """One way out to a venue; ``proxy_url=None`` means straight from this host."""

    name: str
    proxy_url: str | None = None


DIRECT = EgressRoute("direct")


@dataclass(frozen=True)
class EgressRoutes:
    """Candidate routes for one venue, ``direct`` always first."""

    routes: tuple[EgressRoute, ...] = (DIRECT,)

    @staticmethod
    def env_var(exchange_id: str) -> str:
        return f"CCXT_EGRESS_{exchange_id.upper()}"

    @classmethod
    def from_env(cls, exchange_id: str) -> EgressRoutes:
        """``direct`` plus each ``name=url`` in ``CCXT_EGRESS_<EXCHANGE_ID>``."""
        env_var = cls.env_var(exchange_id)
        routes = [DIRECT]
        raw = os.getenv(env_var, "")
        for entry in filter(None, (part.strip() for part in raw.split(","))):
            name, sep, url = (s.strip() for s in entry.partition("="))
            if not sep or not name or not url or name == DIRECT.name:
                logger.warning(
                    "%s: ignoring malformed egress entry %r (want name=url)",
                    env_var, entry,
                )
                continue
            routes.append(EgressRoute(name, url))
        return cls(tuple(routes))

    def preferring(self, name: str | None) -> tuple[EgressRoute, ...]:
        """The routes with *name* moved to the front, the rest in order."""
        return tuple(sorted(self.routes, key=lambda r: r.name != name))

    def __iter__(self) -> Iterator[EgressRoute]:
        return iter(self.routes)
