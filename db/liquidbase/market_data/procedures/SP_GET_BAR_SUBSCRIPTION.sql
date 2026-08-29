-- Current bar subscriptions, for the Market data page.
--
-- IN_BAR_SUBSCRIPTION_ID  optional — when set, filter to one subscription.
--
-- Unscoped by user, because a subscription is not owned by one: bars are shared
-- facts and one row per series serves everybody. Everyone sees the same list,
-- which is the point — you cannot reason about whether to disable a capture if
-- you cannot see that it exists.
--
-- Open rows only. Disabled rows are returned: the page shows them as paused so
-- they can be re-enabled, and their absence would read as "deleted" instead.
-- Coverage (first bar, last bar, gaps) is deliberately not joined here — it is
-- a MARKET_DATA.PRICE_BAR question answered per row by SP_GET_PRICE_BAR_COVERAGE,
-- and folding an aggregate over the bar table into this read would turn a cheap
-- list into a scan.
CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_GET_BAR_SUBSCRIPTION(
    IN  IN_BAR_SUBSCRIPTION_ID  UUID,
    OUT OUT_RESULT              REFCURSOR,
    OUT OUT_SQLSTATE            TEXT,
    OUT OUT_SQLMSG              TEXT,
    OUT OUT_SQLERRMC            TEXT
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

    V_OTHER_TEXT := 'IN_BAR_SUBSCRIPTION_ID=' || COALESCE(IN_BAR_SUBSCRIPTION_ID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_bar_subscription_cursor';

    OPEN OUT_RESULT FOR
        SELECT s.BAR_SUBSCRIPTION_ID,
               s.BAR_SUBSCRIPTION_VID,
               s.INTERNAL_CUSIP,
               s.TM_INTERVAL_ID,
               s.SOURCE_APP_ID,
               s.IS_ENABLED_IND,
               s.BACKFILL_FROM_TS,
               s.TRANSACT_FROM_TS
          FROM MARKET_DATA.BAR_SUBSCRIPTION s
         WHERE s.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
           AND (IN_BAR_SUBSCRIPTION_ID IS NULL
                OR s.BAR_SUBSCRIPTION_ID = IN_BAR_SUBSCRIPTION_ID)
         ORDER BY s.INTERNAL_CUSIP, s.TM_INTERVAL_ID, s.SOURCE_APP_ID;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_GET_BAR_SUBSCRIPTION', V_LOG_START, NULL, V_OTHER_TEXT,
        NULL, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_BAR_SUBSCRIPTION] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_GET_BAR_SUBSCRIPTION(
        UUID,
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
