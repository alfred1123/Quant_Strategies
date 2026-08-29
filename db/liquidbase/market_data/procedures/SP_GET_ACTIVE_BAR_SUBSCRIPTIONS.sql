-- Series that have been subscribed to, for the warmer.
--
-- The counterpart to TRADE.SP_GET_SCHEDULED_INSTRUMENTS, and it emits the same
-- three columns under the same names (SOURCE_APP_ID aliased to APP_ID) so the
-- warmer can concatenate the two reads instead of translating between them.
--
-- No DISTINCT, unlike the deployment-side read: a deployment is per user and a
-- dozen can name one instrument, whereas UQ_BAR_SUBSCRIPTION_OPEN already
-- allows only one open row per series. Duplicates across the two sources are
-- still possible and are folded downstream by PriceBarService.sync.
CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_GET_ACTIVE_BAR_SUBSCRIPTIONS(
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
    OUT_RESULT := 'sp_get_active_bar_subscriptions_cursor';

    OPEN OUT_RESULT FOR
        SELECT s.TM_INTERVAL_ID,
               s.INTERNAL_CUSIP,
               s.SOURCE_APP_ID AS APP_ID
          FROM MARKET_DATA.BAR_SUBSCRIPTION s
          -- Inner join, matching the deployment-side read: an interval with no
          -- PERIOD_LENGTH has no computable bar boundary, so it is not warmable.
          JOIN REFDATA.TM_INTERVAL ti
            ON ti.TM_INTERVAL_ID = s.TM_INTERVAL_ID
         WHERE s.IS_ENABLED_IND = 'Y'
           AND s.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
         ORDER BY s.TM_INTERVAL_ID, s.INTERNAL_CUSIP, APP_ID;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_GET_ACTIVE_BAR_SUBSCRIPTIONS', V_LOG_START, NULL, NULL,
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

            RAISE WARNING '[SP_GET_ACTIVE_BAR_SUBSCRIPTIONS] % (SQLSTATE: %). Detail: %. Context: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_GET_ACTIVE_BAR_SUBSCRIPTIONS(
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
