"""Application configuration loader.

Priority (highest → lowest):
    1. AWS SSM Parameter Store  — when USE_SSM=1 (CI / production)
    2. .env file                — local development (python-dotenv)
    3. Hardcoded defaults       — fallback so the app starts without any config

Logging is also initialised here so that all subsequent imports see a
correctly formatted logger.

Usage (call once at process startup, before any other imports):
    from api.config import load_config
    load_config()
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

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


def _build_db_conninfo() -> str:
    """Build a psycopg connection string from env vars."""
    return os.getenv(
        "QUANTDB_CONNINFO",
        "host={host} port={port} dbname=quantdb user={user} password={password} sslmode=require".format(
            host=os.getenv("QUANTDB_HOST", "localhost"),
            port=os.getenv("QUANTDB_PORT", "5433"),
            user=os.getenv("QUANTDB_USERNAME", "quant_admin"),
            password=os.getenv("QUANTDB_PASSWORD", ""),
        ),
    )


def load_config(debug: bool = False) -> str:
    """Load configuration and initialise logging.

    Returns the psycopg DB connection string so callers don't need to
    rebuild it themselves.

    Args:
        debug: If True, set log level to DEBUG.

    Returns:
        DB connection string (str).
    """
    # Add src/ to import path so pipeline modules resolve correctly
    src_path = os.path.join(os.path.dirname(__file__), os.pardir, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Initialise logging first so subsequent log calls are formatted
    from src.log_config import setup_logging  # noqa: PLC0415
    setup_logging(debug=debug)

    # Load secrets / config
    use_ssm = os.getenv("USE_SSM", "").strip() == "1"
    if use_ssm:
        env = os.getenv("APP_ENV", "dev")
        _load_from_ssm(env)
    else:
        _load_from_dotenv()

    return _build_db_conninfo()
