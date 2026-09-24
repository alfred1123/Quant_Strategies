"""Service for ``/api/v1/backtest/promotions`` — read-only promotion log.

HTTP-agnostic. All DB access is delegated to :class:`PromotionRepo`.
The promotion log is not user-scoped (``USER_ID`` on ``BT.PROMOTION`` is
audit-only). The Trade strategy picker is owner-scoped; this list is not.
"""

import logging
import uuid

from quant.promotion.repo import PromotionRepo

logger = logging.getLogger(__name__)


class PromotionService:
    """Read promotion decision-log rows for the Promotion tab."""

    def __init__(self, repo: PromotionRepo) -> None:
        self._repo = repo

    def list_promotions(
        self, strategy_id: uuid.UUID | None = None, *, limit: int = 200
    ) -> list[dict]:
        """Promotion log newest-first; optionally scoped to one strategy."""
        return self._repo.sp_get_promotion(strategy_id, limit=limit)
