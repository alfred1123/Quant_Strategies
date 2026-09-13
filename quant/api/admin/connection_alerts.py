"""Presentation layer for admin ops alerts."""

from __future__ import annotations

from quant.api.admin.models import StaleConnectionSweep
from quant.shared.notify import AlertCategory, prefix_alert


class ConnectionMaintenanceAlertFormatter:
    """Format Slack bodies for admin DB maintenance events."""

    def format_stale_connection(
        self,
        *,
        sweep: StaleConnectionSweep,
        idle_seconds: int,
    ) -> str:
        """Plain-text Slack body when idle quant_app sessions are found."""
        hours = idle_seconds / 3600
        threshold = f"{idle_seconds}s" if hours < 1 else f"{hours:g}h ({idle_seconds}s)"
        lines = [
            "*Stale Postgres connections detected (quant_app)*",
            f"Found: {sweep.stale} idle > {threshold}",
            f"Terminated: {sweep.terminated}",
        ]
        if sweep.stale != sweep.terminated:
            lines.append(
                f"Warning: {sweep.stale - sweep.terminated} backend(s) could not be terminated"
            )
        return prefix_alert(AlertCategory.DB, "\n".join(lines))
