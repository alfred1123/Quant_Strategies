CREATE OR REPLACE PROCEDURE BT.SP_INS_QUEUE(
    IN  IN_QUEUE_ID          UUID,
    IN  IN_QUEUE_VID         INTEGER,
    IN  IN_STRATEGY_ID       UUID,
    IN  IN_STRATEGY_VID      INTEGER,
    IN  IN_QUEUE_STATUS_ID   INTEGER,
    IN  IN_PRIORITY          INTEGER,
    IN  IN_ERROR_TEXT        TEXT,
    IN  IN_USER_ID           TEXT,
    OUT OUT_SQLSTATE         TEXT,
    OUT OUT_SQLMSG           TEXT,
    OUT OUT_SQLERRMC         TEXT
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

    V_OTHER_TEXT := 'IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '')
                 || ', IN_PRODUCT_GRP_ID=' || COALESCE(IN_PRODUCT_GRP_ID::TEXT, '');

    -- Step 10: Resolve VID — get current max, or start at 1
    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(QUEUE_VID), 0) + 1
      INTO V_VID
      FROM BT.QUEUE
     WHERE QUEUE_ID = IN_QUEUE_ID;

    -- Step 20: Close old current row — set TRANSACT_TO_TS to now
    OUT_SQLMSG := '20';
    UPDATE BT.QUEUE
       SET IS_CURRENT_IND = 'N'
     WHERE QUEUE_ID     = IN_QUEUE_ID
       AND IS_CURRENT_IND = 'Y';

    -- Step 30: Insert new QUEUE version (TRANSACT_TO_TS = 9999-12-31)
    OUT_SQLMSG := '30';
    INSERT INTO BT.QUEUE (
        QUEUE_ID,
        QUEUE_VID,
        STRATEGY_ID,
        STRATEGY_VID,
        QUEUE_STATUS_ID,
        PRIORITY,
        ERROR_TEXT,
        IS_CURRENT_IND,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_QUEUE_ID,
        V_VID,
        IN_STRATEGY_ID,
        IN_STRATEGY_VID,
        IN_QUEUE_STATUS_ID,
        IN_PRIORITY,
        IN_ERROR_TEXT,
        'Y',
        IN_USER_ID,
        NOW() AT TIME ZONE 'UTC'
    );

    OUT_SQLMSG := '50';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_QUEUE', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_QUEUE] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
