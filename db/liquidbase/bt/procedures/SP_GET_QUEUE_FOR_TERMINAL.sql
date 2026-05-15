CREATE OR REPLACE PROCEDURE BT.SP_GET_QUEUE_FOR_TERMINAL(
    IN  IN_USER_ID           TEXT,
    IN  IN_QUEUE_STATUS_ID   INTEGER,
    IN  IN_LIMIT             INTEGER,
    OUT OUT_RESULT           REFCURSOR,
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
    V_LIMIT      INTEGER;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_USER_ID='          || COALESCE(IN_USER_ID, '')
                 || ', IN_QUEUE_STATUS_ID=' || COALESCE(IN_QUEUE_STATUS_ID::TEXT, '');

    V_LIMIT := COALESCE(IN_LIMIT, 50);

    -- Step 10: Active queue rows joined to current strategy version for terminal display.
    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_queue_for_terminal_cursor';

    IF IN_USER_ID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT q.QUEUE_ID,
                   q.STRATEGY_ID,
                   q.STRATEGY_VID,
                   s.STRATEGY_NM,
                   s.IS_CURRENT_IND AS STRAT_CURRENT_IND,
                   q.TRANSACT_FROM_TS,
                   (SELECT NAME FROM REFDATA.QUEUE_STATUS WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,
                   q.PRIORITY,
                   q.USER_ID,
                   s.CONFIG_JSON,
                   q.ERROR_TEXT
              FROM BT.QUEUE q
              JOIN BT.STRATEGY s ON s.STRATEGY_ID  = q.STRATEGY_ID
                                AND s.STRATEGY_VID = q.STRATEGY_VID
             WHERE q.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
               AND q.QUEUE_STATUS_ID IN (1,2,3)
               AND q.USER_ID = IN_USER_ID
             ORDER BY q.PRIORITY ASC, q.TRANSACT_FROM_TS ASC
             LIMIT V_LIMIT;
    ELSE
        OPEN OUT_RESULT FOR
            SELECT q.QUEUE_ID,
                   q.STRATEGY_ID,
                   q.STRATEGY_VID,
                   s.STRATEGY_NM,
                   s.IS_CURRENT_IND AS STRAT_CURRENT_IND,
                   q.TRANSACT_FROM_TS,
                   (SELECT NAME FROM REFDATA.QUEUE_STATUS WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,
                   q.PRIORITY,
                   q.USER_ID,
                   s.CONFIG_JSON,
                   q.ERROR_TEXT
              FROM BT.QUEUE q
              JOIN BT.STRATEGY s ON s.STRATEGY_ID  = q.STRATEGY_ID
                                AND s.STRATEGY_VID = q.STRATEGY_VID
             WHERE q.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
               AND q.QUEUE_STATUS_ID IN (1,2,3)
             ORDER BY q.PRIORITY ASC, q.TRANSACT_FROM_TS ASC
             LIMIT V_LIMIT;
    END IF;

    -- Step 20: Audit log
    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_QUEUE_FOR_TERMINAL', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_QUEUE_FOR_TERMINAL] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
