"""Composes REFDATA reader + INST cache + BT cache into one bundle.

Used identically in FastAPI lifespan and the long-lived worker so the
same wiring is shared between API and queue processes.
"""

from __future__ import annotations

import logging

from quant.data.backtest_cache import BacktestCache
from quant.data.instruments import InstrumentCache
from quant.refdata.reader import RedisRefData

logger = logging.getLogger(__name__)


class DataCaches:
    """Redis REFDATA + INST + BT caches wired the same way in API and worker.

    ``BacktestCache`` uses the same ``RedisRefData`` instance as ``refdata``
    so REFDATA.APP / APP_METRIC resolution matches ``run_optimize``."""

    def __init__(self, conninfo: str, redis_url: str) -> None:
        self._conninfo = conninfo
        self.refdata = RedisRefData(redis_url)
        self.instrument_cache = InstrumentCache(conninfo)
        self.backtest_cache = BacktestCache(conninfo, refdata=self.refdata)

    @property
    def conninfo(self) -> str:
        return self._conninfo

    def require_redis(self) -> None:
        """Raise if Redis is not reachable (queue worker hard-requires REFDATA)."""
        if not self.refdata.ping():
            raise RuntimeError(f"Redis at {self.refdata.url} is not reachable")

    def load_instruments(self, *, soft_fail: bool = False) -> None:
        """Load all INST products into memory.

        ``soft_fail=True`` (worker): log warning and continue with empty/partial INST.
        ``soft_fail=False`` (API): log exception; same as historical ``api/main`` —
        server still boots with an unprepared ``InstrumentCache``.
        """
        try:
            self.instrument_cache.load_all()
        except Exception:
            if soft_fail:
                logger.warning(
                    "InstrumentCache load failed — proceeding without it",
                    exc_info=True,
                )
            else:
                logger.exception(
                    "Failed to load INST data — product endpoints will be empty",
                )
