-- Read TRADE.EXECUTION_EVENT rows for one user.
--
-- IN_APP_USER_ID   required — scope via DEPLOYMENT ownership.
-- IN_DEPLOYMENT_ID optional — when set, filter to one logical deployment.
-- IN_LIMIT         optional — row cap (default 50); Python clamps the max.
--
-- Joins the deployment version stamped on the event so product / account
-- context matches the apply tick. Exposes TRANSACT_AT (diary time), not
-- CREATED_AT (audit). Filter / ownership validation lives in Python.
CREATE OR REPLACE PROCEDURE TRADE.SP_GET_EXECUTION_EVENT(
    IN  IN_APP_USER_ID      UUID,
    IN  IN_DEPLOYMENT_ID    UUID,
    IN  IN_LIMIT            INTEGER,
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
    V_LIMIT      INTEGER := COALESCE(NULLIF(IN_LIMIT, 0), 50);
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_APP_USER_ID=' || COALESCE(IN_APP_USER_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_LIMIT=' || COALESCE(IN_LIMIT::TEXT, '');

    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_execution_event_cursor';

    IF IN_DEPLOYMENT_ID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT e.EXECUTION_EVENT_ID,
                   e.DEPLOYMENT_ID,
                   e.DEPLOYMENT_VID,
                   d.INTERNAL_CUSIP,
                   d.API_CREDENTIAL_ID,
                   d.APP_ID,
                   d.IS_PAPER_IND,
                   e.SIGNAL_VALUE,
                   e.POSITION_QTY,
                   e.BUY_SELL_CD,
                   e.QUANTITY,
                   e.VENDOR_ORDER_ID,
                   e.IS_SUCCESS_IND,
                   e.TRANSACT_AT
              FROM TRADE.EXECUTION_EVENT e
              JOIN TRADE.DEPLOYMENT d
                ON d.DEPLOYMENT_ID  = e.DEPLOYMENT_ID
               AND d.DEPLOYMENT_VID = e.DEPLOYMENT_VID
             WHERE d.APP_USER_ID    = IN_APP_USER_ID
               AND e.DEPLOYMENT_ID  = IN_DEPLOYMENT_ID
             ORDER BY e.TRANSACT_AT DESC, e.CREATED_AT DESC
             LIMIT V_LIMIT;
    ELSE
        OPEN OUT_RESULT FOR
            SELECT e.EXECUTION_EVENT_ID,
                   e.DEPLOYMENT_ID,
                   e.DEPLOYMENT_VID,
                   d.INTERNAL_CUSIP,
                   d.API_CREDENTIAL_ID,
                   d.APP_ID,
                   d.IS_PAPER_IND,
                   e.SIGNAL_VALUE,
                   e.POSITION_QTY,
                   e.BUY_SELL_CD,
                   e.QUANTITY,
                   e.VENDOR_ORDER_ID,
                   e.IS_SUCCESS_IND,
                   e.TRANSACT_AT
              FROM TRADE.EXECUTION_EVENT e
              JOIN TRADE.DEPLOYMENT d
                ON d.DEPLOYMENT_ID  = e.DEPLOYMENT_ID
               AND d.DEPLOYMENT_VID = e.DEPLOYMENT_VID
             WHERE d.APP_USER_ID = IN_APP_USER_ID
             ORDER BY e.TRANSACT_AT DESC, e.CREATED_AT DESC
             LIMIT V_LIMIT;
    END IF;

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_EXECUTION_EVENT', V_LOG_START, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_GET_EXECUTION_EVENT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_GET_EXECUTION_EVENT(
        UUID, UUID, INTEGER,
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
