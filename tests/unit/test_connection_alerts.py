"""Unit tests for admin alert formatters."""

from quant.api.admin.connection_alerts import ConnectionMaintenanceAlertFormatter
from quant.api.admin.models import StaleConnectionSweep


class TestConnectionMaintenanceAlertFormatter:
    def setup_method(self):
        self.formatter = ConnectionMaintenanceAlertFormatter()

    def test_includes_found_and_terminated(self):
        msg = self.formatter.format_stale_connection(
            sweep=StaleConnectionSweep(stale=3, terminated=3),
            idle_seconds=3600,
        )
        assert msg.startswith("[DB] ")
        assert "Found: 3 idle > 1h (3600s)" in msg
        assert "Terminated: 3" in msg
        assert "Warning" not in msg

    def test_warns_when_termination_fails(self):
        msg = self.formatter.format_stale_connection(
            sweep=StaleConnectionSweep(stale=2, terminated=1),
            idle_seconds=3600,
        )
        assert "Warning: 1 backend(s) could not be terminated" in msg

    def test_sub_hour_threshold_shows_seconds(self):
        msg = self.formatter.format_stale_connection(
            sweep=StaleConnectionSweep(stale=1, terminated=1),
            idle_seconds=300,
        )
        assert "Found: 1 idle > 300s" in msg
