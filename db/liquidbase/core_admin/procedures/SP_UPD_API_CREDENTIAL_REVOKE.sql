-- Soft-version revoke: demote current row and insert IS_ACTIVE_IND='N' with
-- cleared ciphertext. Caller must own the credential (IN_APP_USER_ID).
CREATE OR REPLACE PROCEDURE CORE_ADMIN.SP_UPD_API_CREDENTIAL_REVOKE(
    IN  IN_APP_USER_ID           UUID,
    IN  IN_API_CREDENTIAL_ID     INTEGER,
    OUT OUT_API_CREDENTIAL_VID   INTEGER,
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
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_OWNER      UUID;
    V_APP_ID     INTEGER;
    V_LABEL      TEXT;
BEGIN
    OUT_SQLSTATE           := '00000';
    OUT_SQLMSG             := '0';
    OUT_SQLERRMC           := 'Stored Procedure completed successfully';
    OUT_API_CREDENTIAL_VID := NULL;

    V_OTHER_TEXT := 'IN_APP_USER_ID=' || COALESCE(IN_APP_USER_ID::TEXT, '')
                 || ', IN_API_CREDENTIAL_ID=' || COALESCE(IN_API_CREDENTIAL_ID::TEXT, '');

    OUT_SQLMSG := '10';
    IF IN_APP_USER_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_APP_USER_ID is required';
        RETURN;
    END IF;
    IF IN_API_CREDENTIAL_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_API_CREDENTIAL_ID is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '20';
    SELECT APP_USER_ID, APP_ID, LABEL
      INTO V_OWNER, V_APP_ID, V_LABEL
      FROM CORE_ADMIN.API_CREDENTIAL
     WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID
       AND IS_CURRENT_IND    = 'Y'
       AND IS_ACTIVE_IND     = 'Y';

    IF V_OWNER IS NULL THEN
        OUT_SQLSTATE := '02000';
        OUT_SQLERRMC := 'API_CREDENTIAL_ID not found or already revoked';
        RETURN;
    END IF;
    IF V_OWNER <> IN_APP_USER_ID THEN
        OUT_SQLSTATE := '42501';
        OUT_SQLERRMC := 'API_CREDENTIAL_ID does not belong to APP_USER_ID';
        RETURN;
    END IF;

    OUT_SQLMSG := '30';
    SELECT COALESCE(MAX(API_CREDENTIAL_VID), 0) + 1
      INTO V_VID
      FROM CORE_ADMIN.API_CREDENTIAL
     WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID;

    OUT_SQLMSG := '40';
    UPDATE CORE_ADMIN.API_CREDENTIAL
       SET IS_CURRENT_IND = 'N'
     WHERE API_CREDENTIAL_ID = IN_API_CREDENTIAL_ID
       AND IS_CURRENT_IND    = 'Y';

    OUT_SQLMSG := '50';
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
        IN_API_CREDENTIAL_ID,
        V_VID,
        IN_APP_USER_ID,
        V_APP_ID,
        V_LABEL,
        '',
        '',
        'N',
        'Y',
        NOW() AT TIME ZONE 'UTC'
    );

    OUT_API_CREDENTIAL_VID := V_VID;

    OUT_SQLMSG := '60';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'CORE_ADMIN', 'SP_UPD_API_CREDENTIAL_REVOKE', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_UPD_API_CREDENTIAL_REVOKE] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_API_CREDENTIAL_REVOKE(
        UUID, INTEGER, OUT INTEGER, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
