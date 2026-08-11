-- Validation read for deployment creation — fetch credential metadata
-- by API_CREDENTIAL_ID without owner scoping. The caller checks ownership
-- (app_user_id) and active status in application logic.
CREATE OR REPLACE PROCEDURE CORE_ADMIN.SP_GET_CREDENTIAL_CHECK(
    IN  IN_API_CREDENTIAL_ID  INTEGER,
    OUT OUT_RESULT             REFCURSOR,
    OUT OUT_SQLSTATE           TEXT,
    OUT OUT_SQLMSG             TEXT,
    OUT OUT_SQLERRMC           TEXT
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

    V_OTHER_TEXT := 'IN_API_CREDENTIAL_ID=' || COALESCE(IN_API_CREDENTIAL_ID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_credential_check_cursor';

    OPEN OUT_RESULT FOR
        SELECT APP_USER_ID,
               APP_ID,
               IS_ACTIVE_IND,
               IS_CURRENT_IND
          FROM CORE_ADMIN.API_CREDENTIAL
         WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID
           AND IS_CURRENT_IND    = 'Y';

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'CORE_ADMIN', 'SP_GET_CREDENTIAL_CHECK', V_LOG_START, NULL,
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

            RAISE WARNING '[SP_GET_CREDENTIAL_CHECK] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
