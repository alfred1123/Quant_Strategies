"""Tests for quant.api.services.promotion.PromotionService."""

import uuid
from unittest.mock import MagicMock

from quant.api.services.promotion import PromotionService


def test_list_promotions_delegates_to_repo():
    repo = MagicMock()
    repo.sp_get_promotion.return_value = [{"outcome": "PROMOTED"}]
    svc = PromotionService(repo=repo)

    rows = svc.list_promotions()

    assert rows == [{"outcome": "PROMOTED"}]
    repo.sp_get_promotion.assert_called_once_with(None, limit=200)


def test_list_promotions_passes_strategy_and_limit():
    repo = MagicMock()
    repo.sp_get_promotion.return_value = []
    svc = PromotionService(repo=repo)
    sid = uuid.uuid4()

    svc.list_promotions(sid, limit=10)

    repo.sp_get_promotion.assert_called_once_with(sid, limit=10)
