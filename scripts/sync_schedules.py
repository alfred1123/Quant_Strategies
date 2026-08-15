#!/usr/bin/env python3
"""Sync EventBridge Scheduler schedules from config/scheduler/*.yml.

Reads each YAML job definition, resolves Lambda ARN and invoke role from
the CFN scheduler stack outputs, then creates or updates the schedule.

Usage:
    python3 scripts/sync_schedules.py              # apply all
    python3 scripts/sync_schedules.py --dry-run    # preview only

Called automatically by aws/deploy.sh after the scheduler stack deploys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
import yaml

PROJECT = "quant"
REGION = "ap-southeast-1"
SCHEDULER_STACK = f"{PROJECT}-scheduler"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "scheduler"


def _get_stack_outputs(cfn, stack_name: str) -> dict[str, str]:
    resp = cfn.describe_stacks(StackName=stack_name)
    outputs = resp["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def _load_jobs() -> list[dict]:
    jobs = []
    for path in sorted(CONFIG_DIR.glob("*.yml")):
        with open(path) as f:
            job = yaml.safe_load(f)
        if not job or not job.get("task"):
            print(f"  SKIP {path.name}: missing 'task' field")
            continue
        job["_file"] = path.name
        jobs.append(job)
    return jobs


def _upsert_schedule(scheduler, *, name, group, expression, timezone,
                     description, target_arn, role_arn, event_input,
                     enabled, dry_run):
    state = "ENABLED" if enabled else "DISABLED"
    kwargs = dict(
        Name=name,
        GroupName=group,
        ScheduleExpression=expression,
        ScheduleExpressionTimezone=timezone,
        FlexibleTimeWindow={"Mode": "OFF"},
        State=state,
        Target={
            "Arn": target_arn,
            "RoleArn": role_arn,
            "Input": json.dumps(event_input),
            "RetryPolicy": {"MaximumRetryAttempts": 0},
        },
    )
    if description:
        kwargs["Description"] = description

    if dry_run:
        print(f"  DRY RUN  {name}  {expression}  state={state}")
        return

    try:
        scheduler.update_schedule(**kwargs)
        print(f"  UPDATED  {name}  {expression}  state={state}")
    except scheduler.exceptions.ResourceNotFoundException:
        scheduler.create_schedule(**kwargs)
        print(f"  CREATED  {name}  {expression}  state={state}")


def main():
    dry_run = "--dry-run" in sys.argv

    if not CONFIG_DIR.is_dir():
        print(f"No config directory at {CONFIG_DIR} — nothing to sync.")
        return

    jobs = _load_jobs()
    if not jobs:
        print("No job definitions found in config/scheduler/.")
        return

    cfn = boto3.client("cloudformation", region_name=REGION)
    outputs = _get_stack_outputs(cfn, SCHEDULER_STACK)

    lambda_arn = outputs.get("ScheduledTaskLambdaArn")
    role_arn = outputs.get("SchedulerInvokeRoleArn")
    group_name = outputs.get("SystemJobsScheduleGroupName")

    if not all([lambda_arn, role_arn, group_name]):
        print(f"ERROR: Missing CFN outputs from {SCHEDULER_STACK}.")
        print(f"  Found: {list(outputs.keys())}")
        sys.exit(1)

    scheduler = boto3.client("scheduler", region_name=REGION)

    print(f"Syncing {len(jobs)} schedule(s) → group={group_name}")
    for job in jobs:
        schedule = job.get("schedule", {})
        _upsert_schedule(
            scheduler,
            name=f"{PROJECT}-{job['task'].replace('_', '-')}",
            group=group_name,
            expression=schedule.get("expression", ""),
            timezone=schedule.get("timezone", "UTC"),
            description=job.get("description", ""),
            target_arn=lambda_arn,
            role_arn=role_arn,
            event_input={"task": job["task"]},
            enabled=job.get("enabled", True),
            dry_run=dry_run,
        )

    print("Done.")


if __name__ == "__main__":
    main()
