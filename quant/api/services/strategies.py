"""Business logic for ``GET /api/v1/strategies`` — Phase 1.6."""

import json
from typing import Any, Literal
from uuid import UUID

from quant.queue.repo import BtQueueRepo

StrategyListVersions = Literal["best", "all"]


class StrategyNotFound(Exception):
    """No ``BT.STRATEGY`` row for the requested id and version."""


def _as_object(value: Any) -> dict | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    return value if isinstance(value, dict) else None


class StrategiesService:
    """Read-only strategy catalog for the Trade picker — caller-owned rows only."""

    def __init__(self, repo: BtQueueRepo) -> None:
        self._repo = repo

    def get_result(self, strategy_id: UUID, strategy_vid: int) -> dict:
        """Stored backtest for one version.

        ``SP_GET_STRATEGY`` supplies the name and frozen config.
        ``SP_GET_RESULT`` supplies the payload, keyed by strategy id and vid.
        """
        rows = self._repo.sp_get_strategy(strategy_id, strategy_vid=strategy_vid)
        if not rows:
            raise StrategyNotFound(
                f"strategy {strategy_id} v{strategy_vid} not found"
            )
        row = rows[0]
        return {
            "strategy_id": row["strategy_id"],
            "strategy_vid": row["strategy_vid"],
            "strategy_nm": row.get("strategy_nm"),
            "config_json": _as_object(row.get("config_json")),
            "result": self._repo.fetch_result_payload(strategy_id, strategy_vid),
        }

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
