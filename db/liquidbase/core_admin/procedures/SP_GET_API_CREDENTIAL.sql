-- List or get current exchange API credentials for an app user.
--
-- IN_API_CREDENTIAL_ID NULL => all current active rows for IN_APP_USER_ID.
-- IN_API_CREDENTIAL_ID set  => one current active row (404-equivalent empty
--                               cursor if not found or wrong owner).
--
-- Returns IS_CURRENT_IND='Y' and IS_ACTIVE_IND='Y' rows only.
CREATE OR REPLACE PROCEDURE CORE_ADMIN.SP_GET_API_CREDENTIAL(
    IN  IN_APP_USER_ID           UUID,
    IN  IN_API_CREDENTIAL_ID     INTEGER,
    OUT OUT_RESULT               REFCURSOR,
    OUT OUT_SQLSTATE             TEXT,
    OUT OUT_SQLMSG               TEXT,
    OUT OUT_SQLERRMC             TEXT
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
                 || ', IN_API_CREDENTIAL_ID=' || COALESCE(IN_API_CREDENTIAL_ID::TEXT, '');

    OUT_SQLMSG := '10';
    IF IN_APP_USER_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_APP_USER_ID is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_api_credential_cursor';

    IF IN_API_CREDENTIAL_ID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT API_CREDENTIAL_ID,
                   API_CREDENTIAL_VID,
                   APP_USER_ID,
                   APP_ID,
                   LABEL,
                   API_KEY_CIPHERTEXT,
                   API_SECRET_CIPHERTEXT,
                   IS_ACTIVE_IND,
                   IS_CURRENT_IND
              FROM CORE_ADMIN.API_CREDENTIAL
             WHERE APP_USER_ID       = IN_APP_USER_ID
               AND API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID
               AND IS_CURRENT_IND    = 'Y'
               AND IS_ACTIVE_IND     = 'Y';
    ELSE
        OPEN OUT_RESULT FOR
            SELECT API_CREDENTIAL_ID,
                   API_CREDENTIAL_VID,
                   APP_USER_ID,
                   APP_ID,
                   LABEL,
                   API_KEY_CIPHERTEXT,
                   API_SECRET_CIPHERTEXT,
                   IS_ACTIVE_IND,
                   IS_CURRENT_IND
              FROM CORE_ADMIN.API_CREDENTIAL
             WHERE APP_USER_ID    = IN_APP_USER_ID
               AND IS_CURRENT_IND = 'Y'
               AND IS_ACTIVE_IND  = 'Y'
             ORDER BY API_CREDENTIAL_ID;
    END IF;

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'CORE_ADMIN', 'SP_GET_API_CREDENTIAL', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_GET_API_CREDENTIAL] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_API_CREDENTIAL(
        UUID, INTEGER, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
