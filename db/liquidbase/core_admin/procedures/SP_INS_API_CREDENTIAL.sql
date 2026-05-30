-- Insert a new exchange API credential or rotate keys (soft-version).
--
-- IN_API_CREDENTIAL_ID NULL  => new account: SP assigns next API_CREDENTIAL_ID
--                               (MAX+1 globally), API_CREDENTIAL_VID = 1.
-- IN_API_CREDENTIAL_ID set   => rotate: demote current row, insert VID+1 for
--                               the same API_CREDENTIAL_ID (must belong to
--                               IN_APP_USER_ID).
CREATE OR REPLACE PROCEDURE CORE_ADMIN.SP_INS_API_CREDENTIAL(
    IN  IN_APP_USER_ID              UUID,
    IN  IN_APP_ID                   INTEGER,
    IN  IN_LABEL                    TEXT,
    IN  IN_API_KEY_CIPHERTEXT       TEXT,
    IN  IN_API_SECRET_CIPHERTEXT    TEXT,
    IN  IN_API_CREDENTIAL_ID        INTEGER,
    OUT OUT_SQLSTATE                TEXT,
    OUT OUT_SQLMSG                  TEXT,
    OUT OUT_SQLERRMC                TEXT,
    OUT OUT_API_CREDENTIAL_ID       INTEGER,
    OUT OUT_API_CREDENTIAL_VID      INTEGER
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_OWNER      UUID;
BEGIN
    OUT_SQLSTATE           := '00000';
    OUT_SQLMSG             := '0';
    OUT_SQLERRMC           := 'Stored Procedure completed successfully';
    OUT_API_CREDENTIAL_ID  := NULL;
    OUT_API_CREDENTIAL_VID := NULL;

    V_OTHER_TEXT := 'IN_APP_USER_ID=' || COALESCE(IN_APP_USER_ID::TEXT, '')
                 || ', IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '')
                 || ', IN_LABEL=' || COALESCE(IN_LABEL, '')
                 || ', IN_API_CREDENTIAL_ID=' || COALESCE(IN_API_CREDENTIAL_ID::TEXT, '');

    OUT_SQLMSG := '10';
    IF IN_APP_USER_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_APP_USER_ID is required';
        RETURN;
    END IF;
    IF IN_APP_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_APP_ID is required';
        RETURN;
    END IF;
    IF IN_LABEL IS NULL OR BTRIM(IN_LABEL) = '' THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_LABEL is required';
        RETURN;
    END IF;
    IF IN_API_KEY_CIPHERTEXT IS NULL OR BTRIM(IN_API_KEY_CIPHERTEXT) = '' THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_API_KEY_CIPHERTEXT is required';
        RETURN;
    END IF;
    IF IN_API_SECRET_CIPHERTEXT IS NULL OR BTRIM(IN_API_SECRET_CIPHERTEXT) = '' THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_API_SECRET_CIPHERTEXT is required';
        RETURN;
    END IF;

    IF IN_API_CREDENTIAL_ID IS NULL THEN
        OUT_SQLMSG := '20';
        SELECT COALESCE(MAX(API_CREDENTIAL_ID), 0) + 1
          INTO OUT_API_CREDENTIAL_ID
          FROM CORE_ADMIN.API_CREDENTIAL;

        V_VID := 1;
    ELSE
        OUT_SQLMSG := '20';
        OUT_API_CREDENTIAL_ID := IN_API_CREDENTIAL_ID;

        SELECT APP_USER_ID
          INTO V_OWNER
          FROM CORE_ADMIN.API_CREDENTIAL
         WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID
           AND IS_CURRENT_IND    = 'Y';

        IF V_OWNER IS NULL THEN
            OUT_SQLSTATE := '02000';
            OUT_SQLERRMC := 'API_CREDENTIAL_ID not found';
            RETURN;
        END IF;
        IF V_OWNER <> IN_APP_USER_ID THEN
            OUT_SQLSTATE := '42501';
            OUT_SQLERRMC := 'API_CREDENTIAL_ID does not belong to APP_USER_ID';
            RETURN;
        END IF;

        OUT_SQLMSG := '25';
        SELECT COALESCE(MAX(API_CREDENTIAL_VID), 0) + 1
          INTO V_VID
          FROM CORE_ADMIN.API_CREDENTIAL
         WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID;

        OUT_SQLMSG := '30';
        UPDATE CORE_ADMIN.API_CREDENTIAL
           SET IS_CURRENT_IND = 'N'
         WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID
           AND IS_CURRENT_IND    = 'Y';
    END IF;

    OUT_SQLMSG := '40';
    INSERT INTO CORE_ADMIN.API_CREDENTIAL (
        API_CREDENTIAL_ID,
        API_CREDENTIAL_VID,
        APP_USER_ID,
        APP_ID,
        LABEL,
        API_KEY_CIPHERTEXT,
        API_SECRET_CIPHERTEXT,
        IS_ACTIVE_IND,
        IS_CURRENT_IND,
        CREATED_AT
    ) VALUES (
        OUT_API_CREDENTIAL_ID,
        V_VID,
        IN_APP_USER_ID,
        IN_APP_ID,
        IN_LABEL,
        IN_API_KEY_CIPHERTEXT,
        IN_API_SECRET_CIPHERTEXT,
        'Y',
        'Y',
        NOW() AT TIME ZONE 'UTC'
    );

    OUT_API_CREDENTIAL_VID := V_VID;

    OUT_SQLMSG := '50';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'CORE_ADMIN', 'SP_INS_API_CREDENTIAL', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_API_CREDENTIAL] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_INS_API_CREDENTIAL(
        UUID, INTEGER, TEXT, TEXT, TEXT, INTEGER,
        OUT TEXT, OUT TEXT, OUT TEXT, OUT INTEGER, OUT INTEGER
    ) TO quant_app;
  END IF;
END $$;
