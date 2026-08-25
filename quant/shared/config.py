"""Application configuration loader.

Priority (highest → lowest):
    1. AWS SSM Parameter Store  — when USE_SSM=1 (CI / production)
    2. .env file                — local development (python-dotenv)
    3. ``config/db-targets.json`` — what ``local`` and ``prod`` mean

Which database a process talks to is chosen by ``DB_TARGET`` alone
(``local`` or ``prod``); ``config/db-targets.json`` declares both, and
``scripts/lib/db-target.sh`` resolves them identically for shell entry points.

Logging is configured in ``quant.shared.logging`` and invoked from
``load_config()`` so subsequent imports see a correctly formatted logger.

Usage (call once at process startup):
    from quant.shared.config import load_config
    load_config()
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from quant.shared.logging import setup_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSM / env loading
# ---------------------------------------------------------------------------

# SSM path prefix — all parameters are stored as /quant/<env>/<KEY>
_SSM_PREFIX = "/quant/{env}/"


def _load_from_ssm(env: str) -> None:
    """Fetch all parameters under /quant/<env>/ and set them as env vars."""
    import boto3

    prefix = _SSM_PREFIX.format(env=env)
    ssm = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "ap-southeast-1"))
    paginator = ssm.get_paginator("get_parameters_by_path")
    for page in paginator.paginate(Path=prefix, WithDecryption=True):
        for param in page["Parameters"]:
            key = param["Name"].removeprefix(prefix)   # e.g. QUANTDB_PASSWORD
            os.environ.setdefault(key, param["Value"])
    logger.info("Loaded config from SSM path %s", prefix)


def _load_from_dotenv() -> None:
    """Load .env from project root (no-op if file is absent)."""
    from dotenv import load_dotenv
    load_dotenv()
    logger.debug("Loaded config from .env")


def _ensure_connect_timeout(conninfo: str, *, seconds: int) -> str:
    """Append ``connect_timeout`` if the DSN does not already set it."""
    if "connect_timeout=" in conninfo.lower():
        return conninfo
    sep = "" if conninfo.endswith((" ", "\n", "\t")) else " "
    return f"{conninfo}{sep}connect_timeout={seconds}"


LOCAL = "local"
PROD = "prod"

#: Declares what ``local`` and ``prod`` actually mean — host, port, database,
#: user, TLS — and which environment variables override each field.
#: ``scripts/lib/db-target.sh`` reads the same file, so the shell entry points
#: and the app cannot disagree about where a target points.
DB_TARGETS_PATH = Path(__file__).resolve().parents[2] / "config" / "db-targets.json"


@lru_cache(maxsize=1)
def _db_targets() -> dict:
    try:
        with open(DB_TARGETS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        # Most likely a container image that did not COPY it — the app cannot
        # guess a database, so say which file is missing rather than fall back
        # to defaults that would silently duplicate this one.
        raise RuntimeError(
            f"missing {DB_TARGETS_PATH}: it declares the local and prod "
            "databases and must ship with the application"
        ) from exc


def db_target() -> str:
    """Which database this process talks to — ``local`` or ``prod``.

    Defaults to the file's ``default_target`` (``prod``), so a fresh checkout
    with no ``.env`` still points somewhere real.
    """
    spec = _db_targets()
    target = os.getenv("DB_TARGET", "").strip().lower() or spec["default_target"]
    if target not in spec["targets"]:
        valid = ", ".join(sorted(spec["targets"]))
        raise ValueError(f"DB_TARGET must be one of {valid} — got {target!r}")
    return target


def db_settings(target: str | None = None) -> dict:
    """Resolved connection settings for *target* (default: :func:`db_target`).

    Each field takes the first environment variable listed for it that is set,
    then falls back to the file's default. That layering is what lets one
    ``prod`` entry serve both a laptop on the SSM tunnel (port 5433, the
    default) and the EC2 host talking to Aurora directly (port 5432, supplied
    by SSM as ``QUANTDB_PORT``).
    """
    target = target or db_target()
    spec = _db_targets()["targets"][target]

    resolved = {"target": target, "sslmode": spec["sslmode"]}
    for field, rule in spec["fields"].items():
        value = next(
            (os.environ[var] for var in rule["env"] if os.environ.get(var)),
            rule["default"],
        )
        resolved[field] = "" if value is None else str(value)

    if target == PROD:
        _reject_local_masquerading_as_prod(resolved)
    return resolved


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _reject_local_masquerading_as_prod(resolved: dict) -> None:
    """Fail when ``prod`` resolves to the address the local database owns.

    Reachable through a stale ``QUANTDB_PORT`` in .env, and the failure it
    prevents is the worst kind: writes labelled prod landing in the laptop
    dump, or a "prod check" reporting local rows. Loopback *and* the local
    port together can only be the local database, so this cannot fire on EC2,
    where prod is the cluster endpoint rather than loopback.
    """
    local_port = _db_targets()["targets"][LOCAL]["fields"]["port"]["default"]
    if resolved["host"] in _LOOPBACK and resolved["port"] == str(local_port):
        raise ValueError(
            f"DB_TARGET=prod resolved to {resolved['host']}:{resolved['port']}, "
            f"which is the local database (port {local_port}). Prod on a laptop "
            "goes through the SSM tunnel on port "
            f"{_db_targets()['targets'][PROD]['fields']['port']['default']} — "
            "unset QUANTDB_PORT in .env, or set DB_TARGET=local if that is what "
            "you meant."
        )


def _build_db_conninfo() -> str:
    """Build a psycopg connection string for the selected target.

    ``QUANTDB_CONNINFO`` still wins when set — it is the deliberate escape
    hatch for a DSN that this file cannot express.
    """
    settings = db_settings()
    raw = os.getenv("QUANTDB_CONNINFO") or (
        "host={host} port={port} dbname={dbname} user={user} "
        "password={password} sslmode={sslmode}".format(**settings)
    )
    logger.info(
        "DB_TARGET=%s → %s:%s/%s (sslmode=%s)",
        settings["target"], settings["host"], settings["port"],
        settings["dbname"], settings["sslmode"],
    )
    sec = int(os.getenv("QUANTDB_CONNECT_TIMEOUT", "15"))
    return _ensure_connect_timeout(raw, seconds=sec)


DEFAULT_REDIS_URL = "redis://localhost:6379"


def get_redis_url() -> str:
    """Return the Redis URL from env (REDIS_URL), defaulting to localhost."""
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def load_config(debug: bool = False) -> str:
    """Load configuration and initialise logging.

    Returns the psycopg DB connection string so callers don't need to
    rebuild it themselves.

    Args:
        debug: If True, set log level to DEBUG.

    Returns:
        DB connection string (str).
    """
    # Initialise logging first so subsequent log calls are formatted
    setup_logging(debug=debug)

    # Load secrets / config
    use_ssm = os.getenv("USE_SSM", "").strip() == "1"
    if use_ssm:
        env = os.getenv("APP_ENV", "dev")
        try:
            _load_from_ssm(env)
        except Exception as exc:
            logger.warning("SSM unavailable (%s), falling back to .env", exc)
            _load_from_dotenv()
    else:
        _load_from_dotenv()

    # Built after loading, not before: DB_TARGET itself usually comes from
    # .env, and db_settings() reads the variables that load just supplied.
    return _build_db_conninfo()
