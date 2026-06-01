"""Promotion DB access — strategy lookup, result comparison, IS_BEST_IND flip.

All bt.* reads are delegated to the injected BtQueueRepo — no duplicate
SP wrappers. Only promotion-specific writes (flip_best, ins_promotion)
live here.
"""

from __future__ import annotations

import json
import logging
import uuid

from quant.promotion.evaluate import DEMOTED, PROMOTED, PromotionDecision, evaluate_promotion
from quant.queue.repo import BtQueueRepo
from quant.refdata.reader import RedisRefData
from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class PromotionRepo(DbGateway):
    """Promotion-specific writes + orchestration; reads delegated to BtQueueRepo."""

    def __init__(self, conninfo: str, bt: BtQueueRepo) -> None:
        super().__init__(conninfo)
        self._bt = bt

    # ── writes (promotion-specific SPs) ───────────────────────────────

    def flip_best(
        self, *, strategy_id, strategy_vid: int | None, user_id: str
    ) -> None:
        vid_param = int(strategy_vid) if strategy_vid is not None else None
        self._call_write(
            "CALL bt.sp_upd_promote_strategy("
            "%s::uuid, %s::integer, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (str(strategy_id), vid_param, user_id),
        )

    def ins_promotion(
        self,
        *,
        queue_id: uuid.UUID | str,
        strategy_id,
        strategy_vid: int,
        outcome: str,
        user_id: str,
        compared_vid: int | None = None,
        gate_results: list[dict] | None = None,
    ) -> None:
        self._call_write(
            "CALL bt.sp_ins_promotion("
            "%s::uuid, %s::uuid, %s::uuid, %s::integer, %s::text,"
            " %s::integer, %s::jsonb, %s::text,"
            " NULL::text, NULL::text, NULL::text)",
            (
                str(uuid.uuid4()),
                str(queue_id),
                str(strategy_id),
                int(strategy_vid),
                outcome,
                compared_vid,
                json.dumps(gate_results) if gate_results else None,
                user_id,
            ),
        )

    # ── orchestration ────────────────────────────────────────────────

    def _fetch_best_payload(self, strategy_id, best_strat: dict) -> dict | None:
        rows = self._bt.sp_get_queue(strategy_id=strategy_id, limit=1)
        best_q = next(
            (r for r in rows if r["strategy_vid"] == best_strat["strategy_vid"]),
            None,
        )
        if best_q is None:
            return None
        result = self._bt.sp_get_result(best_q["queue_id"])
        return result["payload_json"] if result else None

    def _apply(
        self, decision: PromotionDecision, *, strategy_id, strategy_vid: int,
        user_id: str, queue_id: uuid.UUID,
    ) -> None:
        if decision.outcome in (DEMOTED, PROMOTED):
            vid = strategy_vid if decision.outcome == PROMOTED else None
            self.flip_best(
                strategy_id=strategy_id, strategy_vid=vid, user_id=user_id,
            )

        self.ins_promotion(
            queue_id=queue_id,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            outcome=decision.outcome,
            user_id=user_id,
            compared_vid=decision.compared_vid,
            gate_results=[
                {"name": g.name, "passed": g.passed,
                 "value": g.value, "threshold": g.threshold}
                for g in decision.gate_results
            ] if decision.gate_results else None,
        )

    def run(
        self,
        refdata: RedisRefData,
        job: dict,
        payload: dict,
        queue_id: uuid.UUID,
    ) -> PromotionDecision:
        """Full promotion flow: evaluate against current best + persist."""
        promotion_metrics = refdata.get_promotion_metrics()
        best_rows = self._bt.sp_get_strategy(job["strategy_id"], is_best_ind="Y")
        best_strat = best_rows[0] if best_rows else None

        is_current_best = (
            best_strat is not None
            and best_strat["strategy_vid"] == job["strategy_vid"]
        )
        best_vid = best_strat["strategy_vid"] if best_strat else None

        best_payload = None
        if not is_current_best and best_strat:
            best_payload = self._fetch_best_payload(job["strategy_id"], best_strat)

        decision = evaluate_promotion(
            payload, best_payload, promotion_metrics,
            is_current_best=is_current_best, best_vid=best_vid,
        )
        refdata.validate_promotion_state(decision.outcome)

        self._apply(
            decision,
            strategy_id=job["strategy_id"],
            strategy_vid=job["strategy_vid"],
            user_id=job["user_id"],
            queue_id=queue_id,
        )
        logger.info(
            "Promotion decision for strategy_id=%s vid=%s: %s",
            job["strategy_id"], job["strategy_vid"], decision.outcome,
        )
        return decision
