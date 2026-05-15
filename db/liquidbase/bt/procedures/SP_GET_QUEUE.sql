CREATE OR REPLACE PROCEDURE BT.SP_GET_QUEUE(
    IN  IN_QUEUE_ID          UUID,
    IN  IN_STRATEGY_ID       UUID,
    IN  IN_QUEUE_STATUS_ID   INTEGER,
    IN  IN_USER_ID           TEXT,
    IN  IN_LIMIT             INTEGER,
    OUT OUT_RESULT           REFCURSOR,
    OUT OUT_SQLSTATE         TEXT,
    OUT OUT_SQLMSG           TEXT,
    OUT OUT_SQLERRMC         TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_custom_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_SQL        TEXT;
    V_LIMIT      INTEGER;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_QUEUE_ID='      || COALESCE(IN_QUEUE_ID::TEXT, '')
                 || ', IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_USER_ID='     || COALESCE(IN_USER_ID, '');

    V_LIMIT := COALESCE(IN_LIMIT, 50);

    -- Step 10: Base SELECT — join status lookup; scope active vs full history
    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_queue_cursor';

    V_SQL := 'SELECT q.QUEUE_ID,'
          || '       q.QUEUE_VID,'
          || '       q.STRATEGY_ID,'
          || '       q.STRATEGY_VID,'
          || '       q.TRANSACT_FROM_TS,'
          || '       q.QUEUE_STATUS_ID,'
          || '       (SELECT NAME FROM REFDATA.QUEUE_STATUS WHERE QUEUE_STATUS_ID = rs.QUEUE_STATUS_ID) AS QUEUE_STATUS,'
          || '       q.PRIORITY,'
          || '       q.ERROR_TEXT,'
          || '       q.USER_ID'
          || '  FROM BT.QUEUE q'
          || '  JOIN REFDATA.QUEUE_STATUS rs ON q.QUEUE_STATUS_ID = rs.QUEUE_STATUS_ID'
          || ' WHERE 1=1';

    -- When QUEUE_ID is supplied return all VIDs (full history for that job).
    -- Otherwise restrict to the active row only.
    IF IN_QUEUE_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND q.QUEUE_ID = %L::uuid', IN_QUEUE_ID);
    ELSE
        V_SQL := V_SQL || ' AND q.TRANSACT_TO_TS = TIMESTAMPTZ ' || quote_literal('9999-12-31 00:00:00+00');
    END IF;

    IF IN_STRATEGY_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND q.STRATEGY_ID = %L::uuid', IN_STRATEGY_ID);
    END IF;

    IF IN_QUEUE_STATUS_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND q.QUEUE_STATUS_ID = %s', IN_QUEUE_STATUS_ID);
    END IF;

    IF IN_USER_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND q.USER_ID = %L', IN_USER_ID);
    END IF;

    V_SQL := V_SQL || ' ORDER BY q.QUEUE_ID, q.QUEUE_VID ASC';
    V_SQL := V_SQL || format(' LIMIT %s', V_LIMIT);

    OPEN OUT_RESULT FOR EXECUTE V_SQL;

    -- Step 20: Audit log
    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_QUEUE', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_QUEUE] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
