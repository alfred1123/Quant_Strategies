CREATE OR REPLACE PROCEDURE BT.SP_INS_RESULT(
    IN  IN_RESULT_ID       UUID,
    IN  IN_QUEUE_ID        UUID,
    IN  IN_PAYLOAD_JSON    JSONB,
    OUT OUT_SQLSTATE       TEXT,
    OUT OUT_SQLMSG         TEXT,
    OUT OUT_SQLERRMC       TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START    TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT   TEXT;
    V_LOG_STATE    TEXT;
    V_LOG_MSG      TEXT;
    V_USER_ID      TEXT;
    V_STRATEGY_ID  UUID;
    V_STRATEGY_VID INTEGER;
    V_RESULT_VID   INTEGER;
    V_METRICS      JSONB;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_RESULT_ID=' || COALESCE(IN_RESULT_ID::TEXT, '')
                 || ', IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '');

    -- Derive audit + strategy keys from the queue submission (latest VID row).
    OUT_SQLMSG := '05';
    SELECT USER_ID, STRATEGY_ID, STRATEGY_VID
      INTO V_USER_ID, V_STRATEGY_ID, V_STRATEGY_VID
      FROM BT.QUEUE
     WHERE QUEUE_ID = IN_QUEUE_ID
     ORDER BY QUEUE_VID DESC
     LIMIT 1;

    IF V_STRATEGY_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'QUEUE_ID not found or missing STRATEGY_ID';
        RETURN;
    END IF;

    OUT_SQLMSG := '08';
    SELECT COALESCE(MAX(RESULT_VID), 0) + 1
      INTO V_RESULT_VID
      FROM BT.RESULT
     WHERE STRATEGY_ID  = V_STRATEGY_ID
       AND STRATEGY_VID = V_STRATEGY_VID;

    OUT_SQLMSG := '09';
    UPDATE BT.RESULT
       SET IS_CURRENT_IND = 'N'
     WHERE STRATEGY_ID  = V_STRATEGY_ID
       AND STRATEGY_VID = V_STRATEGY_VID
       AND IS_CURRENT_IND = 'Y';

    V_METRICS := IN_PAYLOAD_JSON -> 'performance' -> 'strategy_metrics';

    OUT_SQLMSG := '10';
    INSERT INTO BT.RESULT (
        RESULT_ID,
        QUEUE_ID,
        STRATEGY_ID,
        STRATEGY_VID,
        RESULT_VID,
        IS_CURRENT_IND,
        PAYLOAD_JSON,
        TOTAL_RETURN,
        ANNUALIZED_RETURN,
        SHARPE_RATIO,
        MAX_DRAWDOWN,
        CALMAR_RATIO,
        CREATED_AT
    ) VALUES (
        IN_RESULT_ID,
        IN_QUEUE_ID,
        V_STRATEGY_ID,
        V_STRATEGY_VID,
        V_RESULT_VID,
        'Y',
        IN_PAYLOAD_JSON,
        (V_METRICS ->> 'Total Return')::NUMERIC,
        (V_METRICS ->> 'Annualized Return')::NUMERIC,
        (V_METRICS ->> 'Sharpe Ratio')::NUMERIC,
        (V_METRICS ->> 'Max Drawdown')::NUMERIC,
        (V_METRICS ->> 'Calmar Ratio')::NUMERIC,
        NOW() AT TIME ZONE 'UTC'
    );

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'BT', 'SP_INS_RESULT', V_LOG_START, NULL, V_OTHER_TEXT,
        COALESCE(V_USER_ID, 'system'), V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_INS_RESULT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
