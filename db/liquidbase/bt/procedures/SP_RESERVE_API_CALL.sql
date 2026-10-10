-- Add one to CONFIG.API_LIMIT.CALL_COUNT for this app.
-- An elapsed window starts again at 1. There is no per-call row.

CREATE OR REPLACE PROCEDURE BT.SP_RESERVE_API_CALL(
    IN  IN_APP_ID      INTEGER,
    OUT OUT_SQLSTATE   TEXT,
    OUT OUT_SQLMSG     TEXT,
    OUT OUT_SQLERRMC   TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_custom_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '');

    OUT_SQLMSG := '10';
    UPDATE CONFIG.API_LIMIT
       SET CALL_COUNT = CASE
               WHEN WINDOW_FROM_TS + (TIME_WINDOW_SEC * INTERVAL '1 second') > V_START_TS
               THEN COALESCE(CALL_COUNT, 0) + 1
               ELSE 1
           END,
           WINDOW_FROM_TS = CASE
               WHEN WINDOW_FROM_TS + (TIME_WINDOW_SEC * INTERVAL '1 second') > V_START_TS
               THEN WINDOW_FROM_TS
               ELSE V_START_TS
           END,
           UPDATED_AT = V_START_TS
     WHERE APP_ID = IN_APP_ID
       AND TIME_WINDOW_SEC IS NOT NULL;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'BT', 'SP_RESERVE_API_CALL', V_LOG_START, NULL,
        V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG
    );

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

            RAISE WARNING '[SP_RESERVE_API_CALL] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
