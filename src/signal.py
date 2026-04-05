"""Backward-compatibility shim — Strategy signals have moved to strat.py.

Note: 'signal' shadows a Python builtin module. Import from strat directly.
"""
from strat import Strategy  # noqa: F401