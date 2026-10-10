-- Read current TRADE.DEPLOYMENT_PERFORMANCE rows for one user.
--
-- IN_APP_USER_ID    required — scope via the current deployment owner.
-- IN_DEPLOYMENT_ID  optional — one logical deployment.
-- IN_FROM_TS        optional — BAR_TIMESTAMP >= this instant.
-- IN_TO_TS          optional — BAR_TIMESTAMP <= this instant.
-- IN_LIMIT          optional — row cap (default 50); Python clamps the max.
--
-- Current rows only. CREATED_AT is exposed as RECONCILED_AT: the chart's
-- last-reconcile stamp is the newest of these. USER_ID stays off the cursor.
-- Newest bar first.
CREATE OR REPLACE PROCEDURE TRADE.SP_GET_DEPLOYMENT_PERFORMANCE(
    IN  IN_APP_USER_ID      UUID,
    IN  IN_DEPLOYMENT_ID    UUID,
    IN  IN_FROM_TS          TIMESTAMPTZ,
    IN  IN_TO_TS            TIMESTAMPTZ,
    IN  IN_LIMIT            INTEGER,
    OUT OUT_RESULT          REFCURSOR,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_custom_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_SQL        TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_LIMIT      INTEGER := COALESCE(NULLIF(IN_LIMIT, 0), 50);
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    IF IN_APP_USER_ID IS NULL THEN
        RAISE EXCEPTION 'SP_GET_DEPLOYMENT_PERFORMANCE needs IN_APP_USER_ID';
    END IF;

    V_OTHER_TEXT := 'IN_APP_USER_ID=' || IN_APP_USER_ID::TEXT
                 || ', IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_FROM_TS=' || COALESCE(IN_FROM_TS::TEXT, '')
                 || ', IN_TO_TS=' || COALESCE(IN_TO_TS::TEXT, '')
                 || ', IN_LIMIT=' || COALESCE(IN_LIMIT::TEXT, '');

    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_deployment_performance_cursor';

    V_SQL := 'SELECT p.DEPLOYMENT_PERFORMANCE_ID,'
          || '       p.DEPLOYMENT_PERFORMANCE_VID,'
          || '       p.DEPLOYMENT_ID,'
          || '       p.DEPLOYMENT_VID,'
          || '       p.INTENT_ID,'
          || '       p.TM_INTERVAL_ID,'
          || '       p.BAR_TIMESTAMP,'
          || '       p.IS_MANAGED_IND,'
          || '       p.TARGET_POSITION,'
          || '       p.BACKTEST_POSITION,'
          || '       p.UNIT_NOTIONAL_AMT,'
          || '       p.LIVE_RETURN,'
          || '       p.LIVE_FILL_GAP_RETURN,'
          || '       p.LIVE_FEE_RETURN,'
          || '       p.BACKTEST_RETURN,'
          || '       p.CREATED_AT AS RECONCILED_AT'
          || '  FROM TRADE.DEPLOYMENT_PERFORMANCE p'
          || '  JOIN TRADE.DEPLOYMENT d'
          || '    ON d.DEPLOYMENT_ID = p.DEPLOYMENT_ID'
          || '   AND d.TRANSACT_TO_TS = TIMESTAMPTZ ''9999-12-31 00:00:00+00'''
          || format(' WHERE d.APP_USER_ID = %L::uuid', IN_APP_USER_ID)
          || '   AND p.IS_CURRENT_IND = ''Y''';

    IF IN_DEPLOYMENT_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND p.DEPLOYMENT_ID = %L::uuid', IN_DEPLOYMENT_ID);
    END IF;

    IF IN_FROM_TS IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND p.BAR_TIMESTAMP >= %L::timestamptz', IN_FROM_TS);
    END IF;

    IF IN_TO_TS IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND p.BAR_TIMESTAMP <= %L::timestamptz', IN_TO_TS);
    END IF;

    V_SQL := V_SQL || ' ORDER BY p.BAR_TIMESTAMP DESC'
                  || format(' LIMIT %s', V_LIMIT);

    OPEN OUT_RESULT FOR EXECUTE V_SQL;

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_DEPLOYMENT_PERFORMANCE', V_LOG_START, NULL, V_OTHER_TEXT,
        IN_APP_USER_ID::TEXT, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_DEPLOYMENT_PERFORMANCE] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_GET_DEPLOYMENT_PERFORMANCE(
        UUID, UUID, TIMESTAMPTZ, TIMESTAMPTZ, INTEGER,
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
