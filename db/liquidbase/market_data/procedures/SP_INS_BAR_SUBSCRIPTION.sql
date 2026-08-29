-- Create or version one bar subscription.
--
-- Caller supplies IN_BAR_SUBSCRIPTION_ID (UUID v7). First insert for that id =>
-- BAR_SUBSCRIPTION_VID = 1. Enabling, disabling and retargeting the wanted
-- history all take the same path: close the open row (TRANSACT_TO_TS = now())
-- and insert VID + 1, so the table keeps a record of which series the platform
-- was capturing when.
--
-- Subscriptions are platform-wide, not per user — bars are shared facts, so
-- IN_USER_ID is audit rather than ownership. Any signed-in caller may edit any
-- row. It is NOT stored on the row: it goes to CORE_INS_LOG_PROC below, so
-- CORE_ADMIN.LOG_PROC answers who changed a series and the version window here
-- answers when, without the two keeping separate copies that can disagree.
--
-- Warmability checks (product exists, xref maps it to a vendor symbol for this
-- app, app resolves to a ccxt venue) live in Python — checked on write so three
-- silent per-tick warm failures become one immediate error.
CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_INS_BAR_SUBSCRIPTION(
    IN  IN_BAR_SUBSCRIPTION_ID  UUID,
    IN  IN_INTERNAL_CUSIP       TEXT,
    IN  IN_TM_INTERVAL_ID       INTEGER,
    IN  IN_SOURCE_APP_ID        INTEGER,
    IN  IN_IS_ENABLED_IND       CHAR(1),
    IN  IN_BACKFILL_FROM_TS     TIMESTAMPTZ,
    IN  IN_USER_ID              TEXT,
    OUT OUT_SQLSTATE            TEXT,
    OUT OUT_SQLMSG              TEXT,
    OUT OUT_SQLERRMC            TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    -- V_START_TS is the transaction timestamp and stamps the version window;
    -- the log needs wall-clock, which CURRENT_TIMESTAMP does not advance.
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_BAR_SUBSCRIPTION_ID=' || COALESCE(IN_BAR_SUBSCRIPTION_ID::TEXT, '')
                 || ', IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '')
                 || ', IN_TM_INTERVAL_ID=' || COALESCE(IN_TM_INTERVAL_ID::TEXT, '')
                 || ', IN_SOURCE_APP_ID=' || COALESCE(IN_SOURCE_APP_ID::TEXT, '')
                 || ', IN_IS_ENABLED_IND=' || COALESCE(IN_IS_ENABLED_IND, '');

    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(BAR_SUBSCRIPTION_VID), 0) + 1
      INTO V_VID
      FROM MARKET_DATA.BAR_SUBSCRIPTION
     WHERE BAR_SUBSCRIPTION_ID = IN_BAR_SUBSCRIPTION_ID;

    OUT_SQLMSG := '20';
    UPDATE MARKET_DATA.BAR_SUBSCRIPTION
       SET TRANSACT_TO_TS = V_START_TS
     WHERE BAR_SUBSCRIPTION_ID = IN_BAR_SUBSCRIPTION_ID
       AND TRANSACT_TO_TS      = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    OUT_SQLMSG := '30';
    INSERT INTO MARKET_DATA.BAR_SUBSCRIPTION (
        BAR_SUBSCRIPTION_ID,
        BAR_SUBSCRIPTION_VID,
        INTERNAL_CUSIP,
        TM_INTERVAL_ID,
        SOURCE_APP_ID,
        IS_ENABLED_IND,
        BACKFILL_FROM_TS,
        TRANSACT_FROM_TS,
        TRANSACT_TO_TS,
        CREATED_AT
    ) VALUES (
        IN_BAR_SUBSCRIPTION_ID,
        V_VID,
        IN_INTERNAL_CUSIP,
        IN_TM_INTERVAL_ID,
        IN_SOURCE_APP_ID,
        IN_IS_ENABLED_IND,
        IN_BACKFILL_FROM_TS,
        V_START_TS,
        TIMESTAMPTZ '9999-12-31 00:00:00+00',
        NOW()
    );

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_INS_BAR_SUBSCRIPTION', V_LOG_START, NULL, V_OTHER_TEXT,
        IN_USER_ID, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_INS_BAR_SUBSCRIPTION] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_INS_BAR_SUBSCRIPTION(
        UUID, TEXT, INTEGER, INTEGER, CHAR(1), TIMESTAMPTZ, TEXT,
        OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
