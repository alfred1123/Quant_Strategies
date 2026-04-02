"""
Centralised logging configuration for the backtest pipeline.

Usage (entry points only):
    from log_config import setup_logging
    setup_logging()          # INFO level
    setup_logging(debug=True)  # DEBUG level
"""

import logging
import os

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
LOG_FILE = os.path.join(LOG_DIR, 'bt_app.log')


def setup_logging(*, debug: bool = False) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(),
        ],
    )
