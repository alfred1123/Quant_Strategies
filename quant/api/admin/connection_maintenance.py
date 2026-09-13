"""Orchestrate admin DB connection hygiene — sweep, alert, return."""

from __future__ import annotations

import logging

from quant.api.admin.connection_alerts import ConnectionMaintenanceAlertFormatter
from quant.api.admin.models import StaleConnectionSweep
from quant.api.admin.repo import ConnectionMaintenanceRepo, DEFAULT_STALE_IDLE_SECONDS
from quant.shared.notify import Notifier

logger = logging.getLogger(__name__)


class ConnectionMaintenanceService:
    """Terminate stale Postgres sessions and notify ops when any are found."""

    def __init__(
        self,
        repo: ConnectionMaintenanceRepo,
        *,
        alert_formatter: ConnectionMaintenanceAlertFormatter | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self._repo = repo
        self._alert_formatter = alert_formatter or ConnectionMaintenanceAlertFormatter()
        self._notifier = notifier or Notifier.from_env()

    def sweep_stale_connections(
        self,
        *,
        idle_seconds: int = DEFAULT_STALE_IDLE_SECONDS,
    ) -> StaleConnectionSweep:
        sweep = self._repo.terminate_stale_connections(idle_seconds=idle_seconds)
        if sweep.stale > 0:
            self._notifier.send(
                self._alert_formatter.format_stale_connection(
                    sweep=sweep,
                    idle_seconds=idle_seconds,
                ),
            )
        return sweep
