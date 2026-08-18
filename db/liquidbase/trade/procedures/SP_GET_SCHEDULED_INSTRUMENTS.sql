-- Instruments that scheduled deployments will need bars for, all intervals.
--
-- Feeds the price-bar warmer (POST /api/v1/market-data/price-bars/sync), which
-- fetches one bar set per (INTERNAL_CUSIP, APP_ID) instead of letting every
-- deployment sharing an instrument fetch and race on the same insert.
--
-- Deliberately does NOT join DEPLOYMENT_SCHEDULE_STATUS. Warming happens before
-- a deployment comes due, so filtering on the cursor would warm only what is
-- already late — the opposite of the point. SP_GET_MISSED_DUE_DEPLOYMENTS is the
-- due-ness query; this one answers "what will be traded on this interval at all".
--
-- DISTINCT because the warmer wants instruments, not deployments: a dozen
-- deployments on one symbol collapse to a single row and a single fetch.
CREATE OR REPLACE PROCEDURE TRADE.SP_GET_SCHEDULED_INSTRUMENTS(
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
    OUT_RESULT := 'sp_get_scheduled_instruments_cursor';

    OPEN OUT_RESULT FOR
        SELECT DISTINCT
               d.SCHEDULE_TM_INTERVAL_ID AS TM_INTERVAL_ID,
               d.INTERNAL_CUSIP,
               d.APP_ID
          FROM TRADE.DEPLOYMENT d
          -- Inner join: an interval the app cannot resolve to a PERIOD_LENGTH is
          -- one it cannot compute a bar boundary for, so it is not warmable.
          JOIN REFDATA.TM_INTERVAL ti
            ON ti.TM_INTERVAL_ID = d.SCHEDULE_TM_INTERVAL_ID
         WHERE d.SCHEDULE_TM_INTERVAL_ID IS NOT NULL
           AND d.IS_ENABLED_IND = 'Y'
           AND d.DEPLOYMENT_STATUS NOT IN ('PAUSED', 'STOPPED')
           AND d.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
         ORDER BY TM_INTERVAL_ID, d.INTERNAL_CUSIP, d.APP_ID;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_SCHEDULED_INSTRUMENTS', V_LOG_START, NULL, NULL,
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

            RAISE WARNING '[SP_GET_SCHEDULED_INSTRUMENTS] % (SQLSTATE: %). Detail: %. Context: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_GET_SCHEDULED_INSTRUMENTS(
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
