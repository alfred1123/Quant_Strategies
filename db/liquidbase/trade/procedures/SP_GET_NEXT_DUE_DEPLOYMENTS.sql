-- Enabled scheduled deployments not yet due — UI / ops preview only.
--
-- Latest DEPLOYMENT_SCHEDULE_STATUS must be PENDING with SCHEDULED_TS > NOW().
-- Poller uses SP_GET_MISSED_DUE_DEPLOYMENTS instead. No APP_USER_ID filter.
CREATE OR REPLACE PROCEDURE TRADE.SP_GET_NEXT_DUE_DEPLOYMENTS(
    OUT OUT_RESULT          REFCURSOR,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_next_due_deployments_cursor';

    OPEN OUT_RESULT FOR
        SELECT d.DEPLOYMENT_ID,
               d.DEPLOYMENT_VID,
               d.SCHEDULE_TM_INTERVAL_ID,
               ss.SCHEDULED_TS AS NEXT_DUE_AT
          FROM TRADE.DEPLOYMENT d
          JOIN TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
            ON ss.DEPLOYMENT_ID = d.DEPLOYMENT_ID
           AND ss.IS_CURRENT_IND = 'Y'
         WHERE d.IS_ENABLED_IND = 'Y'
           AND d.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
           AND ss.STATUS = 'PENDING'
           AND ss.SCHEDULED_TS > NOW()
         ORDER BY ss.SCHEDULED_TS ASC;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_NEXT_DUE_DEPLOYMENTS', V_LOG_START, NULL, NULL,
        'system', V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_NEXT_DUE_DEPLOYMENTS] % (SQLSTATE: %). Detail: %. Context: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_GET_NEXT_DUE_DEPLOYMENTS(
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
