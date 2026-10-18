"""Standing requests to keep a provider series.

The Data tab reads :meth:`ProviderSubscrRepo.list_current`. The stored
window is joined inside ``MARKET_DATA.SP_GET_PROVIDER_SUBSCR`` on
``PROVIDER_SUBSCR_ID``. This module does not write a subscription.
"""

from __future__ import annotations

from quant.shared.db import DbGateway


class ProviderSubscrRepo(DbGateway):
    """SP wrapper for ``MARKET_DATA.PROVIDER_SUBSCR``."""

    def list_current(self) -> list[dict]:
        """Current subscriptions, including one whose window is not stored yet."""
        return self._call_get(
            "CALL market_data.sp_get_provider_subscr("
            "NULL::refcursor, NULL::text, NULL::text, NULL::text)",
            (),
        )
