"""Run order is priority then enqueue time, on top of a newest-first read."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from quant.queue.repo import BtQueueRepo, in_run_order
from quant.queue.worker_loop import WorkerLoopRepo


def _row(queue_id: str, priority: int, submitted: str) -> dict:
    return {
        "queue_id": queue_id,
        "strategy_id": "00000000-0000-0000-0000-000000000001",
        "strategy_vid": 1,
        "priority": priority,
        "transact_from_ts": datetime.fromisoformat(submitted).replace(tzinfo=timezone.utc),
        "user_id": "alice",
    }


def test_newer_row_does_not_jump_an_older_one_at_the_same_priority():
    newest = _row("new", 100, "2026-09-26T10:00:00")
    oldest = _row("old", 100, "2026-08-30T10:00:00")
    assert in_run_order([newest, oldest])[0]["queue_id"] == "old"


def test_lower_priority_number_runs_before_an_older_normal_job():
    run_now = _row("now", 0, "2026-09-26T10:00:00")
    waiting = _row("old", 100, "2026-08-30T10:00:00")
    assert [r["queue_id"] for r in in_run_order([waiting, run_now])] == ["now", "old"]


def test_queued_position_counts_jobs_that_should_run_first():
    repo = BtQueueRepo("postgresql://test")
    newest = _row("new", 100, "2026-09-26T10:00:00")
    oldest = _row("old", 100, "2026-08-30T10:00:00")
    repo.sp_get_queue = MagicMock(return_value=[newest, oldest])
    assert repo.queued_position("new", 1) == 2
    assert repo.queued_position("old", 1) == 1


def test_claim_takes_the_oldest_even_when_the_read_is_newest_first():
    repo = WorkerLoopRepo("postgresql://test")
    newest = _row("new", 100, "2026-09-26T10:00:00")
    oldest = _row("old", 100, "2026-08-30T10:00:00")
    repo.list_by_status = MagicMock(return_value=[newest, oldest])
    repo.sp_ins_queue = MagicMock()
    claimed = repo.claim_next(1, 2)
    assert claimed["queue_id"] == "old"
    repo.sp_ins_queue.assert_called_once()
    assert repo.sp_ins_queue.call_args.kwargs["queue_id"] == "old"
