"""Admin domain value objects — no I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StaleConnectionSweep:
    """Outcome of terminating idle quant_app Postgres backends."""

    stale: int
    terminated: int
