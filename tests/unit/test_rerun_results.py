from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from quant.api.schemas.jobs import MAX_QUEUED_PER_USER
from scripts.rerun_results import parse_args, rerun_user, stale_versions

CUTOVER = datetime(2026, 9, 21, tzinfo=timezone.utc)
OLD = CUTOVER - timedelta(days=30)
NEW = CUTOVER + timedelta(minutes=5)


def _strategy(vid: int, name: str = "s"):
    return {"strategy_id": f"sid-{name}", "strategy_vid": vid, "strategy_nm": name}


def _repo(strategies, results):
    """``results`` maps ``(strategy_id, vid)`` to a created_at, or None for no result."""
    repo = MagicMock()
    repo.sp_get_strategy_list.return_value = strategies
    repo.sp_get_result_by_strategy.side_effect = lambda sid, vid: (
        None if results[(sid, vid)] is None else {"created_at": results[(sid, vid)]}
    )
    repo.sp_get_queued_count.return_value = 0
    return repo


class TestStaleVersions:
    def test_selects_results_older_than_cutover(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        assert stale_versions(repo, "u", CUTOVER) == [("sid-a", 1, "a")]

    def test_skips_results_already_migrated(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): NEW})
        assert stale_versions(repo, "u", CUTOVER) == []

    def test_cutover_boundary_counts_as_migrated(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): CUTOVER})
        assert stale_versions(repo, "u", CUTOVER) == []

    def test_skips_versions_that_never_ran(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): None})
        assert stale_versions(repo, "u", CUTOVER) == []

    def test_requests_every_vid_not_just_best(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        stale_versions(repo, "u", CUTOVER)
        assert repo.sp_get_strategy_list.call_args.kwargs["is_best_ind"] is None


class TestRerunUser:
    def _run(self, repo, **overrides):
        kwargs = dict(user_id="u", cutover=CUTOVER, priority=100, dry_run=False)
        kwargs.update(overrides)
        return rerun_user(repo, MagicMock(), 10, **kwargs)

    def test_enqueues_stale_versions(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        assert self._run(repo) == (1, 0)
        call = repo.sp_ins_queue.call_args.kwargs
        assert call["strategy_id"] == "sid-a"
        assert call["strategy_vid"] == 1
        assert call["status_id"] == 10

    def test_enqueues_as_the_strategy_owner(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        self._run(repo, user_id="owner-1")
        assert repo.sp_ins_queue.call_args.kwargs["user_id"] == "owner-1"

    def test_reuses_the_same_strategy_version(self):
        """A replay must not mint a new BT.STRATEGY version."""
        repo = _repo([_strategy(3, "a")], {("sid-a", 3): OLD})
        self._run(repo)
        repo.sp_ins_strategy.assert_not_called()
        assert repo.sp_ins_queue.call_args.kwargs["strategy_vid"] == 3

    def test_nothing_stale_is_a_no_op(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): NEW})
        assert self._run(repo) == (0, 0)
        repo.sp_ins_queue.assert_not_called()

    def test_dry_run_writes_nothing(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        assert self._run(repo, dry_run=True) == (1, 0)
        repo.sp_ins_queue.assert_not_called()

    def test_respects_the_per_user_queue_cap(self):
        n = MAX_QUEUED_PER_USER + 5
        strategies = [_strategy(1, f"s{i}") for i in range(n)]
        results = {(f"sid-s{i}", 1): OLD for i in range(n)}
        repo = _repo(strategies, results)
        assert self._run(repo) == (MAX_QUEUED_PER_USER, 5)

    def test_existing_queued_jobs_reduce_the_budget(self):
        strategies = [_strategy(1, f"s{i}") for i in range(4)]
        results = {(f"sid-s{i}", 1): OLD for i in range(4)}
        repo = _repo(strategies, results)
        repo.sp_get_queued_count.return_value = MAX_QUEUED_PER_USER - 2
        assert self._run(repo) == (2, 2)

    def test_full_queue_defers_everything(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        repo.sp_get_queued_count.return_value = MAX_QUEUED_PER_USER
        assert self._run(repo) == (0, 1)
        repo.sp_ins_queue.assert_not_called()

    def test_wakes_the_worker_only_after_enqueuing(self):
        repo = _repo([_strategy(1, "a")], {("sid-a", 1): OLD})
        client = MagicMock()
        rerun_user(repo, client, 10, user_id="u", cutover=CUTOVER,
                   priority=100, dry_run=False)
        client.lpush.assert_called_once()

        quiet = MagicMock()
        rerun_user(repo, quiet, 10, user_id="u", cutover=CUTOVER,
                   priority=100, dry_run=True)
        quiet.lpush.assert_not_called()


class TestParseArgs:
    def test_user_id_repeats(self):
        args = parse_args(["--user-id", "a", "--user-id", "b"])
        assert args.user_id == ["a", "b"]

    def test_user_id_is_required(self):
        with pytest.raises(SystemExit):
            parse_args([])

    def test_defaults(self):
        args = parse_args(["--user-id", "a"])
        assert args.priority == "normal"
        assert args.cutover is None
        assert args.dry_run is False
