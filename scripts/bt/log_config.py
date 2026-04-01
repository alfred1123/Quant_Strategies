"""
Centralised logging configuration for the backtest pipeline.

Usage (entry points only):
    from log_config import setup_logging
    setup_logging()          # INFO level
    setup_logging(debug=True)  # DEBUG level
"""

import logging

LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'


def setup_logging(*, debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
    )
