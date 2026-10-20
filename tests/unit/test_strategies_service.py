"""Unit tests for StrategiesService."""

import uuid
from unittest.mock import MagicMock

import pytest

from quant.api.services.strategies import StrategiesService, StrategyNotFound


def test_list_strategies_best_versions_default():
    repo = MagicMock()
    repo.sp_get_strategy_list.return_value = [{"strategy_id": uuid.uuid4()}]
    svc = StrategiesService(repo)

    rows = svc.list_strategies(user_id="user-1", limit=100)

    assert len(rows) == 1
    repo.sp_get_strategy_list.assert_called_once_with(
        user_id="user-1", limit=100, is_best_ind="Y",
    )


def test_get_result_reads_strategy_then_payload():
    repo = MagicMock()
    sid = uuid.uuid4()
    repo.sp_get_strategy.return_value = [{
        "strategy_id": sid,
        "strategy_vid": 3,
        "strategy_nm": "btc daily",
        "config_json": {"symbol": "btcusdt.crypto"},
    }]
    repo.fetch_result_payload.return_value = {"best": {"sharpe": 1.2}}
    svc = StrategiesService(repo)

    row = svc.get_result(sid, 3)

    assert row["strategy_nm"] == "btc daily"
    assert row["result"]["best"]["sharpe"] == 1.2
    repo.sp_get_strategy.assert_called_once_with(sid, strategy_vid=3)
    repo.fetch_result_payload.assert_called_once_with(sid, 3)


def test_get_result_missing_strategy():
    repo = MagicMock()
    repo.sp_get_strategy.return_value = []
    svc = StrategiesService(repo)

    with pytest.raises(StrategyNotFound):
        svc.get_result(uuid.uuid4(), 1)


def test_list_strategies_all_versions():
    repo = MagicMock()
    repo.sp_get_strategy_list.return_value = []
    svc = StrategiesService(repo)

    svc.list_strategies(user_id="user-1", limit=50, versions="all")

    repo.sp_get_strategy_list.assert_called_once_with(
        user_id="user-1", limit=50, is_best_ind=None,
    )


# ── lifecycle writes ───────────────────────────────────────────────────


def test_set_logical_delete_requires_a_queue_row():
    repo = MagicMock()
    repo.sp_get_queue.return_value = []
    svc = StrategiesService(repo)
    sid = uuid.uuid4()

    with pytest.raises(StrategyNotFound):
        svc.set_logical_delete("user-uuid", sid, "Y")

    repo.sp_upd_strategy_logical_delete.assert_not_called()


def test_set_logical_delete_flips_the_lineage():
    repo = MagicMock()
    repo.sp_get_queue.return_value = [{"queue_id": uuid.uuid4()}]
    svc = StrategiesService(repo)
    sid = uuid.uuid4()

    svc.set_logical_delete("user-uuid", sid, "Y")

    repo.sp_upd_strategy_logical_delete.assert_called_once_with(
        strategy_id=sid,
        strategy_vid=None,
        logical_delete_ind="Y",
        user_id="user-uuid",
    )


def test_promote_requires_a_queue_row():
    repo = MagicMock()
    repo.sp_get_queue.return_value = []
    promotion = MagicMock()
    svc = StrategiesService(repo, promotion=promotion)

    with pytest.raises(StrategyNotFound):
        svc.promote("user-uuid", uuid.uuid4(), 2)

    promotion.flip_best.assert_not_called()


def test_promote_flips_best_through_promotion_repo():
    repo = MagicMock()
    repo.sp_get_queue.return_value = [{"queue_id": uuid.uuid4()}]
    promotion = MagicMock()
    svc = StrategiesService(repo, promotion=promotion)
    sid = uuid.uuid4()

    svc.promote("user-uuid", sid, 2)

    promotion.flip_best.assert_called_once_with(
        strategy_id=sid, strategy_vid=2, user_id="user-uuid",
    )
