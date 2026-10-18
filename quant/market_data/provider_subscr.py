"""Standing requests to keep a provider series.

The Data tab reads :meth:`ProviderSubscrRepo.sp_get_provider_subscr`. The
stored window is joined inside that procedure on ``PROVIDER_SUBSCR_ID``.
This module does not write a subscription.
"""

from __future__ import annotations

from quant.shared.db import DbGateway


class ProviderSubscrRepo(DbGateway):
    """SP wrapper for ``MARKET_DATA.PROVIDER_SUBSCR``."""

    def sp_get_provider_subscr(self) -> list[dict]:
        """Current rows, including one whose window is not stored yet."""
        return self._call_get(
            "CALL market_data.sp_get_provider_subscr("
            "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (),
        )
