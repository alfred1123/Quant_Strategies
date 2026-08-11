CREATE OR REPLACE PROCEDURE BT.SP_GET_RESULT(
    IN  IN_QUEUE_ID        UUID,
    OUT OUT_RESULT          REFCURSOR,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_result_cursor';

    OPEN OUT_RESULT FOR
        SELECT RESULT_ID,
               QUEUE_ID,
               STRATEGY_ID,
               STRATEGY_VID,
               RESULT_VID,
               IS_CURRENT_IND,
               PAYLOAD_JSON,
               TOTAL_RETURN,
               ANNUALIZED_RETURN,
               SHARPE_RATIO,
               MAX_DRAWDOWN,
               CALMAR_RATIO,
               CREATED_AT
          FROM BT.RESULT
         WHERE QUEUE_ID = IN_QUEUE_ID
         ORDER BY CREATED_AT DESC
         LIMIT 1;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_RESULT', V_LOG_START, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

EXCEPTION
    WHEN OTHERS THEN
        DECLARE
            V_DETAIL  TEXT;
            V_CONTEXT TEXT;
        BEGIN
            GET STACKED DIAGNOSTICS
                OUT_SQLSTATE = RETURNED_SQLSTATE,
                OUT_SQLERRMC = MESSAGE_TEXT,
                V_DETAIL     = PG_EXCEPTION_DETAIL,
                V_CONTEXT    = PG_EXCEPTION_CONTEXT;

            RAISE WARNING '[SP_GET_RESULT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
