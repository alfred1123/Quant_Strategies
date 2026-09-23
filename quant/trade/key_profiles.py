"""Redis cache of what each venue says about an API key.

Cache-only by design: every field is re-derivable from one venue call, and a
stored copy would be a second truth that silently goes stale when the user
edits the key. The one fact that must outlive Redis — that a deployment was
paused because of the key — is already persisted as the deployment's state.

This module is broker-agnostic: it stores :class:`KeyProfile` under a key the
caller derives. How that key is built, and how a profile is learned, is the
broker's business (:mod:`quant.trade.brokers.ccxt.routing`).
"""

from __future__ import annotations

import json
import logging

import redis

from quant.trade.models.key_profile import KeyProfile

logger = logging.getLogger(__name__)

KEY_PROFILE_KEY_PREFIX = "key_profile:"
#: Long enough that a scheduled tick normally hits the cache, short enough
#: that display fields such as key expiry do not drift far. Correctness does
#: not depend on it: a stale route is caught on the next connect.
KEY_PROFILE_TTL_S = 86_400


class RedisKeyProfiles:
    """Key profiles in Redis with a TTL. An unreachable cache reads as empty."""

    def __init__(self, redis_url: str) -> None:
        # Short timeouts: a stalled cache must not hold up a tick, which can
        # always reconnect on the candidate routes instead.
        self._redis = redis.Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )

    def get(self, key: str) -> KeyProfile | None:
        try:
            raw = self._redis.get(key)
        except redis.RedisError:
            logger.debug("key profiles: read failed", exc_info=True)
            return None
        if not raw:
            return None
        try:
            return KeyProfile.from_json(json.loads(raw))
        except (ValueError, TypeError, KeyError):
            logger.warning("key profiles: unreadable entry %s — ignoring it", key)
            return None

    def put(self, key: str, profile: KeyProfile) -> None:
        try:
            self._redis.set(key, json.dumps(profile.to_json()), ex=KEY_PROFILE_TTL_S)
        except redis.RedisError:
            logger.warning("key profiles: write failed for %s", key, exc_info=True)
