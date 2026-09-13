"""Unit tests for :mod:`quant.api.admin.connection_maintenance`."""

from unittest.mock import MagicMock

from quant.api.admin.connection_alerts import ConnectionMaintenanceAlertFormatter
from quant.api.admin.connection_maintenance import ConnectionMaintenanceService
from quant.api.admin.models import StaleConnectionSweep


class TestSweepStaleConnections:
    def test_sends_slack_when_stale_found(self):
        repo = MagicMock()
        repo.terminate_stale_connections.return_value = StaleConnectionSweep(
            stale=2, terminated=2,
        )
        notifier = MagicMock()
        service = ConnectionMaintenanceService(
            repo,
            alert_formatter=ConnectionMaintenanceAlertFormatter(),
            notifier=notifier,
        )

        sweep = service.sweep_stale_connections(idle_seconds=3600)

        notifier.send.assert_called_once()
        assert "Found: 2" in notifier.send.call_args.args[0]
        assert sweep == StaleConnectionSweep(stale=2, terminated=2)
        repo.terminate_stale_connections.assert_called_once_with(idle_seconds=3600)

    def test_skips_slack_when_nothing_stale(self):
        repo = MagicMock()
        repo.terminate_stale_connections.return_value = StaleConnectionSweep(
            stale=0, terminated=0,
        )
        notifier = MagicMock()
        service = ConnectionMaintenanceService(repo, notifier=notifier)

        service.sweep_stale_connections(idle_seconds=3600)

        notifier.send.assert_not_called()
