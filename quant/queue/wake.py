"""Cross-process wake signal for the backtest queue.

Producers (FastAPI enqueue handler) call ``publish_wake()`` after inserting a
new row into ``BT.QUEUE``. Long-lived workers (``src.worker_loop``) sit on
``wait_for_wake()``; the call returns when a producer fires or the timeout
elapses (whichever comes first), so workers also poll periodically as a
safety net against missed wakes.

Implementation: Redis LIST with ``BLPOP`` semantics. Each producer pushes one
token, each worker pops one token. Multiple workers across processes/hosts
share the same key — the one that wins ``BLPOP`` is the one that wakes; the
others stay parked until the next push. Tokens piling up while workers are
busy is harmless: the next idle worker drains them in O(N) BLPOP calls.

Why not pub/sub: with N workers and M wakes, pub/sub fan-outs would wake all
N workers per message (thundering herd against ``claim_next``). LIST + BLPOP
gives at-most-one wake per token, which matches "one new job, one worker".
"""

import logging

import redis

logger = logging.getLogger(__name__)

WAKE_KEY = "bt:queue:wake"


def publish_wake(client: redis.Redis) -> None:
    """Notify exactly one parked worker that there may be a new job.

    Best-effort: a Redis outage logs a warning but does not raise — the
    worker's BLPOP timeout will still pick up the row on the next poll
    cycle, just with extra latency.
    """
    try:
        client.lpush(WAKE_KEY, "1")
    except redis.RedisError as exc:
        logger.warning("publish_wake failed: %s (worker will catch up via poll)", exc)


def wait_for_wake(client: redis.Redis, *, timeout: int = 30) -> bool:
    """Block until a wake token arrives or ``timeout`` seconds elapse.

    Returns ``True`` if a token was consumed, ``False`` on timeout. Callers
    should attempt a ``claim_next`` either way — the timeout is the safety
    net against missed wakes (e.g. Redis bounce, producer crash).
    """
    try:
        # BLPOP returns (key, value) on hit, None on timeout.
        return client.blpop([WAKE_KEY], timeout=timeout) is not None
    except redis.RedisError as exc:
        logger.warning("wait_for_wake failed: %s (treating as timeout)", exc)
        return False
