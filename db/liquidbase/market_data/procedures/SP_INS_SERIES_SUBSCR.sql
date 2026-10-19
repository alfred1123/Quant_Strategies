-- Create or version one series subscription.
--
-- The row the system versions is IN_SERIES_SUBSCR_ID. Interval, product,
-- source and metric are attributes of that id. A venue's bars pass a
-- null metric.
--
-- Enabling, disabling and retargeting the wanted history take that path:
-- close the open row and insert VID + 1. IN_USER_ID is the audit log, not
-- a column. Subscriptions are platform-wide.

CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_INS_SERIES_SUBSCR(
    IN  IN_SERIES_SUBSCR_ID  UUID,
    IN  IN_INTERNAL_CUSIP      TEXT,
    IN  IN_APP_ID              INTEGER,
    IN  IN_APP_METRIC_ID       INTEGER,
    IN  IN_TM_INTERVAL_ID      INTEGER,
    IN  IN_IS_ENABLED_IND      CHAR(1),
    IN  IN_BACKFILL_FROM_TS    TIMESTAMPTZ,
    IN  IN_USER_ID             TEXT,
    OUT OUT_SQLSTATE           TEXT,
    OUT OUT_SQLMSG             TEXT,
    OUT OUT_SQLERRMC           TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    OUT_SQLMSG := '10';
    V_OTHER_TEXT := 'IN_SERIES_SUBSCR_ID=' || COALESCE(IN_SERIES_SUBSCR_ID::TEXT, '')
                 || ', IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '')
                 || ', IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '')
                 || ', IN_APP_METRIC_ID=' || COALESCE(IN_APP_METRIC_ID::TEXT, '')
                 || ', IN_TM_INTERVAL_ID=' || COALESCE(IN_TM_INTERVAL_ID::TEXT, '')
                 || ', IN_IS_ENABLED_IND=' || COALESCE(IN_IS_ENABLED_IND, '');

    OUT_SQLMSG := '20';
    SELECT COALESCE(MAX(SERIES_SUBSCR_VID), 0) + 1
      INTO V_VID
      FROM MARKET_DATA.SERIES_SUBSCR
     WHERE SERIES_SUBSCR_ID = IN_SERIES_SUBSCR_ID;

    OUT_SQLMSG := '30';
    UPDATE MARKET_DATA.SERIES_SUBSCR
       SET TRANSACT_TO_TS = V_START_TS
     WHERE SERIES_SUBSCR_ID = IN_SERIES_SUBSCR_ID
       AND TRANSACT_TO_TS     = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    OUT_SQLMSG := '40';
    INSERT INTO MARKET_DATA.SERIES_SUBSCR (
        SERIES_SUBSCR_ID,
        SERIES_SUBSCR_VID,
        INTERNAL_CUSIP,
        APP_ID,
        APP_METRIC_ID,
        TM_INTERVAL_ID,
        IS_ENABLED_IND,
        BACKFILL_FROM_TS,
        TRANSACT_FROM_TS,
        TRANSACT_TO_TS,
        CREATED_AT
    ) VALUES (
        IN_SERIES_SUBSCR_ID,
        V_VID,
        IN_INTERNAL_CUSIP,
        IN_APP_ID,
        IN_APP_METRIC_ID,
        IN_TM_INTERVAL_ID,
        IN_IS_ENABLED_IND,
        IN_BACKFILL_FROM_TS,
        V_START_TS,
        TIMESTAMPTZ '9999-12-31 00:00:00+00',
        NOW()
    );

    OUT_SQLMSG := '50';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_INS_SERIES_SUBSCR', V_LOG_START, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_SERIES_SUBSCR] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
        GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_INS_SERIES_SUBSCR(
            UUID, TEXT, INTEGER, INTEGER, INTEGER, CHAR(1), TIMESTAMPTZ, TEXT,
            OUT TEXT, OUT TEXT, OUT TEXT
        ) TO quant_app;
    END IF;
END $$;
