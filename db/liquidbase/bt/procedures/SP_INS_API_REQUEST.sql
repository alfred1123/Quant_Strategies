CREATE OR REPLACE PROCEDURE BT.SP_INS_API_REQUEST(
    IN  IN_API_REQ_ID       UUID,
    IN  IN_APP_ID           INTEGER,
    IN  IN_APP_METRIC_ID    INTEGER,
    IN  IN_TM_INTERVAL_ID   INTEGER,
    IN  IN_SYMBOL           TEXT,
    IN  IN_FULL_RANGE_START TIMESTAMPTZ,
    IN  IN_FULL_RANGE_END   TIMESTAMPTZ,
    IN  IN_USER_ID          TEXT,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_API_REQ_ID=' || COALESCE(IN_API_REQ_ID::TEXT, '')
                 || ', IN_SYMBOL=' || COALESCE(IN_SYMBOL, '');

    -- Step 10: Resolve VID — get current max, or start at 1
    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(API_REQ_VID), 0) + 1
      INTO V_VID
      FROM BT.API_REQUEST
     WHERE API_REQ_ID = IN_API_REQ_ID;

    -- Step 20: Flip old current row(s) to 'N'
    OUT_SQLMSG := '20';
    UPDATE BT.API_REQUEST
       SET IS_CURRENT_IND = 'N'
     WHERE API_REQ_ID     = IN_API_REQ_ID
       AND IS_CURRENT_IND = 'Y';

    -- Step 30: Insert new version as current
    OUT_SQLMSG := '30';
    INSERT INTO BT.API_REQUEST (
        API_REQ_ID,
        API_REQ_VID,
        APP_ID,
        APP_METRIC_ID,
        TM_INTERVAL_ID,
        SYMBOL,
        FULL_RANGE_START,
        FULL_RANGE_END,
        IS_CURRENT_IND,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_API_REQ_ID,
        V_VID,
        IN_APP_ID,
        IN_APP_METRIC_ID,
        IN_TM_INTERVAL_ID,
        IN_SYMBOL,
        IN_FULL_RANGE_START,
        IN_FULL_RANGE_END,
        'Y',
        IN_USER_ID,
        NOW()
    );

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_API_REQUEST', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_API_REQUEST] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
