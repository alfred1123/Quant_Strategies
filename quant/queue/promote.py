"""Auto-promote logic — compare new backtest result against current best VID.

Called by the worker after writing BT.RESULT and before marking COMPLETED.

Metric configuration (direction, thresholds, priority) comes from
REFDATA.PROMOTION_METRIC via RedisRefData — nothing is hardcoded here.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

Outcome = Literal["PROMOTED", "KEPT", "DEMOTED", "REJECTED"]


@dataclass
class GateResult:
    name: str
    metric_key: str
    passed: bool
    value: float | None
    threshold: float | None


@dataclass
class PromotionDecision:
    outcome: Outcome
    gate_results: list[GateResult] = field(default_factory=list)
    compared_vid: int | None = None


def _extract_metric(payload: dict, metric_key: str) -> float | None:
    """Pull a metric value from an OptimizeResponse PAYLOAD_JSON."""
    perf = payload.get("performance")
    if not perf:
        return None
    sm = perf.get("strategy_metrics")
    if not sm:
        return None
    val = sm.get(metric_key)
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return None
    return float(val)


def _check_one_gate(
    payload: dict, metric_key: str, direction: str, threshold: float
) -> bool:
    val = _extract_metric(payload, metric_key)
    if val is None:
        return False
    if direction == "lower_is_better":
        return val <= threshold
    return val >= threshold


def passes_hard_gates(payload: dict, promotion_metrics: list[dict]) -> bool:
    """Return True if payload passes every HARD-type gate in promotion_metrics."""
    for m in promotion_metrics:
        if m.get("requirement_type") != "HARD":
            continue
        threshold = m.get("threshold")
        if threshold is None:
            continue
        metric_key = m["metric_key"]
        direction = m["direction"]
        if not _check_one_gate(payload, metric_key, direction, float(threshold)):
            logger.info(
                "Hard gate FAILED: %s %s %.4f (threshold=%.4f)",
                metric_key, direction,
                _extract_metric(payload, metric_key) or float("nan"),
                float(threshold),
            )
            return False
        logger.debug("Hard gate passed: %s", metric_key)
    return True


def _wins_soft(
    new_val: float, best_val: float, direction: str
) -> bool:
    if direction == "lower_is_better":
        return new_val < best_val
    return new_val > best_val


def should_promote(
    new_payload: dict,
    best_payload: dict | None,
    promotion_metrics: list[dict],
) -> bool:
    """Return True if new_payload passes all hard gates and beats the best on soft metrics.

    ``promotion_metrics`` is a list of REFDATA.PROMOTION_METRIC rows
    sorted by priority, each with keys: metric_key, direction,
    requirement_type ('HARD'/'SOFT'), priority, threshold.

    - No baseline (``best_payload is None``) → promote if hard gates pass.
    - Hard gates are evaluated first; any failure rejects the candidate.
    - Soft metrics are compared in priority order; first decisive win/loss decides.
    - If all soft metrics tie → no promote (conservative).
    """
    if not promotion_metrics:
        logger.warning("No REFDATA.PROMOTION_METRIC rows — skip promote")
        return False

    if not passes_hard_gates(new_payload, promotion_metrics):
        return False

    # No baseline → promote (hard gates already passed).
    if best_payload is None:
        logger.info("No existing best result — promoting (hard gates passed)")
        return True

    # Phase 2: soft comparison in priority order.
    for m in promotion_metrics:
        if m.get("requirement_type") != "SOFT":
            continue
        metric_key = m["metric_key"]
        direction = m["direction"]

        new_val = _extract_metric(new_payload, metric_key)
        best_val = _extract_metric(best_payload, metric_key)

        if new_val is None:
            logger.debug("New has no %s — skip this metric", metric_key)
            continue
        if best_val is None:
            logger.info("Best has no %s — new wins on %s (%.4f)", metric_key, metric_key, new_val)
            return True

        if _wins_soft(new_val, best_val, direction):
            logger.info(
                "PROMOTE on %s: new=%.4f > best=%.4f (%s)",
                metric_key, new_val, best_val, direction,
            )
            return True
        if _wins_soft(best_val, new_val, direction):
            logger.info(
                "KEEP on %s: best=%.4f > new=%.4f (%s)",
                metric_key, best_val, new_val, direction,
            )
            return False
        logger.debug("Tie on %s (%.4f) — check next", metric_key, new_val)

    logger.info("All soft metrics tied — no promote (conservative)")
    return False


def _collect_gate_results(
    payload: dict, promotion_metrics: list[dict]
) -> list[GateResult]:
    results: list[GateResult] = []
    for m in promotion_metrics:
        if m.get("requirement_type") != "HARD":
            continue
        threshold = m.get("threshold")
        if threshold is None:
            continue
        metric_key = m["metric_key"]
        direction = m["direction"]
        val = _extract_metric(payload, metric_key)
        passed = _check_one_gate(payload, metric_key, direction, float(threshold))
        results.append(GateResult(
            name=m.get("name", metric_key),
            metric_key=metric_key,
            passed=passed,
            value=val,
            threshold=float(threshold),
        ))
    return results


def evaluate_promotion(
    new_payload: dict,
    best_payload: dict | None,
    promotion_metrics: list[dict],
    *,
    is_current_best: bool = False,
    best_vid: int | None = None,
) -> PromotionDecision:
    """Full promotion evaluation returning a structured decision.

    Wraps ``passes_hard_gates`` / ``should_promote`` and collects
    gate results + the decisive soft metric for persistence.
    """
    gates = _collect_gate_results(new_payload, promotion_metrics)
    hard_pass = all(g.passed for g in gates)

    if is_current_best:
        if hard_pass:
            return PromotionDecision(outcome="KEPT", gate_results=gates)
        return PromotionDecision(outcome="DEMOTED", gate_results=gates)

    if not hard_pass:
        return PromotionDecision(
            outcome="REJECTED", gate_results=gates, compared_vid=best_vid,
        )

    if best_payload is None:
        return PromotionDecision(
            outcome="PROMOTED", gate_results=gates, compared_vid=best_vid,
        )

    for m in promotion_metrics:
        if m.get("requirement_type") != "SOFT":
            continue
        metric_key = m["metric_key"]
        direction = m["direction"]
        new_val = _extract_metric(new_payload, metric_key)
        best_val = _extract_metric(best_payload, metric_key)

        if new_val is None:
            continue
        if best_val is None:
            return PromotionDecision(
                outcome="PROMOTED", gate_results=gates, compared_vid=best_vid,
            )
        if _wins_soft(new_val, best_val, direction):
            return PromotionDecision(
                outcome="PROMOTED", gate_results=gates, compared_vid=best_vid,
            )
        if _wins_soft(best_val, new_val, direction):
            return PromotionDecision(
                outcome="KEPT", gate_results=gates, compared_vid=best_vid,
            )

    return PromotionDecision(
        outcome="KEPT", gate_results=gates, compared_vid=best_vid,
    )
