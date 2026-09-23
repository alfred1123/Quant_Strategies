"""Which egress route each API key accepts, decided by asking the venue.

A key pinned to one source IP fails from any other, and the user sets that pin
at the venue without telling us — so the route is never configured per key.
:class:`KeyRouter` connects on the candidate routes (:class:`~quant.trade.brokers.
ccxt.egress.EgressRoutes`) in turn and keeps whichever the venue accepts.

Profiles are cached by a fingerprint of the API key rather than the credential
row: the allowlist belongs to the key, and rotating keys moves to a fresh entry
without any invalidation step.
"""

from __future__ import annotations

import hashlib
import logging

from quant.trade.brokers.ccxt.egress import EgressRoutes
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import BrokerAuthError
from quant.trade.key_profiles import KEY_PROFILE_KEY_PREFIX, RedisKeyProfiles
from quant.trade.models.key_profile import KeyProfile
from quant.trade.models.order import OrderRejectReason

logger = logging.getLogger(__name__)


def _environment(session: CcxtSessionConfig) -> str:
    if session.demo:
        return "demo"
    return "paper" if session.paper else "live"


def profile_key(session: CcxtSessionConfig) -> str:
    """``key_profile:<exchange>:<env>:<fingerprint>`` — never the key itself."""
    fingerprint = hashlib.sha256(session.api_key.encode()).hexdigest()[:16]
    return (
        f"{KEY_PROFILE_KEY_PREFIX}{session.preset.exchange_id}:"
        f"{_environment(session)}:{fingerprint}"
    )


class KeyRouter:
    """Connects a keyed session on whichever route the venue accepts its key from.

    The route is decided on the session's real connection, not a side probe:
    ``load_markets`` is public and succeeds from anywhere, so the key-information
    call right after it is the first request the allowlist can refuse. The
    cached route is tried first, so a steady key costs that one extra call.

    An IP refusal moves on to the next route; anything else (proxy down, venue
    unreachable, bad key) stops, because falling back past an outage would send
    the next request from an address the key may reject — a clear
    infrastructure error turned into a confusing auth one.

    ``store=None`` routes without a cache: every connect re-asks the venue.
    """

    def __init__(self, store: RedisKeyProfiles | None) -> None:
        self._store = store

    def connect(self, gateway: CcxtTradeGateway) -> KeyProfile:
        """Leave *gateway* connected on the accepted route; return what the venue said."""
        session = gateway.session
        key = profile_key(session)
        cached = self._store.get(key) if self._store else None
        routes = EgressRoutes.from_env(session.preset.exchange_id).preferring(
            cached.route if cached else None
        )

        refused: list[str] = []
        for route in routes:
            gateway.connect(route)
            try:
                info = gateway.fetch_api_key_info()
            except BrokerAuthError as exc:
                # The caller connects inside ``with``, and an exception out of
                # ``__enter__`` skips ``__exit__`` — so close here, whether we
                # move on or give up.
                gateway.disconnect()
                if exc.reason is not OrderRejectReason.IP_NOT_ALLOWED:
                    raise
                refused.append(route.name)
                continue
            except Exception:
                gateway.disconnect()
                raise
            if info is None and len(routes) > 1:
                logger.warning(
                    "%s has no key-information call, so its egress routes cannot "
                    "be verified — using %s",
                    session.preset.exchange_label, route.name,
                )
            profile = KeyProfile.accepted(route.name, info, carrying=cached)
            if self._store:
                self._store.put(key, profile)
            if cached is not None and cached.route != route.name:
                logger.info(
                    "%s key moved egress route %s → %s",
                    session.preset.exchange_label, cached.route, route.name,
                )
            return profile

        raise BrokerAuthError(
            f"{session.preset.exchange_label} refused this key's source IP on every "
            f"egress route ({', '.join(refused)}). Add one of the platform's egress "
            "IPs to the key's allowlist at the venue.",
            reason=OrderRejectReason.IP_NOT_ALLOWED,
        )

    def record_restriction(
        self, session: CcxtSessionConfig, profile: KeyProfile, market_type: str
    ) -> KeyProfile:
        """Remember that the venue refused *market_type* for this key's account.

        Returns the updated profile so the caller's in-memory copy agrees with
        the cache for the rest of the session.
        """
        restricted = profile.restricting(market_type)
        if self._store is not None:
            self._store.put(profile_key(session), restricted)
        return restricted
