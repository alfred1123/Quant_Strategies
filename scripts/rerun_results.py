#!/usr/bin/env python3
"""Re-run stored backtests so every ``BT.RESULT`` row shares one return convention.

Decision #73 replaced additive cumulative returns with a compounded equity
curve, moved drawdown onto that curve, and made the annualisation geometric.
The worker computes those metrics, so rows written before the change keep the
old numbers indefinitely — and promotion compares a candidate against the
stored current best, so any window where both conventions are live corrupts a
ranking that is otherwise self-consistent.

The rows cannot be recomputed in SQL: ``PAYLOAD_JSON`` holds the metric dicts
but not the per-bar position series an equity curve needs. Replay is the only
route, and it is safe because ``CONFIG_JSON`` carries the whole request
(``data_source`` per decision #53, ``tm_interval_id`` per #57).

**Run this only once the new ``quant-app`` image is serving.** A replay against
the old worker regenerates the old numbers, and this script would then read the
fresh timestamp and consider the row done.

Each job is enqueued against the same ``(STRATEGY_ID, STRATEGY_VID)`` as the
result it replaces, so no new strategy version is minted — only a new
``RESULT_VID``. Ownership is preserved: jobs are enqueued as the strategy's
owner so they appear in that user's job list and count against that user's cap.

Logically deleted strategies are skipped. ``SP_GET_STRATEGY_LIST`` omits them
by design (decision #66) and a retired strategy is not worth queue time; their
promotion history keeps the old figures.

Usage::

    python -m scripts.rerun_results --user-id <uuid> --dry-run
    python -m scripts.rerun_results --user-id <uuid> [--user-id <uuid>]

Re-runnable. Only versions whose current result predates ``--cutover`` are
enqueued, so a second invocation picks up whatever the per-user queue cap left
behind on the first.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

import redis

from quant.api.schemas.jobs import MAX_QUEUED_PER_USER, PRIORITY_MAP
from quant.queue.repo import BtQueueRepo
from quant.queue.wake import publish_wake
from quant.refdata.reader import RedisRefData
from quant.shared.config import load_config

logger = logging.getLogger(__name__)

AUDIT_USER = "rerun_results"


def stale_versions(
    repo: BtQueueRepo, user_id: str, cutover: datetime
) -> list[tuple[str, int, str]]:
    """``(strategy_id, strategy_vid, strategy_nm)`` whose result predates *cutover*.

    A version that never produced a result has nothing to bring forward and is
    not enqueued — this migration moves existing numbers onto the new
    convention, it does not backfill runs that were never made.
    """
    stale: list[tuple[str, int, str]] = []
    for row in repo.sp_get_strategy_list(user_id=user_id, limit=1000, is_best_ind=None):
        strategy_id, strategy_vid = row["strategy_id"], int(row["strategy_vid"])
        result = repo.sp_get_result_by_strategy(strategy_id, strategy_vid)
        if result is None:
            continue
        if result["created_at"] >= cutover:
            logger.debug("skip %s v%s — result already on the new convention",
                         row["strategy_nm"], strategy_vid)
            continue
        stale.append((str(strategy_id), strategy_vid, row["strategy_nm"]))
    return stale


def rerun_user(
    repo: BtQueueRepo,
    redis_client: redis.Redis,
    queued_status_id: int,
    *,
    user_id: str,
    cutover: datetime,
    priority: int,
    dry_run: bool,
) -> tuple[int, int]:
    """Enqueue one user's stale versions. Returns ``(enqueued, deferred)``."""
    stale = stale_versions(repo, user_id, cutover)
    if not stale:
        logger.info("user %s: nothing stale", user_id)
        return 0, 0

    # The per-user cap is what keeps one submitter from starving the queue.
    # A backfill has no claim to bypass it, so it takes whatever headroom is
    # free and reports the rest for the next invocation.
    in_flight = repo.sp_get_queued_count(user_id, queued_status_id)
    budget = max(MAX_QUEUED_PER_USER - in_flight, 0)
    batch, deferred = stale[:budget], stale[budget:]

    logger.info("user %s: %d stale, %d already queued, enqueuing %d",
                user_id, len(stale), in_flight, len(batch))

    for strategy_id, strategy_vid, strategy_nm in batch:
        if dry_run:
            logger.info("  DRY RUN  %s v%s", strategy_nm, strategy_vid)
            continue
        queue_id = uuid.uuid4()
        repo.sp_ins_queue(
            queue_id=queue_id,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            status_id=queued_status_id,
            priority=priority,
            user_id=user_id,
        )
        logger.info("  QUEUED   %s v%s  queue_id=%s", strategy_nm, strategy_vid, queue_id)

    if batch and not dry_run:
        publish_wake(redis_client)

    for strategy_id, strategy_vid, strategy_nm in deferred:
        logger.info("  DEFERRED %s v%s — queue cap reached", strategy_nm, strategy_vid)

    return len(batch), len(deferred)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--user-id", action="append", required=True, metavar="UUID",
        help="Strategy owner to migrate; repeat for several owners.",
    )
    parser.add_argument(
        "--cutover", metavar="ISO8601",
        help="Results created at or after this instant are treated as already "
             "migrated. Defaults to now, which marks every existing row stale.",
    )
    parser.add_argument(
        "--priority", choices=sorted(PRIORITY_MAP), default="normal",
        help="Queue priority for the replayed jobs (default: normal).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be enqueued and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # load_config() initialises logging and returns the DB conninfo.
    conninfo = load_config()

    if args.cutover:
        cutover = datetime.fromisoformat(args.cutover)
        if cutover.tzinfo is None:
            cutover = cutover.replace(tzinfo=timezone.utc)
    else:
        cutover = datetime.now(timezone.utc)

    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    refdata = RedisRefData(redis_url)
    redis_client = redis.Redis.from_url(redis_url)
    repo = BtQueueRepo(conninfo, user_id=AUDIT_USER)
    queued_status_id = refdata.resolve_queue_status_id("QUEUED")

    logger.info("cutover=%s priority=%s dry_run=%s",
                cutover.isoformat(), args.priority, args.dry_run)

    enqueued = deferred = 0
    for user_id in args.user_id:
        done, left = rerun_user(
            repo, redis_client, queued_status_id,
            user_id=user_id,
            cutover=cutover,
            priority=PRIORITY_MAP[args.priority],
            dry_run=args.dry_run,
        )
        enqueued += done
        deferred += left

    logger.info("enqueued %d, deferred %d", enqueued, deferred)
    if deferred:
        logger.info("re-run this script once the queue drains to pick up the rest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
