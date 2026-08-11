-- Scheduled deployments due for apply now, scoped to one REFDATA.TM_INTERVAL.
--
-- Poller passes IN_TM_INTERVAL_ID (EventBridge / local tick per interval).
-- Returns NEXT_SCHEDULED_TS so the caller can CALL SP_INS_DEPLOYMENT_SCHEDULE_STATUS
-- after apply (no separate advance proc).
DROP PROCEDURE IF EXISTS TRADE.SP_GET_MISSED_DUE_DEPLOYMENTS(
    OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
);

CREATE OR REPLACE PROCEDURE TRADE.SP_GET_MISSED_DUE_DEPLOYMENTS(
    IN  IN_TM_INTERVAL_ID   INTEGER,
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
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_TM_INTERVAL_ID=' || COALESCE(IN_TM_INTERVAL_ID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_missed_due_deployments_cursor';

    OPEN OUT_RESULT FOR
        SELECT d.DEPLOYMENT_ID,
               d.DEPLOYMENT_VID,
               d.APP_USER_ID,
               d.STRATEGY_ID,
               d.STRATEGY_VID,
               d.API_CREDENTIAL_ID,
               d.APP_ID,
               d.INTERNAL_CUSIP,
               d.QTY,
               d.IS_PAPER_IND,
               d.IS_ENABLED_IND,
               d.DEPLOYMENT_STATUS,
               d.SCHEDULE_TM_INTERVAL_ID,
               d.USER_ID,
               ss.SCHEDULED_TS,
               ss.SCHEDULED_TS + ti.PERIOD_LENGTH AS NEXT_SCHEDULED_TS
          FROM TRADE.DEPLOYMENT d
          JOIN REFDATA.TM_INTERVAL ti
            ON ti.TM_INTERVAL_ID = d.SCHEDULE_TM_INTERVAL_ID
          JOIN TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
            ON ss.DEPLOYMENT_ID = d.DEPLOYMENT_ID
           AND ss.IS_CURRENT_IND = 'Y'
         WHERE d.SCHEDULE_TM_INTERVAL_ID = IN_TM_INTERVAL_ID
           AND d.IS_ENABLED_IND = 'Y'
           AND d.DEPLOYMENT_STATUS NOT IN ('PAUSED', 'STOPPED')
           AND d.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
           AND ss.STATUS = 'PENDING'
           AND ss.SCHEDULED_TS <= NOW()
         ORDER BY ss.SCHEDULED_TS ASC;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_MISSED_DUE_DEPLOYMENTS', V_LOG_START, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_GET_MISSED_DUE_DEPLOYMENTS] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_GET_MISSED_DUE_DEPLOYMENTS(
        INTEGER, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
