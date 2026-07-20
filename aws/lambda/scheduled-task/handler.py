"""EventBridge Scheduler → FastAPI task bridge.

One Lambda serves every scheduled API task. The event names the task and
carries the path fields; business logic stays in FastAPI::

    {"task": "trade_apply", "deployment_id": "<uuid>"}

Adding a scheduled task (e.g. price-bar ingestion) is one entry in
``_TASK_PATHS`` — no new Lambda or stack change.

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

# POST endpoints on the FastAPI app; formatted with fields from the event.
_TASK_PATHS = {
    "trade_apply": "/api/v1/trade/deployments/{deployment_id}/apply",
    # Phase 1.9 follow-up — price-bar ingestion, once the endpoint exists:
    # "price_bar_sync": "/api/v1/market-data/price-bars/sync",
}


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
    """Validate the event and build the API path for its task."""
    if not isinstance(event, dict):
        raise ValueError(f"event must be an object, got {event!r}")
    task = event.get("task")
    template = _TASK_PATHS.get(task)
    if template is None:
        raise ValueError(
            f"event.task must be one of {sorted(_TASK_PATHS)}, got {task!r}"
        )
    try:
        return task, template.format(**event)
    except KeyError as exc:
        raise ValueError(f"task {task!r} requires event field {exc}") from exc


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
