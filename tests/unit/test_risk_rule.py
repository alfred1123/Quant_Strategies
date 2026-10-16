"""A run records the risk rule it read, and stores nothing when the rule is missing."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from quant.schemas.backtest import (
    FactorConfig,
    OptimizeRequest,
    PerformanceResponse,
    RangeParam,
    RiskRuleRecord,
)
from quant.strategy.backtest_service import run_optimize
from quant.strategy.risk_rule import RiskRuleMissing, read_risk_rule, record_for_run


def _request() -> OptimizeRequest:
    return OptimizeRequest(
        symbol="btcusdt.crypto",
        start="2024-01-01",
        end="2024-12-31",
        data_source="bybit",
        tm_interval_id=1,
        trading_period=365,
        factors=[
            FactorConfig(
                indicator="get_sma",
                strategy="momentum",
                window_range=RangeParam(min=10, max=10, step=10),
                signal_range=RangeParam(min=0.0, max=0.0, step=1.0),
            )
        ],
    )


def _search():
    result = MagicMock()
    result.n_valid = 1
    result.best = {"sharpe": 1.2}
    result.grid_df = [0]
    result.top10 = []
    result.grid = []
    result.extract_plots.return_value = None
    return result


class TestRunRecordsTheRule:
    def test_the_result_is_the_rule_the_run_read(self):
        sharpe = 1.24
        perf = PerformanceResponse(
            strategy_metrics={"Sharpe Ratio": sharpe},
            buy_hold_metrics={"Sharpe Ratio": 0.4},
            equity_curve=[],
            perf_csv="",
        )
        with (
            patch("quant.strategy.backtest_service._build_data_dict", return_value={}),
            patch("quant.strategy.backtest_service.require_scoreable_sample"),
            patch("quant.strategy.backtest_service.build_config"),
            patch("quant.strategy.backtest_service._build_param_ranges", return_value=([], [])),
            patch("quant.strategy.backtest_service.ParametersOptimization") as opt_cls,
            patch("quant.strategy.backtest_service._build_perf_response", return_value=perf),
        ):
            opt_cls.return_value.run.return_value = _search()
            response = run_optimize(_request(), cache=None)

        rule = read_risk_rule()
        stored = response.model_dump()["risk_rule"]
        assert stored["rule_id"] == rule.rule_id
        assert stored["blend_name"] == rule.blend_name
        assert stored["applied"] is False
        assert stored["engine_can_apply"] is False
        assert stored["metrics_are"] == "unit_position"
        assert stored["limits"] is None
        assert {row["key"]: row["weight"] for row in stored["sleeves"]} == {
            sleeve.key: sleeve.weight for sleeve in rule.sleeves
        }
        assert {sleeve.key: sleeve.weight for sleeve in rule.sleeves} == {
            "ETH": 0.37,
            "BNB": 0.25,
            "BTC": 0.38,
        }
        assert {sleeve.key: sleeve.definition for sleeve in rule.sleeves} == {
            "ETH": "BTC Bollinger 65/2.25 filtering ETH Bollinger 100/-1.0",
            "BNB": "BNB held when BTC Bollinger z(100) > 0.5",
            "BTC": "BTC held when BTC Bollinger z(60) > 2.25",
        }
        assert response.performance.strategy_metrics["Sharpe Ratio"] == sharpe
        assert response.performance.buy_hold_metrics["Sharpe Ratio"] == 0.4

    def test_the_record_cannot_claim_the_rule_was_applied(self):
        dumped = record_for_run(read_risk_rule()).model_dump()
        dumped["applied"] = True
        with pytest.raises(ValidationError):
            RiskRuleRecord.model_validate(dumped)

        dumped["applied"] = False
        dumped["metrics_are"] = "sized_blend"
        with pytest.raises(ValidationError):
            RiskRuleRecord.model_validate(dumped)


class TestMissingRuleFailsClosed:
    def test_the_run_raises_and_returns_no_result(self, monkeypatch):
        monkeypatch.setattr("quant.strategy.risk_rule._RULE", None)
        with pytest.raises(RiskRuleMissing, match="risk rule is missing"):
            run_optimize(_request(), cache=None)

    def test_the_worker_stores_no_result(self, monkeypatch):
        from quant.queue.worker import BacktestWorker

        caches = MagicMock()
        caches.refdata.resolve_queue_status_id.side_effect = lambda name: {
            "COMPLETED": 1,
            "FAILED": 4,
        }[name]
        repo = MagicMock()
        repo.fetch_job.return_value = {
            "config_json": _request().model_dump(),
            "strategy_id": str(uuid4()),
            "strategy_vid": 1,
            "priority": 1,
            "user_id": str(uuid4()),
        }
        monkeypatch.setattr("quant.queue.worker.DataCaches", lambda *a, **k: caches)
        monkeypatch.setattr("quant.queue.worker.get_redis_url", lambda: "redis://localhost")
        monkeypatch.setattr("quant.queue.worker.WorkerRepo", lambda url: repo)
        monkeypatch.setattr("quant.queue.worker.PriceBarServiceFactory", lambda *a, **k: MagicMock())

        def _missing(*_a, **_k):
            raise RiskRuleMissing("risk rule is missing")

        monkeypatch.setattr("quant.queue.worker.run_optimize", _missing)

        code = BacktestWorker("postgresql://stub").run(uuid4())

        assert code == 0
        repo.ins_result.assert_not_called()
        assert repo.sp_ins_queue.call_args.kwargs["status_id"] == 4
        assert "risk rule is missing" in repo.sp_ins_queue.call_args.kwargs["error_text"]
