CREATE OR REPLACE PROCEDURE BT.SP_INS_PROMOTION(
    IN  IN_PROMOTION_ID    UUID,
    IN  IN_QUEUE_ID        UUID,
    IN  IN_STRATEGY_ID     UUID,
    IN  IN_STRATEGY_VID    INTEGER,
    IN  IN_OUTCOME         TEXT,
    IN  IN_COMPARED_VID    INTEGER,
    IN  IN_GATE_RESULTS    JSONB,
    IN  IN_USER_ID         TEXT,
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

    V_OTHER_TEXT := 'IN_PROMOTION_ID=' || COALESCE(IN_PROMOTION_ID::TEXT, '')
                 || ', IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '')
                 || ', IN_OUTCOME=' || COALESCE(IN_OUTCOME, '');

    -- Step 10: Insert promotion decision row
    OUT_SQLMSG := '10';
    INSERT INTO BT.PROMOTION (
        PROMOTION_ID,
        QUEUE_ID,
        STRATEGY_ID,
        STRATEGY_VID,
        OUTCOME,
        COMPARED_VID,
        GATE_RESULTS,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_PROMOTION_ID,
        IN_QUEUE_ID,
        IN_STRATEGY_ID,
        IN_STRATEGY_VID,
        IN_OUTCOME,
        IN_COMPARED_VID,
        IN_GATE_RESULTS,
        IN_USER_ID,
        NOW() AT TIME ZONE 'UTC'
    );

    -- Step 20: Audit log
    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_PROMOTION', V_LOG_START, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_PROMOTION] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
