-- Create or version a live deployment (apply).
--
-- Caller supplies IN_DEPLOYMENT_ID (UUID v7). First insert for that id =>
-- DEPLOYMENT_VID = 1. Subsequent config changes close the open row
-- (TRANSACT_TO_TS = now()) and insert DEPLOYMENT_VID + 1.
--
-- SCHEDULE_TM_INTERVAL_ID NULL = manual-only (no scheduler row).
-- Scheduler state lives in TRADE.DEPLOYMENT_SCHEDULE_STATUS (not EXECUTION_EVENT).
-- Input validation and ownership checks live in Python (TradeRepo).
CREATE OR REPLACE PROCEDURE TRADE.SP_INS_DEPLOYMENT(
    IN  IN_DEPLOYMENT_ID              UUID,
    IN  IN_APP_USER_ID                UUID,
    IN  IN_STRATEGY_ID                UUID,
    IN  IN_STRATEGY_VID               INTEGER,
    IN  IN_API_CREDENTIAL_ID          INTEGER,
    IN  IN_APP_ID                     INTEGER,
    IN  IN_INTERNAL_CUSIP             TEXT,
    IN  IN_QTY                        NUMERIC,
    IN  IN_IS_PAPER_IND               CHAR(1),
    IN  IN_IS_ENABLED_IND             CHAR(1),
    IN  IN_DEPLOYMENT_STATUS          TEXT,
    IN  IN_SCHEDULE_TM_INTERVAL_ID    INTEGER,
    IN  IN_USER_ID                    TEXT,
    OUT OUT_SQLSTATE                  TEXT,
    OUT OUT_SQLMSG                    TEXT,
    OUT OUT_SQLERRMC                  TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS            TIMESTAMPTZ := CURRENT_TIMESTAMP;
    -- V_START_TS is the transaction timestamp and stamps the version window;
    -- the log needs wall-clock, which CURRENT_TIMESTAMP does not advance.
    V_LOG_START           TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT          TEXT;
    V_VID                 INTEGER;
    V_LOG_STATE           TEXT;
    V_LOG_MSG             TEXT;
    V_PRIOR_STATUS        TEXT;
    V_PRIOR_SCHEDULED_TS  TIMESTAMPTZ;
    V_SCHEDULE_STATUS     TEXT;
    V_SCHEDULED_TS        TIMESTAMPTZ;
    V_SS_STATE            TEXT;
    V_SS_MSG              TEXT;
    V_SS_ERR              TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_APP_USER_ID=' || COALESCE(IN_APP_USER_ID::TEXT, '')
                 || ', IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '')
                 || ', IN_API_CREDENTIAL_ID=' || COALESCE(IN_API_CREDENTIAL_ID::TEXT, '');

    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(DEPLOYMENT_VID), 0) + 1
      INTO V_VID
      FROM TRADE.DEPLOYMENT
     WHERE DEPLOYMENT_ID = IN_DEPLOYMENT_ID;

    OUT_SQLMSG := '20';
    UPDATE TRADE.DEPLOYMENT
       SET TRANSACT_TO_TS = V_START_TS
     WHERE DEPLOYMENT_ID  = IN_DEPLOYMENT_ID
       AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    OUT_SQLMSG := '30';
    INSERT INTO TRADE.DEPLOYMENT (
        DEPLOYMENT_ID,
        DEPLOYMENT_VID,
        APP_USER_ID,
        STRATEGY_ID,
        STRATEGY_VID,
        API_CREDENTIAL_ID,
        APP_ID,
        INTERNAL_CUSIP,
        QTY,
        IS_PAPER_IND,
        IS_ENABLED_IND,
        DEPLOYMENT_STATUS,
        SCHEDULE_TM_INTERVAL_ID,
        TRANSACT_FROM_TS,
        TRANSACT_TO_TS,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_DEPLOYMENT_ID,
        V_VID,
        IN_APP_USER_ID,
        IN_STRATEGY_ID,
        IN_STRATEGY_VID,
        IN_API_CREDENTIAL_ID,
        IN_APP_ID,
        IN_INTERNAL_CUSIP,
        IN_QTY,
        IN_IS_PAPER_IND,
        IN_IS_ENABLED_IND,
        IN_DEPLOYMENT_STATUS,
        IN_SCHEDULE_TM_INTERVAL_ID,
        V_START_TS,
        TIMESTAMPTZ '9999-12-31 00:00:00+00',
        IN_USER_ID,
        NOW()
    );

    OUT_SQLMSG := '35';
    IF IN_SCHEDULE_TM_INTERVAL_ID IS NOT NULL THEN
        IF V_VID = 1 THEN
            V_SCHEDULE_STATUS := 'PENDING';
            V_SCHEDULED_TS    := V_START_TS;
        ELSE
            SELECT ss.STATUS,
                   ss.SCHEDULED_TS
              INTO V_PRIOR_STATUS,
                   V_PRIOR_SCHEDULED_TS
              FROM TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
             WHERE ss.DEPLOYMENT_ID = IN_DEPLOYMENT_ID
               AND ss.IS_CURRENT_IND = 'Y';

            V_SCHEDULED_TS := COALESCE(V_PRIOR_SCHEDULED_TS, V_START_TS);

            IF IN_DEPLOYMENT_STATUS = 'STOPPED'
               OR IN_IS_ENABLED_IND = 'N'
               OR IN_DEPLOYMENT_STATUS = 'PAUSED' THEN
                V_SCHEDULE_STATUS := 'SUCCESS';
            ELSE
                V_SCHEDULE_STATUS := 'PENDING';
            END IF;
        END IF;

        CALL TRADE.SP_INS_DEPLOYMENT_SCHEDULE_STATUS(
            IN_DEPLOYMENT_ID,
            IN_DEPLOYMENT_ID,
            V_VID,
            V_SCHEDULE_STATUS,
            V_SCHEDULED_TS,
            IN_USER_ID,
            V_SS_STATE,
            V_SS_MSG,
            V_SS_ERR
        );
    ELSIF V_VID > 1 THEN
        SELECT ss.STATUS,
               ss.SCHEDULED_TS
          INTO V_PRIOR_STATUS,
               V_PRIOR_SCHEDULED_TS
          FROM TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
         WHERE ss.DEPLOYMENT_ID = IN_DEPLOYMENT_ID
           AND ss.IS_CURRENT_IND = 'Y';

        IF V_PRIOR_STATUS IS NOT NULL THEN
            CALL TRADE.SP_INS_DEPLOYMENT_SCHEDULE_STATUS(
                IN_DEPLOYMENT_ID,
                IN_DEPLOYMENT_ID,
                V_VID,
                'SUCCESS',
                COALESCE(V_PRIOR_SCHEDULED_TS, V_START_TS),
                IN_USER_ID,
                V_SS_STATE,
                V_SS_MSG,
                V_SS_ERR
            );
        END IF;
    END IF;

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_INS_DEPLOYMENT', V_LOG_START, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_DEPLOYMENT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_INS_DEPLOYMENT(
        UUID, UUID, UUID, INTEGER, INTEGER, INTEGER, TEXT, NUMERIC,
        CHAR(1), CHAR(1), TEXT, INTEGER, TEXT,
        OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
