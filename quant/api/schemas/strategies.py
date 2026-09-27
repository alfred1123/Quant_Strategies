"""Pydantic schemas for ``GET /api/v1/strategies`` — Phase 1.6."""

from datetime import datetime
from typing import Any
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


class StrategyResult(BaseModel):
    """One version's frozen config and stored backtest payload."""

    strategy_id: UUID
    strategy_vid: int
    strategy_nm: str | None = None
    config_json: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
