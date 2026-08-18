"""The scheduler's task table must name routes that actually exist.

Three artefacts have to agree for a scheduled job to run, and nothing else
checks them against each other:

1. ``config/scheduler/*.yml`` names a ``task``,
2. the Lambda's ``_TASK_PATHS`` maps that task to an API path,
3. FastAPI serves that path.

A mismatch is invisible until the schedule fires in production, where the Lambda
gets a 404 and the tick is lost — ``MaximumRetryAttempts`` is 0.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from quant.api.admin.router import router as admin_router
from quant.api.market_data.router import router as market_data_router
from quant.api.routers import deployments

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDLER_PATH = PROJECT_ROOT / "aws" / "lambda" / "scheduled-task" / "handler.py"
SCHEDULE_DIR = PROJECT_ROOT / "config" / "scheduler"

#: Mounted under this prefix in ``quant.api.main``.
API_PREFIX = "/api/v1"

#: Every router the scheduler Lambda is allowed to reach.
SCHEDULED_ROUTERS = (admin_router, market_data_router, deployments.router)


def _load_handler():
    """Import the Lambda handler by path — it is not on the package path."""
    spec = importlib.util.spec_from_file_location("scheduled_task_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def task_paths() -> dict[str, str]:
    return _load_handler()._TASK_PATHS


@pytest.fixture(scope="module")
def served_paths() -> set[str]:
    return {
        API_PREFIX + route.path
        for router in SCHEDULED_ROUTERS
        for route in router.routes
    }


def _schedule_files() -> list[Path]:
    return sorted(SCHEDULE_DIR.glob("*.yml"))


class TestTaskPathsAreServed:
    def test_every_task_maps_to_a_real_route(self, task_paths, served_paths):
        missing = {
            task: path
            for task, path in task_paths.items()
            if path not in served_paths
        }
        assert not missing, (
            f"task paths with no matching route: {missing}. Either the route "
            f"moved or the router is not in SCHEDULED_ROUTERS."
        )

    def test_price_bar_sync_is_wired(self, task_paths, served_paths):
        """The warmer's endpoint specifically — it is the newest of the three."""
        path = task_paths["price_bar_sync"]
        assert path == "/api/v1/market-data/price-bars/sync"
        assert path in served_paths

    def test_paths_carry_the_api_prefix(self, task_paths):
        """The Lambda joins API_BASE_URL to these verbatim, so they must be absolute."""
        for task, path in task_paths.items():
            assert path.startswith(API_PREFIX), f"{task} is missing {API_PREFIX}"


class TestSchedulesNameKnownTasks:
    def test_at_least_one_schedule_is_defined(self):
        assert _schedule_files(), "no schedule YAML found — did config move?"

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_schedule_task_is_in_the_task_table(self, path, task_paths):
        job = yaml.safe_load(path.read_text())
        assert job["task"] in task_paths, (
            f"{path.name} schedules task {job['task']!r}, which the Lambda "
            f"cannot route — add it to _TASK_PATHS."
        )

    @pytest.mark.parametrize("path", _schedule_files(), ids=lambda p: p.stem)
    def test_schedule_declares_an_expression_and_timezone(self, path):
        schedule = yaml.safe_load(path.read_text())["schedule"]
        assert schedule["expression"].startswith(("cron(", "rate(", "at("))
        assert schedule["timezone"]
