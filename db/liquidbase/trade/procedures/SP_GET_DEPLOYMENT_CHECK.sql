-- Validation read for deployment mutations — fetch deployment metadata
-- by DEPLOYMENT_ID without owner scoping. The caller checks ownership
-- (app_user_id) in application logic.
--
-- Two modes:
--   IN_DEPLOYMENT_VID set   => exact version (including closed rows)
--   IN_DEPLOYMENT_VID NULL  => current active row (TRANSACT_TO_TS = 9999-12-31)
CREATE OR REPLACE PROCEDURE TRADE.SP_GET_DEPLOYMENT_CHECK(
    IN  IN_DEPLOYMENT_ID   UUID,
    IN  IN_DEPLOYMENT_VID  INTEGER,
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

    V_OTHER_TEXT := 'IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_VID=' || COALESCE(IN_DEPLOYMENT_VID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_deployment_check_cursor';

    IF IN_DEPLOYMENT_VID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT APP_USER_ID,
                   APP_ID,
                   DEPLOYMENT_VID
              FROM TRADE.DEPLOYMENT
             WHERE DEPLOYMENT_ID  = IN_DEPLOYMENT_ID
               AND DEPLOYMENT_VID = IN_DEPLOYMENT_VID;
    ELSE
        OPEN OUT_RESULT FOR
            SELECT APP_USER_ID,
                   APP_ID,
                   DEPLOYMENT_VID
              FROM TRADE.DEPLOYMENT
             WHERE DEPLOYMENT_ID = IN_DEPLOYMENT_ID
               AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';
    END IF;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_GET_DEPLOYMENT_CHECK', V_LOG_START, NULL,
        V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_DEPLOYMENT_CHECK] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
