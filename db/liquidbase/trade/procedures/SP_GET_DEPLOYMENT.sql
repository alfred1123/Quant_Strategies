-- Read TRADE.DEPLOYMENT rows.
--
-- IN_APP_USER_ID     required — scope to owner.
-- IN_DEPLOYMENT_ID   optional — when set, filter to one logical deployment.
-- IN_DEPLOYMENT_VID  optional — when set with DEPLOYMENT_ID, return that
--                    exact version (including closed rows). When NULL with
--                    DEPLOYMENT_ID, return the current open row only.
-- When IN_DEPLOYMENT_ID is NULL, returns all current deployments for the user.
--
-- NEXT_DUE_AT = current DEPLOYMENT_SCHEDULE_STATUS.SCHEDULED_TS (IS_CURRENT_IND = 'Y').
-- LAST_RUN_AT = NEXT_DUE_AT - interval when schedule VID > 1 (prior tick completed).
-- TRANSACT_FROM_TS = when this deployment version became effective (user-facing).
-- Does not expose CREATED_AT (audit only) or TRANSACT_TO_TS (versioning sentinel).
-- Filter / ownership validation lives in Python (TradeRepo).
CREATE OR REPLACE PROCEDURE TRADE.SP_GET_DEPLOYMENT(
    IN  IN_APP_USER_ID      UUID,
    IN  IN_DEPLOYMENT_ID    UUID,
    IN  IN_DEPLOYMENT_VID   INTEGER,
    OUT OUT_RESULT          REFCURSOR,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_APP_USER_ID=' || COALESCE(IN_APP_USER_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_VID=' || COALESCE(IN_DEPLOYMENT_VID::TEXT, '');

    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_deployment_cursor';

    IF IN_DEPLOYMENT_ID IS NOT NULL AND IN_DEPLOYMENT_VID IS NOT NULL THEN
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
                   CASE
                       WHEN ss.STATUS = 'PENDING'
                        AND ss.DEPLOYMENT_SCHEDULE_VID > 1
                       THEN ss.SCHEDULED_TS - ti.PERIOD_LENGTH
                   END AS LAST_RUN_AT,
                   CASE
                       WHEN ss.STATUS = 'PENDING'
                       THEN ss.SCHEDULED_TS
                   END AS NEXT_DUE_AT,
                   d.TRANSACT_FROM_TS,
                   d.USER_ID
              FROM TRADE.DEPLOYMENT d
              LEFT JOIN REFDATA.TM_INTERVAL ti
                ON ti.TM_INTERVAL_ID = d.SCHEDULE_TM_INTERVAL_ID
              LEFT JOIN TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
                ON ss.DEPLOYMENT_ID = d.DEPLOYMENT_ID
               AND ss.IS_CURRENT_IND = 'Y'
             WHERE d.DEPLOYMENT_ID  = IN_DEPLOYMENT_ID
               AND d.DEPLOYMENT_VID = IN_DEPLOYMENT_VID
               AND d.APP_USER_ID    = IN_APP_USER_ID
             ORDER BY d.DEPLOYMENT_VID DESC;

    ELSIF IN_DEPLOYMENT_ID IS NOT NULL THEN
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
                   CASE
                       WHEN ss.STATUS = 'PENDING'
                        AND ss.DEPLOYMENT_SCHEDULE_VID > 1
                       THEN ss.SCHEDULED_TS - ti.PERIOD_LENGTH
                   END AS LAST_RUN_AT,
                   CASE
                       WHEN ss.STATUS = 'PENDING'
                       THEN ss.SCHEDULED_TS
                   END AS NEXT_DUE_AT,
                   d.TRANSACT_FROM_TS,
                   d.USER_ID
              FROM TRADE.DEPLOYMENT d
              LEFT JOIN REFDATA.TM_INTERVAL ti
                ON ti.TM_INTERVAL_ID = d.SCHEDULE_TM_INTERVAL_ID
              LEFT JOIN TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
                ON ss.DEPLOYMENT_ID = d.DEPLOYMENT_ID
               AND ss.IS_CURRENT_IND = 'Y'
             WHERE d.DEPLOYMENT_ID  = IN_DEPLOYMENT_ID
               AND d.APP_USER_ID    = IN_APP_USER_ID
               AND d.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    ELSE
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
                   CASE
                       WHEN ss.STATUS = 'PENDING'
                        AND ss.DEPLOYMENT_SCHEDULE_VID > 1
                       THEN ss.SCHEDULED_TS - ti.PERIOD_LENGTH
                   END AS LAST_RUN_AT,
                   CASE
                       WHEN ss.STATUS = 'PENDING'
                       THEN ss.SCHEDULED_TS
                   END AS NEXT_DUE_AT,
                   d.TRANSACT_FROM_TS,
                   d.USER_ID
              FROM TRADE.DEPLOYMENT d
              LEFT JOIN REFDATA.TM_INTERVAL ti
                ON ti.TM_INTERVAL_ID = d.SCHEDULE_TM_INTERVAL_ID
              LEFT JOIN TRADE.DEPLOYMENT_SCHEDULE_STATUS ss
                ON ss.DEPLOYMENT_ID = d.DEPLOYMENT_ID
               AND ss.IS_CURRENT_IND = 'Y'
             WHERE d.APP_USER_ID    = IN_APP_USER_ID
               AND d.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
             ORDER BY d.TRANSACT_FROM_TS DESC;
    END IF;

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_DEPLOYMENT', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_GET_DEPLOYMENT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_GET_DEPLOYMENT(
        UUID, UUID, INTEGER,
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
