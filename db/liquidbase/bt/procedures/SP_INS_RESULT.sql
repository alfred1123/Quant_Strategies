CREATE OR REPLACE PROCEDURE BT.SP_INS_RESULT(
    IN  IN_QUEUE_ID          UUID,
    IN  IN_PAYLOAD_JSON      JSONB,
    IN  IN_USER_ID           TEXT,
    OUT OUT_RESULT_ID        INTEGER,
    OUT OUT_SQLSTATE         TEXT,
    OUT OUT_SQLMSG           TEXT,
    OUT OUT_SQLERRMC         TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '');

    -- Step 10: Insert result row; capture generated RESULT_ID
    OUT_SQLMSG := '10';
    INSERT INTO BT.RESULT (
        QUEUE_ID,
        PAYLOAD_JSON,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_QUEUE_ID,
        IN_PAYLOAD_JSON,
        IN_USER_ID,
        NOW() AT TIME ZONE 'UTC'
    )
    RETURNING RESULT_ID INTO OUT_RESULT_ID;

    -- Step 20: Audit log
    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_RESULT', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_RESULT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
