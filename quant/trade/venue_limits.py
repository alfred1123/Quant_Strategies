"""Cache each venue's order-size rules in Redis, one snapshot per broker app.

The ccxt adapter already checks the rules before it submits (see
``CcxtTradeAdapter._undersized``), but by then the only remedy left is to pause
the deployment: nobody is at the keyboard when a scheduled tick fires. Caching
the same rules where the API can reach them without a broker session moves the
refusal to the moment a person types the quantity.

``load_markets`` is public, so the publisher needs no credentials — and it is
already how :class:`MarketLimits` is sourced at order time, so the edit-time
answer and the order-time answer come from one place.

Key shape mirrors REFDATA's (``venue_limits:<app_id>`` plus a
``venue_limits:version`` stamp readers watch), so a long-lived API or worker
process picks up a refresh without pub/sub.
"""

from __future__ import annotations

import json
import logging

import redis

from quant.refdata.reader import RedisRefData
from quant.trade.brokers.ccxt.config import CcxtExchangePreset
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.models.market import MarketLimits
from quant.trade.registry import ccxt_apps

logger = logging.getLogger(__name__)

VENUE_LIMITS_KEY_PREFIX = "venue_limits:"
VENUE_LIMITS_VERSION_KEY = "venue_limits:version"


def _key(app_id: int) -> str:
    return f"{VENUE_LIMITS_KEY_PREFIX}{app_id}"


def _redis(url: str) -> redis.Redis:
    # Short timeouts: a stalled cache must not hold up an edit, which falls
    # back to the order-time check rather than failing.
    return redis.Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )


class VenueLimitsPublisher:
    """Snapshots every listed symbol's min lot and min notional, per app.

    One keyless ccxt session per broker app, so this costs one ``load_markets``
    per venue — seconds at API startup, and the reason it is also exposed as a
    refresh endpoint rather than run on a timer.
    """

    def __init__(self, redis_url: str, *, refdata: RedisRefData) -> None:
        self._redis = _redis(redis_url)
        self._refdata = refdata

    def publish_all(self) -> int:
        """Publish a snapshot per broker app; returns how many apps were written.

        One venue being unreachable must not cost the others their snapshot, so
        a failure is logged and skipped. Readers treat a missing app as "no
        rules known", which defers to the order-time check.
        """
        snapshots: dict[int, dict[str, MarketLimits]] = {}
        for app_id, preset in ccxt_apps(self._refdata):
            try:
                snapshots[app_id] = self._fetch(preset)
            except Exception:
                logger.warning(
                    "venue limits: %s unreachable — keeping any previous snapshot",
                    preset.exchange_label,
                    exc_info=True,
                )

        if not snapshots:
            return 0

        pipe = self._redis.pipeline(transaction=True)
        for app_id, limits in snapshots.items():
            pipe.set(_key(app_id), json.dumps(_encode(limits)))
        pipe.incr(VENUE_LIMITS_VERSION_KEY)
        pipe.execute()

        logger.info(
            "venue limits: published %s",
            ", ".join(
                f"app {app_id}={len(limits)} symbols"
                for app_id, limits in sorted(snapshots.items())
            ),
        )
        return len(snapshots)

    def _fetch(self, preset: CcxtExchangePreset) -> dict[str, dict[str, MarketLimits]]:
        """Limits per symbol, split by the default type ``ISSUE_TYPE`` selects.

        One id can be two markets. A flat symbol key would keep whichever
        market ccxt listed last, and the edit-time check would enforce the
        wrong lot.
        """
        gateway = CcxtTradeGateway(CcxtSessionConfig.public(preset))
        gateway.connect()
        try:
            default_types = list(dict.fromkeys(preset.default_type_by_issue.values())) or [None]
            merged: dict[str, dict[str, MarketLimits]] = {}
            for default_type in default_types:
                gateway.pin_default_type(default_type)
                label = default_type or "default"
                for symbol, limits in gateway.fetch_all_market_limits().items():
                    merged.setdefault(symbol, {})[label] = limits
            return merged
        finally:
            gateway.disconnect()


class RedisVenueLimits:
    """Read-only venue order-size rules, per broker app, out of Redis.

    Unknown app, unknown symbol, or an unreachable cache all yield empty limits,
    which enforce nothing: the ccxt adapter's pre-submit check is the authority,
    and a cache outage must not block an edit the venue would accept.

    Like :class:`RedisRefData`, the local snapshot is dropped when the publisher
    bumps ``venue_limits:version``.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = _redis(redis_url)
        self._by_app: dict[int, dict[str, dict[str, MarketLimits]]] = {}
        self._version: str | None = None

    def get(
        self, app_id: int, vendor_symbol: str, default_type: str | None = None
    ) -> MarketLimits:
        """The venue's rules for one symbol and default type.

        ``default_type`` is what the instrument's ``ISSUE_TYPE`` mapped to.
        When it is omitted and the symbol has exactly one default type, that
        rule is the answer. Several and no choice enforce nothing — guessing
        would apply the other product's lot.
        """
        self._check_version()
        snapshot = self._by_app.get(app_id)
        if snapshot is None:
            snapshot = self._load(app_id)
            self._by_app[app_id] = snapshot
        by_default_type = snapshot.get(vendor_symbol)
        if not by_default_type:
            return MarketLimits(symbol=vendor_symbol)
        if default_type is not None:
            rule = by_default_type.get(default_type)
            return rule if rule is not None else MarketLimits(symbol=vendor_symbol)
        if len(by_default_type) == 1:
            return next(iter(by_default_type.values()))
        return MarketLimits(symbol=vendor_symbol)

    def _check_version(self) -> None:
        try:
            version = self._redis.get(VENUE_LIMITS_VERSION_KEY)
        except redis.RedisError:
            logger.debug("venue limits: version read failed", exc_info=True)
            return
        if version != self._version:
            self._version = version
            self._by_app.clear()

    def _load(self, app_id: int) -> dict[str, dict[str, MarketLimits]]:
        try:
            raw = self._redis.get(_key(app_id))
        except redis.RedisError:
            logger.warning(
                "venue limits: Redis unreachable — qty edits fall back to the "
                "order-time check",
                exc_info=True,
            )
            return {}
        if not raw:
            return {}
        try:
            return _decode(json.loads(raw))
        except (ValueError, TypeError):
            logger.warning("venue limits: app %s snapshot is unreadable", app_id)
            return {}


def _encode(limits: dict[str, dict[str, MarketLimits]]) -> dict[str, dict]:
    """Symbol → default type → rules. The symbol stays the key; the default type splits it."""
    return {
        symbol: {
            default_type: {"min_qty": rule.min_qty, "min_notional": rule.min_notional}
            for default_type, rule in by_default_type.items()
        }
        for symbol, by_default_type in limits.items()
    }


def _decode(payload: dict) -> dict[str, dict[str, MarketLimits]]:
    decoded: dict[str, dict[str, MarketLimits]] = {}
    for symbol, by_default_type in payload.items():
        if not isinstance(by_default_type, dict):
            continue
        decoded[symbol] = {
            default_type: MarketLimits(
                symbol=symbol,
                min_qty=rule.get("min_qty"),
                min_notional=rule.get("min_notional"),
            )
            for default_type, rule in by_default_type.items()
            if isinstance(rule, dict)
        }
    return decoded
