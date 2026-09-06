"""BtQueueRepo.sp_upd_strategy_logical_delete CALL matches the procedure DDL."""

from unittest.mock import patch
from uuid import uuid4

from quant.queue.repo import BtQueueRepo
from tests.unit.liquibase_sources import call_arg_count, procedure_param_count


@patch.object(BtQueueRepo, "_call_write", return_value=())
def test_logical_delete_call_matches_ddl(mock_write):
    repo = BtQueueRepo("postgresql://test")
    repo.sp_upd_strategy_logical_delete(
        strategy_id=uuid4(),
        logical_delete_ind="Y",
        user_id="u1",
    )
    sql = mock_write.call_args.args[0]
    assert call_arg_count(sql) == procedure_param_count(
        "bt", "SP_UPD_STRATEGY_LOGICAL_DELETE.sql"
    )
