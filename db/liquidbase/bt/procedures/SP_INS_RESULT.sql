CREATE OR REPLACE PROCEDURE BT.SP_INS_RESULT(
    IN  IN_STRATEGY_ID       UUID,
    IN  IN_STRATEGY_VID      INTEGER,
    IN  IN_RUN_AT            TIMESTAMPTZ,
    IN  IN_DATA_START        DATE,
    IN  IN_DATA_END          DATE,
    IN  IN_TICKER            TEXT,
    IN  IN_FEE_BPS           NUMERIC,
    IN  IN_METRICS_JSON      JSONB,
    IN  IN_WALK_FORWARD_JSON JSONB,
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
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '')
                 || ', IN_TICKER=' || COALESCE(IN_TICKER, '');

    OUT_SQLMSG := '10';
    INSERT INTO BT.RESULT (
        STRATEGY_ID,
        STRATEGY_VID,
        RUN_AT,
        DATA_START,
        DATA_END,
        TICKER,
        FEE_BPS,
        METRICS_JSON,
        WALK_FORWARD_JSON,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_STRATEGY_ID,
        IN_STRATEGY_VID,
        IN_RUN_AT,
        IN_DATA_START,
        IN_DATA_END,
        IN_TICKER,
        IN_FEE_BPS,
        IN_METRICS_JSON,
        IN_WALK_FORWARD_JSON,
        IN_USER_ID,
        NOW()
    );

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_RESULT', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, NULL, NULL);

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
