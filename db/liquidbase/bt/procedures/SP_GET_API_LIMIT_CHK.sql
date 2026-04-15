CREATE OR REPLACE PROCEDURE BT.SP_GET_API_LIMIT_CHK(
    IN  IN_APP_ID       INTEGER,
    OUT OUT_ALLOWED      CHAR(1),
    OUT OUT_LIMIT_TYPE   TEXT,
    OUT OUT_CURRENT_CNT  INTEGER,
    OUT OUT_MAX_VALUE    INTEGER,
    OUT OUT_SQLSTATE     TEXT,
    OUT OUT_SQLMSG       TEXT,
    OUT OUT_SQLERRMC     TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    V_START_TS      TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT    TEXT;
    V_CNT           INTEGER;
    V_LOG_STATE     TEXT;
    V_LOG_MSG       TEXT;
    R_LIMIT         RECORD;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';
    OUT_ALLOWED  := 'Y';

    V_OTHER_TEXT := 'IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '');

    -- Step 10: Loop over all limit rules for this APP_ID
    OUT_SQLMSG := '10';
    FOR R_LIMIT IN
        SELECT LIMIT_TYPE, MAX_VALUE, TIME_WINDOW_SEC
          FROM REFDATA.API_LIMIT
         WHERE APP_ID = IN_APP_ID
    LOOP
        -- Step 20: Count API_REQUEST rows within the time window
        OUT_SQLMSG := '20';
        SELECT COUNT(*)
          INTO V_CNT
          FROM BT.API_REQUEST
         WHERE APP_ID     = IN_APP_ID
           AND CREATED_AT >= V_START_TS - (R_LIMIT.TIME_WINDOW_SEC * INTERVAL '1 second');

        -- Step 30: If any limit is breached, return the first violation
        IF V_CNT >= R_LIMIT.MAX_VALUE THEN
            OUT_ALLOWED     := 'N';
            OUT_LIMIT_TYPE  := R_LIMIT.LIMIT_TYPE;
            OUT_CURRENT_CNT := V_CNT;
            OUT_MAX_VALUE   := R_LIMIT.MAX_VALUE;

            OUT_SQLMSG := '40';
            CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_API_LIMIT_CHK', V_START_TS, NULL,
                V_OTHER_TEXT || ', BREACH=' || R_LIMIT.LIMIT_TYPE || ', CNT=' || V_CNT::TEXT || '/' || R_LIMIT.MAX_VALUE::TEXT,
                NULL, V_LOG_STATE, V_LOG_MSG);
            RETURN;
        END IF;
    END LOOP;

    -- All limits passed
    OUT_SQLMSG := '50';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_API_LIMIT_CHK', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_API_LIMIT_CHK] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
