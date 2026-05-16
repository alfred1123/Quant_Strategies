"""Unit tests for ``quant.queue.worker_loop`` — Phase A v6 daemon."""

import uuid
from unittest.mock import MagicMock

import pytest

from quant.queue.worker_loop import WorkerLoop


# ── shared fakes ────────────────────────────────────────────────────────


class FakeRefData:
    """Stub for ``RedisRefData.resolve_queue_status_id`` only."""

    _IDS = {"QUEUED": 1, "RUNNING": 2, "COMPLETED": 3, "FAILED": 4, "CANCELLED": 5}

    def resolve_queue_status_id(self, name: str) -> int:
        return self._IDS[name]


class FakeProc:
    """Minimal Popen stand-in — controls ``poll()`` return."""

    def __init__(self, returncode=None, pid=12345):
        self._returncode = returncode
        self.returncode = returncode
        self.pid = pid
        self.killed = False
        self.waited = False

    def poll(self):
        return self._returncode

    def finish(self, code=0):
        self._returncode = code
        self.returncode = code

    def wait(self, timeout=None):
        self.waited = True
        return self.returncode

    def kill(self):
        self.killed = True


def _row(queue_id=None, *, priority=0, sid=None, vid=1, user="u1"):
    return {
        "queue_id": queue_id or uuid.uuid4(),
        "strategy_id": sid or uuid.uuid4(),
        "strategy_vid": vid,
        "priority": priority,
        "user_id": user,
    }


def _make_loop(*, repo=None, refdata=None, spawn_fn=None, max_concurrent=1):
    """Build a WorkerLoop with all externals stubbed."""
    return WorkerLoop(
        db_url="postgresql://stub",
        redis_url="redis://stub",
        max_concurrent=max_concurrent,
        spawn_fn=spawn_fn or (lambda qid: FakeProc()),
        repo=repo or MagicMock(),
        refdata=refdata or FakeRefData(),
        redis_client=MagicMock(),
    )


# ── recover_stale ──────────────────────────────────────────────────────


class TestRecoverStale:
    def test_marks_each_running_row_failed(self):
        repo = MagicMock()
        rows = [_row(), _row(), _row()]
        repo.list_by_status.return_value = rows
        loop = _make_loop(repo=repo)

        n = loop.recover_stale()

        assert n == 3
        repo.list_by_status.assert_called_once_with(2)  # RUNNING id
        assert repo.mark_failed.call_count == 3
        for call, row in zip(repo.mark_failed.call_args_list, rows):
            args = call.args
            assert args[0] == row["queue_id"]
            assert args[5] == 4  # FAILED id
            assert "worker_loop restarted" in args[6]

    def test_zero_running_returns_zero(self):
        repo = MagicMock()
        repo.list_by_status.return_value = []
        loop = _make_loop(repo=repo)

        assert loop.recover_stale() == 0
        repo.mark_failed.assert_not_called()


# ── _try_claim_and_spawn ───────────────────────────────────────────────


class TestClaimAndSpawn:
    def test_spawns_when_job_available(self):
        repo = MagicMock()
        row = _row()
        repo.claim_next.return_value = row
        spawned = []
        loop = _make_loop(
            repo=repo,
            spawn_fn=lambda qid: spawned.append(qid) or FakeProc(),
        )

        assert loop._try_claim_and_spawn() is True
        repo.claim_next.assert_called_once_with(1, 2)  # QUEUED, RUNNING
        assert spawned == [uuid.UUID(str(row["queue_id"]))]
        assert uuid.UUID(str(row["queue_id"])) in loop._active

    def test_no_spawn_when_queue_empty(self):
        repo = MagicMock()
        repo.claim_next.return_value = None
        spawned = []
        loop = _make_loop(
            repo=repo,
            spawn_fn=lambda qid: spawned.append(qid) or FakeProc(),
        )

        assert loop._try_claim_and_spawn() is False
        assert spawned == []
        assert loop._active == {}


# ── tick ────────────────────────────────────────────────────────────────


class TestTick:
    def test_fills_to_max_concurrent(self):
        repo = MagicMock()
        rows = [_row(), _row(), _row()]
        repo.claim_next.side_effect = rows + [None]
        loop = _make_loop(repo=repo, max_concurrent=2)
        loop._running = True

        loop.tick()

        assert len(loop._active) == 2
        assert repo.claim_next.call_count == 2

    def test_stops_when_queue_drains(self):
        repo = MagicMock()
        repo.claim_next.side_effect = [_row(), None]
        loop = _make_loop(repo=repo, max_concurrent=5)
        loop._running = True

        loop.tick()

        assert len(loop._active) == 1
        assert repo.claim_next.call_count == 2  # one hit + one miss

    def test_does_not_claim_when_at_capacity(self):
        repo = MagicMock()
        loop = _make_loop(repo=repo, max_concurrent=1)
        loop._running = True
        loop._active[uuid.uuid4()] = FakeProc()  # already at capacity, still running

        loop.tick()

        repo.claim_next.assert_not_called()

    def test_reaps_finished_children_before_claiming(self):
        repo = MagicMock()
        repo.claim_next.side_effect = [_row(), None]
        loop = _make_loop(repo=repo, max_concurrent=1)
        loop._running = True

        done = FakeProc(returncode=0)
        old_qid = uuid.uuid4()
        loop._active[old_qid] = done

        loop.tick()

        assert old_qid not in loop._active  # reaped
        assert len(loop._active) == 1  # one new child spawned
        repo.claim_next.assert_called()

    def test_does_not_spawn_when_not_running(self):
        repo = MagicMock()
        repo.claim_next.return_value = _row()
        loop = _make_loop(repo=repo, max_concurrent=2)
        loop._running = False

        loop.tick()

        repo.claim_next.assert_not_called()


# ── _drain ──────────────────────────────────────────────────────────────


class TestDrain:
    def test_waits_for_each_active_child(self):
        loop = _make_loop()
        p1, p2 = FakeProc(returncode=0), FakeProc(returncode=0)
        loop._active = {uuid.uuid4(): p1, uuid.uuid4(): p2}

        loop._drain()

        assert p1.waited and p2.waited
        assert not p1.killed and not p2.killed

    def test_kills_children_that_exceed_timeout(self):
        import subprocess

        loop = _make_loop()
        slow = FakeProc(returncode=None)
        slow.wait = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1))
        loop._active = {uuid.uuid4(): slow}

        loop._drain()

        assert slow.killed


# ── stop ────────────────────────────────────────────────────────────────


class TestStop:
    def test_flips_running_flag(self):
        loop = _make_loop()
        loop._running = True
        loop.stop()
        assert loop._running is False

    def test_idempotent_when_already_stopped(self):
        loop = _make_loop()
        loop._running = False
        loop.stop()  # no exception
        assert loop._running is False
