CREATE OR REPLACE PROCEDURE BT.SP_GET_QUEUED_COUNT(
    IN  IN_USER_ID           TEXT,
    IN  IN_QUEUE_STATUS_ID   INTEGER,
    OUT OUT_COUNT            INTEGER,
    OUT OUT_SQLSTATE         TEXT,
    OUT OUT_SQLMSG           TEXT,
    OUT OUT_SQLERRMC         TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
/*
 * Count active rows in BT.QUEUE owned by IN_USER_ID with the given status
 * (typically QUEUED). Used by the coordinator to enforce the per-user
 * queued-job rate limit (see docs/design/backtest-queue.md §8.2).
 *
 * Uses IX_QUEUE_USER_CURRENT — index-only-ish scan over current rows
 * (TRANSACT_TO_TS = '9999-12-31') filtered by USER_ID + QUEUE_STATUS_ID.
 */
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';
    OUT_COUNT    := 0;

    V_OTHER_TEXT := 'IN_USER_ID=' || COALESCE(IN_USER_ID, '')
                 || ', IN_QUEUE_STATUS_ID=' || COALESCE(IN_QUEUE_STATUS_ID::TEXT, '');

    OUT_SQLMSG := '10';
    SELECT COUNT(*)::INTEGER
      INTO OUT_COUNT
      FROM BT.QUEUE
     WHERE TRANSACT_TO_TS  = TIMESTAMPTZ '9999-12-31'
       AND QUEUE_STATUS_ID = IN_QUEUE_STATUS_ID
       AND USER_ID         = IN_USER_ID;

    OUT_SQLMSG := '50';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_QUEUED_COUNT', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_QUEUED_COUNT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
