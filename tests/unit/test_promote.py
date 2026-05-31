"""Tests for quant.queue.promote — REFDATA-driven auto-promote logic."""

import pytest

from quant.queue.promote import passes_hard_gates, should_promote


def _payload(sharpe: float = 1.0, calmar: float = 0.5, max_dd: float = -0.1, total_ret: float = 0.2):
    return {
        "performance": {
            "strategy_metrics": {
                "Sharpe Ratio": sharpe,
                "Calmar Ratio": calmar,
                "Max Drawdown": max_dd,
                "Total Return": total_ret,
                "Annualized Return": 0.15,
            }
        }
    }


def _metrics():
    """Minimal REFDATA.PROMOTION_METRIC rows: two hard gates + three soft."""
    return [
        {"metric_key": "Sharpe Ratio", "direction": "higher_is_better", "requirement_type": "HARD", "priority": 0,  "threshold": 0},
        {"metric_key": "Max Drawdown", "direction": "lower_is_better",  "requirement_type": "HARD", "priority": 10, "threshold": 0.40},
        {"metric_key": "Sharpe Ratio", "direction": "higher_is_better", "requirement_type": "SOFT", "priority": 0,  "threshold": None},
        {"metric_key": "Calmar Ratio", "direction": "higher_is_better", "requirement_type": "SOFT", "priority": 20, "threshold": None},
        {"metric_key": "Max Drawdown", "direction": "lower_is_better",  "requirement_type": "SOFT", "priority": 80, "threshold": None},
    ]


class TestHardGates:
    def test_fails_when_sharpe_below_zero(self):
        assert should_promote(_payload(sharpe=-0.5), None, _metrics()) is False

    def test_passes_when_sharpe_at_zero(self):
        assert should_promote(_payload(sharpe=0.0), None, _metrics()) is True

    def test_passes_when_sharpe_positive(self):
        assert should_promote(_payload(sharpe=1.5), None, _metrics()) is True


class TestNoBaseline:
    def test_promote_when_no_best(self):
        assert should_promote(_payload(), None, _metrics()) is True


class TestSoftComparison:
    def test_higher_sharpe_wins(self):
        assert should_promote(_payload(sharpe=2.0), _payload(sharpe=1.0), _metrics()) is True

    def test_lower_sharpe_loses(self):
        assert should_promote(_payload(sharpe=0.5), _payload(sharpe=1.0), _metrics()) is False

    def test_tied_sharpe_falls_to_calmar(self):
        assert should_promote(
            _payload(sharpe=1.0, calmar=2.0),
            _payload(sharpe=1.0, calmar=1.0),
            _metrics(),
        ) is True

    def test_tied_sharpe_and_calmar_falls_to_max_dd(self):
        assert should_promote(
            _payload(sharpe=1.0, calmar=0.5, max_dd=0.05),
            _payload(sharpe=1.0, calmar=0.5, max_dd=0.10),
            _metrics(),
        ) is True

    def test_all_tied_no_promote(self):
        p = _payload()
        assert should_promote(p, p, _metrics()) is False


class TestPassesHardGates:
    def test_passes_all(self):
        assert passes_hard_gates(_payload(sharpe=1.0, max_dd=0.10), _metrics()) is True

    def test_fails_sharpe_gate(self):
        assert passes_hard_gates(_payload(sharpe=-0.5), _metrics()) is False

    def test_fails_max_dd_gate(self):
        assert passes_hard_gates(_payload(sharpe=1.0, max_dd=0.50), _metrics()) is False

    def test_max_dd_at_boundary(self):
        assert passes_hard_gates(_payload(sharpe=1.0, max_dd=0.40), _metrics()) is True

    def test_empty_metrics_passes(self):
        assert passes_hard_gates(_payload(), []) is True

    def test_vid1_demotion_scenario(self):
        """VID 1 starts as best but result fails hard gates → should demote."""
        bad_result = _payload(sharpe=-1.0, max_dd=0.60)
        assert passes_hard_gates(bad_result, _metrics()) is False


class TestEdgeCases:
    def test_empty_metrics_no_promote(self):
        assert should_promote(_payload(), None, []) is False

    def test_missing_performance_key(self):
        assert should_promote({}, None, _metrics()) is False

    def test_nan_metric_fails_hard_gate(self):
        assert should_promote(_payload(sharpe=float("nan")), None, _metrics()) is False
