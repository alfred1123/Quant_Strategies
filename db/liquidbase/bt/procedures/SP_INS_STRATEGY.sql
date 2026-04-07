CREATE OR REPLACE PROCEDURE BT.SP_INS_STRATEGY(
    IN  IN_STRATEGY_ID    UUID,
    IN  IN_STRATEGY_NM    TEXT,
    IN  IN_TICKER         TEXT,
    IN  IN_CONJUNCTION    TEXT,
    IN  IN_TRADING_PERIOD INTEGER,
    IN  IN_CONFIG_JSON    JSONB,
    IN  IN_USER_ID        TEXT,
    OUT OUT_SQLSTATE      TEXT,
    OUT OUT_SQLMSG        TEXT,
    OUT OUT_SQLERRMC      TEXT
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

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_NM=' || COALESCE(IN_STRATEGY_NM, '');

    -- Step 10: Resolve VID — get current max, or start at 1
    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(STRATEGY_VID), 0) + 1
      INTO V_VID
      FROM BT.STRATEGY
     WHERE STRATEGY_ID = IN_STRATEGY_ID;

    -- Step 20: Flip old current row(s) to 'N'
    OUT_SQLMSG := '20';
    UPDATE BT.STRATEGY
       SET IS_CURRENT_IND = 'N'
     WHERE STRATEGY_ID    = IN_STRATEGY_ID
       AND IS_CURRENT_IND = 'Y';

    -- Step 30: Insert new version as current
    OUT_SQLMSG := '30';
    INSERT INTO BT.STRATEGY (
        STRATEGY_ID,
        STRATEGY_VID,
        STRATEGY_NM,
        TICKER,
        CONJUNCTION,
        TRADING_PERIOD,
        CONFIG_JSON,
        USER_ID,
        CREATED_AT,
        IS_CURRENT_IND
    ) VALUES (
        IN_STRATEGY_ID,
        V_VID,
        IN_STRATEGY_NM,
        IN_TICKER,
        IN_CONJUNCTION,
        IN_TRADING_PERIOD,
        IN_CONFIG_JSON,
        IN_USER_ID,
        NOW(),
        'Y'
    );

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_STRATEGY', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_STRATEGY] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
