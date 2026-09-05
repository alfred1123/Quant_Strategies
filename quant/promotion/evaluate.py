"""Pure promotion evaluation — no DB, no side effects.

Metric configuration (direction, thresholds, priority) comes from
REFDATA.PROMOTION_METRIC via RedisRefData — nothing is hardcoded here.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PROMOTED = "PROMOTED"
KEPT = "KEPT"
DEMOTED = "DEMOTED"
REJECTED = "REJECTED"


@dataclass
class GateResult:
    name: str
    metric_key: str
    passed: bool
    value: float | None
    threshold: float | None


@dataclass
class PromotionDecision:
    outcome: str
    gate_results: list[GateResult] = field(default_factory=list)
    compared_vid: int | None = None


# ── helpers ──────────────────────────────────────────────────────────────

def _extract_metric(payload: dict, metric_key: str) -> float | None:
    val = (payload.get("performance") or {}).get("strategy_metrics", {}).get(metric_key)
    if val is None or (isinstance(val, float) and not math.isfinite(val)):
        return None
    return float(val)


def _compare(a: float, b: float, direction: str) -> int:
    """Lower layer: which of two values wins. 1 if *a*, -1 if *b*, 0 if tied."""
    if direction == "lower_is_better":
        return (b > a) - (b < a)
    return (a > b) - (a < b)


def _meets_threshold(value: float | None, threshold: float, direction: str) -> bool:
    """Lower layer: does a single value satisfy its threshold boundary."""
    return value is not None and _compare(value, threshold, direction) >= 0


# ── metric grouping ──────────────────────────────────────────────────────

def _group_by_type(metrics: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for m in metrics:
        grouped.setdefault(m.get("requirement_type", ""), []).append(m)
    return grouped


# ── HARD / SOFT (higher layer: requirement semantics) ──────────────────────

def _evaluate_hard(payload: dict, hard_metrics: list[dict]) -> list[GateResult]:
    """HARD: every requirement must pass. Builds one gate per metric via the
    threshold check; the caller rejects if any gate fails."""
    gates: list[GateResult] = []
    for m in hard_metrics:
        threshold = m.get("threshold")
        if threshold is None:
            continue
        key = m["metric_key"]
        val = _extract_metric(payload, key)
        gates.append(GateResult(
            name=m.get("name", key), metric_key=key,
            passed=_meets_threshold(val, float(threshold), m["direction"]),
            value=val, threshold=float(threshold),
        ))
    return gates


def _evaluate_soft(
    new_payload: dict, best_payload: dict, soft_metrics: list[dict],
) -> str:
    """SOFT: rank candidate vs best by priority order. First decisive metric
    comparison wins; PROMOTED if candidate ahead, KEPT if behind, KEPT if all tied."""
    for m in soft_metrics:
        new_val = _extract_metric(new_payload, m["metric_key"])
        best_val = _extract_metric(best_payload, m["metric_key"])
        if new_val is None:
            continue
        if best_val is None:
            return PROMOTED
        cmp = _compare(new_val, best_val, m["direction"])
        if cmp != 0:
            return PROMOTED if cmp > 0 else KEPT
    return KEPT


# ── public API ───────────────────────────────────────────────────────────

def passes_hard_gates(payload: dict, promotion_metrics: list[dict]) -> bool:
    """True if all HARD requirements pass. Does not touch SOFT metrics."""
    hard = _group_by_type(promotion_metrics).get("HARD", [])
    return all(g.passed for g in _evaluate_hard(payload, hard))


def evaluate_promotion(
    new_payload: dict,
    best_payload: dict | None,
    promotion_metrics: list[dict],
    *,
    is_current_best: bool = False,
    best_vid: int | None = None,
    strategy_vid: int | None = None,
) -> PromotionDecision:
    """Merge HARD + SOFT into one decision.

    ``compared_vid`` is the opponent VID. It is ``None`` when the candidate
    is already the current best (VID 1 baseline or a re-run of the best),
    or when there is no baseline to rank against.
    """
    if not promotion_metrics:
        logger.warning("No REFDATA.PROMOTION_METRIC rows — rejecting")
        return PromotionDecision(outcome=REJECTED, compared_vid=best_vid)

    by_type = _group_by_type(promotion_metrics)
    gates = _evaluate_hard(new_payload, by_type.get("HARD", []))
    all_passed = all(g.passed for g in gates)

    if is_current_best:
        # Candidate *is* the current best — there is no opponent. VID 1 stays
        # IS_BEST_IND='Y' even when hard gates fail. compared_vid stays None
        # so the UI does not draw a mirror table of this row against itself.
        if strategy_vid == 1:
            return PromotionDecision(outcome=KEPT, gate_results=gates)
        return PromotionDecision(
            outcome=KEPT if all_passed else DEMOTED,
            gate_results=gates,
        )

    if not all_passed:
        return PromotionDecision(
            outcome=REJECTED, gate_results=gates, compared_vid=best_vid,
        )

    if best_payload is None:
        outcome = PROMOTED
    else:
        outcome = _evaluate_soft(new_payload, best_payload, by_type.get("SOFT", []))

    return PromotionDecision(
        outcome=outcome, gate_results=gates, compared_vid=best_vid,
    )
