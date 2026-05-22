"""Central logging configuration for all process entry points."""


import logging
import os

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _repo_root() -> str:
    # quant/shared/logging.py -> repo root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_LOG_DIR = os.path.join(_repo_root(), "log")
_LOG_FILE = os.path.join(_LOG_DIR, "bt_app.log")


def setup_logging(*, debug: bool = False) -> None:
    """Configure root logger once at process startup.

    Local dev: stdout + ``log/bt_app.log``.
    Prod / ``USE_SSM=1``: stdout only (container-friendly).
    """
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if os.getenv("APP_ENV", "dev").lower() != "prod" and not os.getenv("USE_SSM"):
        os.makedirs(_LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(_LOG_FILE))

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
        handlers=handlers,
    )
