"""Strategy catalog and lifecycle — read, promote, logically delete.

The routes live under ``/strategies`` and ``/backtest/jobs/strategies/{id}``;
the logic lives here because every one of them is about a ``BT.STRATEGY``
lineage, not about a queue row.
"""

import json
from typing import Any, Literal
from uuid import UUID

from quant.promotion.repo import PromotionRepo
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

    def __init__(self, repo: BtQueueRepo, promotion: PromotionRepo | None = None) -> None:
        self._repo = repo
        self._promotion = promotion

    def _require_owned_lineage(self, user_id: str, strategy_id: UUID) -> None:
        """The caller must have a queue row for this ``strategy_id``.

        The ownership gate for every lifecycle write; a strategy nobody
        enqueued under this user is not theirs to promote or hide.
        """
        if not self._repo.sp_get_queue(strategy_id=strategy_id, user_id=user_id, limit=1):
            raise StrategyNotFound(str(strategy_id))

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

    # ── lifecycle writes ──────────────────────────────────────────────

    def promote(self, user_id: str, strategy_id: UUID, strategy_vid: int) -> None:
        """Promote one VID to ``IS_BEST_IND = 'Y'`` through ``PromotionRepo``."""
        self._require_owned_lineage(user_id, strategy_id)
        if self._promotion is None:
            raise RuntimeError("PromotionRepo not configured")
        self._promotion.flip_best(
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            user_id=user_id,
        )

    def set_logical_delete(
        self,
        user_id: str,
        strategy_id: UUID,
        logical_delete_ind: str,
        strategy_vid: int | None = None,
    ) -> None:
        """Set ``LOGICAL_DELETE_IND`` on a lineage, or on one VID."""
        self._require_owned_lineage(user_id, strategy_id)
        self._repo.sp_upd_strategy_logical_delete(
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            logical_delete_ind=logical_delete_ind,
            user_id=user_id,
        )
