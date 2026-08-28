"""A scheduled job must name a route that actually exists.

Two artefacts have to agree for a job to run, and nothing else checks them
against each other:

1. ``config/scheduler/*.yml`` declares a ``task`` and the ``path`` to post to,
2. FastAPI serves that path.

A mismatch is invisible until the schedule fires in production, where the Lambda
gets a 404 and the tick is lost — ``MaximumRetryAttempts`` is 0.

There used to be a third: a ``_TASK_PATHS`` map in the Lambda handler. The path
now travels in the schedule's event, built from these files by
``scripts/sync_schedules.py``, so the handler has no task knowledge left to
drift.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
import yaml

from quant.api.admin.router import router as admin_router
from quant.api.market_data.router import router as market_data_router
from quant.api.scheduler.router import router as scheduler_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDLER_PATH = PROJECT_ROOT / "aws" / "lambda" / "scheduled-task" / "handler.py"
SCHEDULE_DIR = PROJECT_ROOT / "config" / "scheduler"

#: Mounted under this prefix in ``quant.api.main``.
API_PREFIX = "/api/v1"

#: Every router the scheduler Lambda is allowed to reach. Each is mounted behind
#: ``require_user_or_service`` in ``quant.api.main``; a router gated by
#: ``require_user`` alone would 401 the Lambda's service token, so this tuple is
#: also the list of what a scheduled job may target.
SCHEDULED_ROUTERS = (admin_router, market_data_router, scheduler_router)


def _load_handler():
    """Import the Lambda handler by path — it is not on the package path."""
    spec = importlib.util.spec_from_file_location("scheduled_task_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def handler_module():
    return _load_handler()


@pytest.fixture(scope="module")
def served_paths() -> set[str]:
    return {
        API_PREFIX + route.path
        for router in SCHEDULED_ROUTERS
        for route in router.routes
    }


def _schedule_files() -> list[Path]:
    return sorted(SCHEDULE_DIR.glob("*.yml"))


def _job(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


class TestSchedulesNameServedRoutes:
    def test_at_least_one_schedule_is_defined(self):
        assert _schedule_files(), "no schedule YAML found — did config move?"

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_declares_a_task_and_a_path(self, path):
        """Both are required: the Lambda has no default for either."""
        job = _job(path)
        assert job.get("task"), f"{path.name} declares no task"
        assert job.get("path"), (
            f"{path.name} declares no path — the handler holds no task table, so "
            f"the schedule's event has to carry it."
        )

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_path_is_served_by_the_api(self, path, served_paths):
        job = _job(path)
        assert job["path"] in served_paths, (
            f"{path.name} posts to {job['path']}, which no scheduled router "
            f"serves. Either the route moved or its router is missing from "
            f"SCHEDULED_ROUTERS (and so from the service-token gate)."
        )

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_path_carries_the_api_prefix(self, path):
        """The Lambda joins API_BASE_URL to this verbatim, so it must be absolute."""
        assert _job(path)["path"].startswith(API_PREFIX)

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_path_needs_no_substitution(self, path):
        """A path with fields in it cannot be driven by a plain schedule.

        Scheduled routes act on everything currently due, which is what lets one
        schedule serve every deployment; a ``{deployment_id}`` would mean
        something has to create a schedule per row.
        """
        assert "{" not in _job(path)["path"]

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_no_schedule_targets_the_human_apply_route(self, path):
        """That route needs a user token; a schedule aimed at it could only 401."""
        assert not _job(path)["path"].endswith("/apply")

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_declares_an_expression_and_timezone(self, path):
        schedule = _job(path)["schedule"]
        assert schedule["expression"].startswith(("cron(", "rate(", "at("))
        assert schedule["timezone"]

    def test_tasks_are_unique(self):
        """The schedule name is derived from the task, so a clash overwrites."""
        tasks = [_job(p)["task"] for p in _schedule_files()]
        assert len(tasks) == len(set(tasks)), f"duplicate task names: {tasks}"


class TestHandlerHoldsNoTaskTable:
    def test_no_task_path_map_remains(self, handler_module):
        """The config is the only place a scheduled endpoint is named."""
        assert not hasattr(handler_module, "_TASK_PATHS")

    def test_no_module_constant_holds_an_api_path(self):
        """A path baked into the code would be one the config cannot move.

        Scoped to module-level assignments, which is where a task table lives —
        the docstring is free to show an example event.
        """
        tree = ast.parse(HANDLER_PATH.read_text())
        baked = [
            node.value
            for statement in tree.body
            if isinstance(statement, ast.Assign)
            for node in ast.walk(statement)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "/api/" in node.value
        ]
        assert not baked, f"handler hardcodes API path(s): {baked}"


class TestEventValidation:
    """The handler trusts the event for its path, so it has to check the shape."""

    def test_accepts_a_synced_event(self, handler_module):
        event = {"task": "price_bar_sync", "path": "/api/v1/market-data/price-bars/sync"}
        assert handler_module._resolve_task(event) == (
            "price_bar_sync",
            "/api/v1/market-data/price-bars/sync",
        )

    @pytest.mark.parametrize(
        "event",
        [
            {},
            {"task": "x"},
            {"path": "/api/v1/scheduler/tick"},
            {"task": "", "path": "/api/v1/scheduler/tick"},
            {"task": "x", "path": ""},
            {"task": "x", "path": None},
            {"task": None, "path": "/api/v1/scheduler/tick"},
        ],
    )
    def test_rejects_an_incomplete_event(self, handler_module, event):
        with pytest.raises(ValueError):
            handler_module._resolve_task(event)

    def test_rejects_a_non_object_event(self, handler_module):
        with pytest.raises(ValueError):
            handler_module._resolve_task(["trade_apply_tick"])

    @pytest.mark.parametrize(
        "bad_path",
        [
            "https://evil.example/steal",
            "//evil.example/steal",
            "api/v1/scheduler/tick",  # no leading slash
            "http://169.254.169.254/latest/meta-data/",
        ],
    )
    def test_rejects_a_path_that_could_redirect_the_token(self, handler_module, bad_path):
        """Every request carries the service token, so the event must not be
        able to choose the host it goes to."""
        with pytest.raises(ValueError, match="absolute path"):
            handler_module._resolve_task({"task": "x", "path": bad_path})


class TestSyncCarriesThePath:
    """``sync_schedules.py`` is what puts the config path into the event."""

    @pytest.fixture(scope="class")
    def sync_source(self) -> str:
        return (PROJECT_ROOT / "scripts" / "sync_schedules.py").read_text()

    def test_event_input_includes_task_and_path(self, sync_source):
        assert '"task": job["task"], "path": job["path"]' in sync_source

    def test_a_job_without_a_path_is_fatal(self, sync_source):
        """Skipping it would drop the schedule silently."""
        assert 'if not job.get("path")' in sync_source
        assert "sys.exit(" in sync_source
