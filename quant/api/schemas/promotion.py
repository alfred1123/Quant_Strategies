"""Pydantic schemas for ``/api/v1/backtest/promotions``.

Mirrors the ``BT.PROMOTION`` decision log plus the resolved STRATEGY_NM.
``gate_results`` is the point-in-time hard-gate snapshot persisted by the
worker (see ``quant/promotion/evaluate.py``).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GateResultRow(BaseModel):
    name: str
    passed: bool
    value: float | None = None
    threshold: float | None = None


class PromotionRow(BaseModel):
    promotion_id: UUID
    queue_id: UUID
    strategy_id: UUID
    strategy_vid: int
    strategy_nm: str | None = None
    is_best_ind: str | None = None
    logical_delete_ind: str | None = None
    outcome: str
    compared_vid: int | None = None
    gate_results: list[GateResultRow] | None = None
    sharpe_ratio: float | None = None
    calmar_ratio: float | None = None
    max_drawdown: float | None = None
    total_return: float | None = None
    annualized_return: float | None = None
    user_id: str
    created_at: datetime
