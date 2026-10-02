"""The risk rule a backtest run reads and records.

This module is the only copy. A research page may describe what a run
does with it. The page is not a second list of limits for a person to apply.

The engine cannot size or combine sleeves, so ``record_for_run`` stores the
rule with ``applied`` false and leaves the performance block as the
unit-position search. Drawdown tiers and a kill switch are not stored:
they are not signed off, and a number here would read as policy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quant.schemas.backtest import RiskRuleRecord, SleeveWeightRecord

logger = logging.getLogger(__name__)

_WEIGHT_SUM = 1.0


@dataclass(frozen=True)
class Sleeve:
    """One sleeve of the book the rule names. ``definition`` is identity, not a search."""

    key: str
    name: str
    definition: str
    weight: float


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    blend_name: str
    sleeves: tuple[Sleeve, ...]


# Alfred's chosen weighting for the three golden sleeves. The sleeve
# definitions are the books already selected. This module does not retune them.
_RULE: RiskRule | None = RiskRule(
    rule_id="middle",
    blend_name="Middle",
    sleeves=(
        Sleeve(
            "ETH",
            "ETH A2",
            "BTC Bollinger 65/2.25 filtering ETH Bollinger 100/-1.0",
            0.37,
        ),
        Sleeve(
            "BNB",
            "BNB",
            "BNB held when BTC Bollinger z(100) > 0.5",
            0.25,
        ),
        Sleeve(
            "BTC",
            "BTC",
            "BTC held when BTC Bollinger z(60) > 2.25",
            0.38,
        ),
    ),
)


class RiskRuleMissing(Exception):
    """The run cannot read a risk rule, so it must not return a result."""


def read_risk_rule() -> RiskRule:
    """Return the application rule. Raise when it is missing or not a whole book."""
    rule = _RULE
    if rule is None or not rule.sleeves:
        logger.error("risk rule is missing; refusing to return a result")
        raise RiskRuleMissing("risk rule is missing")
    total = sum(sleeve.weight for sleeve in rule.sleeves)
    if abs(total - _WEIGHT_SUM) > 1e-9:
        logger.error("risk rule weights are not a complete book; refusing to return a result")
        raise RiskRuleMissing("risk rule weights are not a complete book")
    return rule


def record_for_run(rule: RiskRule) -> RiskRuleRecord:
    """What the result stores. The engine has not applied the rule."""
    return RiskRuleRecord(
        rule_id=rule.rule_id,
        blend_name=rule.blend_name,
        sleeves=[
            SleeveWeightRecord(
                key=sleeve.key,
                name=sleeve.name,
                definition=sleeve.definition,
                weight=sleeve.weight,
            )
            for sleeve in rule.sleeves
        ],
        applied=False,
        engine_can_apply=False,
        metrics_are="unit_position",
        limits=None,
    )
