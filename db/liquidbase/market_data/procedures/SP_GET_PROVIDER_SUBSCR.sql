-- Current provider subscriptions, with the stored window beside each one.
--
-- The join is PROVIDER_SUBSCR_ID. A subscription with no fetch yet still
-- comes back, and the range columns are null. A header whose payload is
-- gone comes back with HAS_PAYLOAD_IND = N. There is no user filter.

CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_GET_PROVIDER_SUBSCR(
    OUT OUT_RESULT    REFCURSOR,
    OUT OUT_SQLSTATE  TEXT,
    OUT OUT_SQLMSG    TEXT,
    OUT OUT_SQLERRMC  TEXT
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
    OUT_RESULT := 'sp_get_provider_subscr_cursor';
    OPEN OUT_RESULT FOR
        SELECT s.PROVIDER_SUBSCR_ID,
               s.APP_ID,
               s.APP_METRIC_ID,
               s.TM_INTERVAL_ID,
               s.INTERNAL_CUSIP,
               s.IS_ENABLED_IND,
               s.BACKFILL_FROM_TS,
               r.RANGE_START_TS,
               r.RANGE_END_TS,
               CASE
                   WHEN r.API_REQ_ID IS NULL THEN NULL
                   WHEN lp.API_REQ_ID IS NULL THEN 'N'
                   ELSE 'Y'
               END AS HAS_PAYLOAD_IND
          FROM MARKET_DATA.PROVIDER_SUBSCR s
          LEFT JOIN MARKET_DATA.API_REQUEST r
            ON r.PROVIDER_SUBSCR_ID = s.PROVIDER_SUBSCR_ID
           AND r.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
          LEFT JOIN MARKET_DATA.API_REQUEST_PAYLOAD lp
            ON lp.API_REQ_ID = r.API_REQ_ID
           AND lp.API_REQ_VID = r.API_REQ_VID
         WHERE s.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
         ORDER BY s.INTERNAL_CUSIP, s.APP_ID, s.APP_METRIC_ID;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_GET_PROVIDER_SUBSCR', V_LOG_START, NULL,
        NULL, NULL, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_PROVIDER_SUBSCR] % (SQLSTATE: %). Detail: %. Context: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT;
        END;
END;
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
        GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_GET_PROVIDER_SUBSCR(
            OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
        ) TO quant_app;
    END IF;
END $$;
