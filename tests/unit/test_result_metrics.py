"""Tests for shredded BT.RESULT metric extraction."""

import math

from quant.queue.result_metrics import ShreddedResultMetrics, extract_shredded_metrics


def _payload(
    *,
    strat: dict | None = None,
    bh: dict | None = None,
) -> dict:
    perf: dict = {}
    if strat is not None:
        perf["strategy_metrics"] = strat
    if bh is not None:
        perf["buy_hold_metrics"] = bh
    return {"performance": perf} if perf else {}


class TestExtractShreddedMetrics:
    def test_reads_strategy_and_buy_hold(self):
        m = extract_shredded_metrics(_payload(
            strat={
                "Total Return": 0.99,
                "Annualized Return": 0.15,
                "Sharpe Ratio": 1.23,
                "Max Drawdown": 0.09,
                "Calmar Ratio": 1.66,
            },
            bh={
                "Total Return": 0.5,
                "Annualized Return": 0.12,
                "Sharpe Ratio": 0.8,
                "Max Drawdown": 0.15,
                "Calmar Ratio": 1.2,
            },
        ))
        assert m == ShreddedResultMetrics(
            total_return=0.99,
            annualized_return=0.15,
            sharpe_ratio=1.23,
            max_drawdown=0.09,
            calmar_ratio=1.66,
            buy_hold_total_return=0.5,
            buy_hold_annualized_return=0.12,
            buy_hold_sharpe_ratio=0.8,
            buy_hold_max_drawdown=0.15,
            buy_hold_calmar_ratio=1.2,
        )

    def test_missing_performance_returns_all_none(self):
        m = extract_shredded_metrics({})
        assert m.total_return is None
        assert m.buy_hold_sharpe_ratio is None

    def test_nan_becomes_none(self):
        m = extract_shredded_metrics(_payload(
            strat={"Sharpe Ratio": math.nan},
        ))
        assert m.sharpe_ratio is None
