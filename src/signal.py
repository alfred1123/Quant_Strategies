"""Backward-compatibility shim — Signal direction logic has moved to strat.py.

Note: 'signal' shadows a Python builtin module. Import from strat directly.
"""
from strat import SignalDirection, Strategy  # noqa: F401