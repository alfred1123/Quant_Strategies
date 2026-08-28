"""EventBridge Scheduler → FastAPI task bridge.

One Lambda serves every scheduled API task. The schedule's event carries both
the task name and the path to post to; business logic stays in FastAPI::

    {"task": "trade_apply_tick", "path": "/api/v1/scheduler/tick"}

Both values come from ``config/scheduler/<task>.yml``, which
``scripts/sync_schedules.py`` reads when it creates or updates the schedule.
This file holds **no task table**. That is deliberate: a table here would be a
second copy of what the YAML already declares, and the two could disagree
silently — the schedule would fire and the Lambda would answer "unknown task",
or worse, post to a path the config had since moved. Adding a scheduled task is
now one YAML file, with no change to this handler and no Lambda redeploy.

The service token is read from SSM at cold start (CloudFormation cannot
inject SecureStrings into Lambda env vars, and runtime fetch keeps the
secret out of plaintext function config). boto3 is bundled in the Lambda
runtime — no packaging of third-party deps.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from functools import lru_cache

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    task, path = _resolve_task(event)
    api_base = os.environ["API_BASE_URL"].rstrip("/")
    timeout_s = float(os.environ.get("HTTP_TIMEOUT_S", "110"))

    url = f"{api_base}{path}"
    logger.info("task=%s url=%s", task, url)

    payload = json.dumps(event.get("payload") or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {_service_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "quant-scheduled-task-lambda/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "task=%s failed status=%s body=%s", task, exc.code, body[:500]
        )
        raise RuntimeError(f"{task} failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        logger.error("task=%s unreachable error=%s", task, exc)
        raise RuntimeError(f"{task} unreachable: {exc}") from exc

    logger.info("task=%s ok status=%s body=%s", task, status, body[:500])
    return {
        "task": task,
        "statusCode": status,
        "body": _safe_json(body),
    }


def _resolve_task(event) -> tuple[str, str]:
    """Validate the event and return its task name and API path."""
    if not isinstance(event, dict):
        raise ValueError(f"event must be an object, got {event!r}")

    task = event.get("task")
    if not task or not isinstance(task, str):
        raise ValueError(f"event.task must be a non-empty string, got {task!r}")

    path = event.get("path")
    if not path or not isinstance(path, str):
        raise ValueError(
            f"event.path must be a non-empty string. sync_schedules.py copies it "
            f"from config/scheduler/*.yml, so a schedule created by hand needs it "
            f"spelled out; got {path!r}"
        )

    # A path on our own API, never a URL. Every request leaves here with the
    # service token attached, so the event must not be able to choose the host
    # it is sent to — the one thing a free-form field could otherwise do.
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        raise ValueError(
            f"event.path must be an absolute path on the API, not a URL: {path!r}"
        )

    return task, path


@lru_cache(maxsize=1)
def _service_token() -> str:
    """Fetch the API service token from SSM once per Lambda container."""
    path = os.environ["TRADE_SERVICE_TOKEN_SSM_PATH"]
    param = boto3.client("ssm").get_parameter(Name=path, WithDecryption=True)
    return param["Parameter"]["Value"]


def _safe_json(raw: str):
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return raw
