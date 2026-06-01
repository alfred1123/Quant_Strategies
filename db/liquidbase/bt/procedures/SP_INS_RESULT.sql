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
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_USER_ID    TEXT;
    V_METRICS    JSONB;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_RESULT_ID=' || COALESCE(IN_RESULT_ID::TEXT, '')
                 || ', IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '');

    -- Derive USER_ID from the queue row for audit logging
    OUT_SQLMSG := '05';
    SELECT USER_ID INTO V_USER_ID
      FROM BT.QUEUE
     WHERE QUEUE_ID = IN_QUEUE_ID
       AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
     LIMIT 1;

    -- Extract strategy_metrics from payload for fast querying
    V_METRICS := IN_PAYLOAD_JSON -> 'performance' -> 'strategy_metrics';

    -- Step 10: Insert result row with shredded metrics
    OUT_SQLMSG := '10';
    INSERT INTO BT.RESULT (
        RESULT_ID,
        QUEUE_ID,
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
        IN_PAYLOAD_JSON,
        (V_METRICS ->> 'Total Return')::NUMERIC,
        (V_METRICS ->> 'Annualized Return')::NUMERIC,
        (V_METRICS ->> 'Sharpe Ratio')::NUMERIC,
        (V_METRICS ->> 'Max Drawdown')::NUMERIC,
        (V_METRICS ->> 'Calmar Ratio')::NUMERIC,
        NOW() AT TIME ZONE 'UTC'
    );

    -- Step 20: Audit log
    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_RESULT', V_START_TS, NULL, V_OTHER_TEXT, COALESCE(V_USER_ID, 'system'), V_LOG_STATE, V_LOG_MSG);

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
