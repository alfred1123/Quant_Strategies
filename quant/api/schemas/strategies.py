"""Pydantic schemas for ``GET /api/v1/strategies`` — Phase 1.6."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class StrategyListRow(BaseModel):
    """One deployable BT.STRATEGY version for the Trade picker (caller-owned)."""

    strategy_id: UUID
    strategy_vid: int
    strategy_nm: str | None = None
    is_best_ind: str
    created_at: datetime
    sharpe_ratio: float | None = None
    calmar_ratio: float | None = None
    max_drawdown: float | None = None
    total_return: float | None = None
    annualized_return: float | None = None
