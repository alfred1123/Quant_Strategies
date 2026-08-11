-- Active BT.QUEUE row for one QUEUE_ID, joined to the frozen BT.STRATEGY
-- snapshot (QUEUE.STRATEGY_VID = STRATEGY.STRATEGY_VID). One round-trip for
-- the Python worker — replaces SP_GET_QUEUE + SP_GET_STRATEGY pair.
--
-- Cursor columns: STRATEGY_ID, STRATEGY_VID, PRIORITY, USER_ID, CONFIG_JSON.
CREATE OR REPLACE PROCEDURE BT.SP_GET_QUEUE_LATEST(
    IN  IN_QUEUE_ID   UUID,
    OUT OUT_RESULT     REFCURSOR,
    OUT OUT_SQLSTATE   TEXT,
    OUT OUT_SQLMSG     TEXT,
    OUT OUT_SQLERRMC   TEXT
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

    V_OTHER_TEXT := 'IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '');

    OUT_SQLMSG := '10';
    IF IN_QUEUE_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_QUEUE_ID is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_queue_latest_cursor';
    OPEN OUT_RESULT FOR
        SELECT q.STRATEGY_ID,
               q.STRATEGY_VID,
               q.PRIORITY,
               q.USER_ID,
               s.CONFIG_JSON
          FROM BT.QUEUE q
          JOIN BT.STRATEGY s
            ON s.STRATEGY_ID  = q.STRATEGY_ID
           AND s.STRATEGY_VID = q.STRATEGY_VID
         WHERE q.QUEUE_ID       = IN_QUEUE_ID
           AND q.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_QUEUE_LATEST', V_LOG_START, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_QUEUE_LATEST] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
