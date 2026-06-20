"""Business logic for ``GET /api/v1/strategies`` — Phase 1.6."""

from typing import Literal

from quant.queue.repo import BtQueueRepo

StrategyListVersions = Literal["best", "all"]


class StrategiesService:
    """Read-only strategy catalog for the Trade picker — caller-owned rows only."""

    def __init__(self, repo: BtQueueRepo) -> None:
        self._repo = repo

    def list_strategies(
        self,
        *,
        user_id: str,
        limit: int = 200,
        versions: StrategyListVersions = "best",
    ) -> list[dict]:
        is_best_ind = "Y" if versions == "best" else None
        return self._repo.sp_get_strategy_list(
            user_id=user_id,
            limit=limit,
            is_best_ind=is_best_ind,
        )
