"""Unit tests for JobsService.enqueue strategy identity."""

import uuid
from unittest.mock import MagicMock

import pytest

from quant.api.schemas.jobs import EnqueueRequest
from quant.api.services.jobs import JobsService


@pytest.fixture
def svc() -> JobsService:
    repo = MagicMock()
    repo.sp_get_queued_count.return_value = 0
    repo.queued_position.return_value = 1
    refdata = MagicMock()
    refdata.resolve_queue_status_id.return_value = 10
    redis_client = MagicMock()
    return JobsService(repo=repo, refdata=refdata, redis_client=redis_client)


def test_enqueue_resolves_strategy_from_name(svc: JobsService) -> None:
    sid = uuid.uuid4()
    svc._repo.sp_ins_strategy.return_value = (sid, 2)

    req = EnqueueRequest(
        strategy_nm="btcusdt.crypto ← btcusdt.crypto/get_bollinger_band/momentum_band_signal on c",
        config_json={"symbol": "btcusdt.crypto", "factors": []},
    )
    resp = svc.enqueue("user-uuid", req)

    svc._repo.sp_ins_strategy.assert_called_once_with(
        strategy_nm=req.strategy_nm,
        config_json=req.config_json,
        user_id="user-uuid",
    )
    svc._repo.sp_ins_queue.assert_called_once()
    queue_kwargs = svc._repo.sp_ins_queue.call_args.kwargs
    assert queue_kwargs["strategy_id"] == sid
    assert queue_kwargs["strategy_vid"] == 2
    assert resp.queue_pos == 1
