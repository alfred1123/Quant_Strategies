"""Admin DB repositories — maintenance stored procedures only.

All writes go through stored procedures; no raw DML.
"""

from __future__ import annotations

import logging

from quant.api.admin.models import StaleConnectionSweep
from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)

DEFAULT_STALE_IDLE_SECONDS = 3600


class ConnectionMaintenanceRepo(DbGateway):
    """Terminate idle Postgres sessions owned by the runtime role."""

    def terminate_stale_connections(
        self,
        *,
        idle_seconds: int = DEFAULT_STALE_IDLE_SECONDS,
    ) -> StaleConnectionSweep:
        """Call ``CORE_ADMIN.SP_TERM_STALE_CONNECTIONS``.

        Returns how many stale backends were found and how many were terminated.
        """
        tail = self._call_write(
            "CALL CORE_ADMIN.SP_TERM_STALE_CONNECTIONS("
            "%s::text, %s::integer, NULL::text, NULL::text, NULL::text,"
            " NULL::integer, NULL::integer)",
            (self.user_id, idle_seconds),
        )
        if not tail:
            return StaleConnectionSweep(stale=0, terminated=0)
        return StaleConnectionSweep(stale=int(tail[0]), terminated=int(tail[1]))


class ApiRequestPayloadRepo(DbGateway):
    """Drop old ``BT.API_REQUEST_PAYLOAD`` partitions."""

    def detach(self, *, retention_days: int) -> int:
        """Call ``BT.SP_DETACH_API_REQUEST_PAYLOAD``.

        Returns how many partitions were dropped. The procedure does not
        write ``API_REQUEST``.
        """
        tail = self._call_write(
            "CALL BT.SP_DETACH_API_REQUEST_PAYLOAD("
            "%s::integer, NULL::text, NULL::text, NULL::text, NULL::integer)",
            (retention_days,),
        )
        return int(tail[0]) if tail else 0


class LogProcRepo(DbGateway):
    """SP wrappers for CORE_ADMIN.LOG_PROC_SUMMARY."""

    def summarize(self, retention_days: int = 30) -> int:
        """Aggregate unsummarized LOG_PROC_DETAIL days into LOG_PROC_SUMMARY,
        then purge detail rows older than *retention_days*.

        The window is a retention period, not a size cap: the table holds
        however many calls the platform makes in that span, which is why it
        reached 236,000 rows and 33 MB without anything being broken. Thirty
        days stays, because a month of per-call detail is the record you go
        back through when something looks wrong and nobody wrote down when it
        started. The size was addressed where it came from instead — the two
        procedures called in tight loops no longer log at all (decision #59).

        Returns the number of summary rows inserted.
        """
        tail = self._call_write(
            "CALL CORE_ADMIN.SP_INS_LOG_PROC_SUMMARY(%s, %s, NULL, NULL, NULL, NULL)",
            (self.user_id, retention_days),
        )
        return int(tail[0]) if tail else 0
