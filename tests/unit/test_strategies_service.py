"""Unit tests for StrategiesService."""

import uuid
from unittest.mock import MagicMock

from quant.api.services.strategies import StrategiesService


def test_list_strategies_best_versions_default():
    repo = MagicMock()
    repo.sp_get_strategy_list.return_value = [{"strategy_id": uuid.uuid4()}]
    svc = StrategiesService(repo)

    rows = svc.list_strategies(user_id="user-1", limit=100)

    assert len(rows) == 1
    repo.sp_get_strategy_list.assert_called_once_with(
        user_id="user-1", limit=100, is_best_ind="Y",
    )


def test_list_strategies_all_versions():
    repo = MagicMock()
    repo.sp_get_strategy_list.return_value = []
    svc = StrategiesService(repo)

    svc.list_strategies(user_id="user-1", limit=50, versions="all")

    repo.sp_get_strategy_list.assert_called_once_with(
        user_id="user-1", limit=50, is_best_ind=None,
    )
