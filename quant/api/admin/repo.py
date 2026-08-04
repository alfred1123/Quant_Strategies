"""Log-proc DB repository — wraps CORE_ADMIN.SP_INS_LOG_PROC_SUMMARY.

All writes go through stored procedures; no raw DML.
"""

from __future__ import annotations

import logging

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class LogProcRepo(DbGateway):
    """SP wrappers for CORE_ADMIN.LOG_PROC_SUMMARY."""

    def summarize(self, retention_days: int = 30) -> int:
        """Aggregate unsummarized LOG_PROC_DETAIL days into LOG_PROC_SUMMARY,
        then purge detail rows older than *retention_days*.

        Returns the number of summary rows inserted.
        """
        tail = self._call_write(
            "CALL CORE_ADMIN.SP_INS_LOG_PROC_SUMMARY(%s, %s, NULL, NULL, NULL, NULL)",
            (self.user_id, retention_days),
        )
        return int(tail[0]) if tail else 0
