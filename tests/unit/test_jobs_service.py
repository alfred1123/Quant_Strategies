"""Unit tests for JobsService.enqueue strategy identity."""

import uuid
from unittest.mock import MagicMock

import pytest

from quant.api.schemas.jobs import EnqueueRequest
from quant.api.services.jobs import JobsService, StrategyNameMismatch, StrategyNotFound


@pytest.fixture
def svc() -> JobsService:
    repo = MagicMock()
    repo.sp_get_queued_count.return_value = 0
    repo.queued_position.return_value = 1
    refdata = MagicMock()
    refdata.resolve_queue_status_id.return_value = 10
    refdata.interval_name.return_value = "DAILY"
    redis_client = MagicMock()
    return JobsService(repo=repo, refdata=refdata, redis_client=redis_client)


def test_enqueue_resolves_strategy_from_name(svc: JobsService) -> None:
    sid = uuid.uuid4()
    svc._repo.sp_ins_strategy.return_value = (sid, 2)

    req = EnqueueRequest(
        strategy_nm=(
            "btcusdt.crypto@bybit:DAILY ← "
            "btcusdt.crypto/get_bollinger_band/momentum_band_signal on c"
        ),
        config_json={"symbol": "btcusdt.crypto", "factors": [], "tm_interval_id": 1},
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


def test_enqueue_refuses_a_name_that_omits_its_cadence(svc: JobsService) -> None:
    """The real incident: a cached bundle forked a lineage after the rename.

    `btcusdt.crypto@bybit ← …` was enqueued once 1.19.0 had already renamed
    every stored row to carry `:DAILY`, so it created a second STRATEGY_ID
    for a strategy that already had one. Repair is blocked by the
    (USER_ID, STRATEGY_NM, STRATEGY_VID) unique constraint, so the write is
    refused instead.
    """
    req = EnqueueRequest(
        strategy_nm="btcusdt.crypto@bybit ← btcusdt.crypto/get_bollinger_band/momentum on c",
        config_json={"symbol": "btcusdt.crypto", "factors": [], "tm_interval_id": 1},
    )

    with pytest.raises(StrategyNameMismatch, match="DAILY"):
        svc.enqueue("user-uuid", req)

    svc._repo.sp_ins_strategy.assert_not_called()


def test_enqueue_refuses_a_name_naming_the_wrong_cadence(svc: JobsService) -> None:
    """An hourly config under a daily name is the identity collapse #58 fixed."""
    svc._refdata.interval_name.return_value = "1H"
    req = EnqueueRequest(
        strategy_nm="btcusdt.crypto@bybit:DAILY ← btcusdt.crypto/get_bollinger_band/momentum on c",
        config_json={"symbol": "btcusdt.crypto", "factors": [], "tm_interval_id": 2},
    )

    with pytest.raises(StrategyNameMismatch, match="1H"):
        svc.enqueue("user-uuid", req)

    svc._repo.sp_ins_strategy.assert_not_called()


def test_enqueue_refuses_a_config_with_no_cadence(svc: JobsService) -> None:
    """Required since #57 — a run with no interval selects no input series."""
    req = EnqueueRequest(
        strategy_nm="btcusdt.crypto@bybit:DAILY ← btcusdt.crypto/get_bollinger_band/momentum on c",
        config_json={"symbol": "btcusdt.crypto", "factors": []},
    )

    with pytest.raises(StrategyNameMismatch, match="tm_interval_id"):
        svc.enqueue("user-uuid", req)

    svc._repo.sp_ins_strategy.assert_not_called()


def test_set_logical_delete_requires_a_queue_row(svc: JobsService) -> None:
    sid = uuid.uuid4()
    svc._repo.sp_get_queue.return_value = []

    with pytest.raises(StrategyNotFound):
        svc.set_logical_delete("user-uuid", sid, "Y")

    svc._repo.sp_upd_strategy_logical_delete.assert_not_called()


def test_set_logical_delete_flips_the_lineage(svc: JobsService) -> None:
    sid = uuid.uuid4()
    svc._repo.sp_get_queue.return_value = [{"queue_id": uuid.uuid4()}]

    svc.set_logical_delete("user-uuid", sid, "Y")

    svc._repo.sp_upd_strategy_logical_delete.assert_called_once_with(
        strategy_id=sid,
        strategy_vid=None,
        logical_delete_ind="Y",
        user_id="user-uuid",
    )
