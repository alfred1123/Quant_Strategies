CREATE OR REPLACE PROCEDURE REFDATA.SP_GET_ENUM(
    IN  IN_TABLE_NM    TEXT,
    OUT OUT_RESULT      REFCURSOR,
    OUT OUT_SQLSTATE   TEXT,
    OUT OUT_SQLMSG     TEXT,
    OUT OUT_SQLERRMC   TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_TABLE_OK   BOOLEAN;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_TABLE_NM=' || COALESCE(IN_TABLE_NM, '');

    -- Step 10: Validate table exists in REFDATA schema
    OUT_SQLMSG := '10';
    SELECT EXISTS (
        SELECT 1
          FROM pg_tables
         WHERE schemaname = 'refdata'
           AND tablename  = LOWER(IN_TABLE_NM)
    ) INTO V_TABLE_OK;

    IF NOT V_TABLE_OK THEN
        OUT_SQLSTATE := 'P0001';
        OUT_SQLERRMC := 'Table not found in REFDATA schema: ' || COALESCE(IN_TABLE_NM, 'NULL');
        RETURN;
    END IF;

    -- Step 20: Open cursor with all rows from the requested table
    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_enum_cursor';
    OPEN OUT_RESULT FOR EXECUTE format('SELECT * FROM REFDATA.%I', LOWER(IN_TABLE_NM));

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('REFDATA', 'SP_GET_ENUM', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_ENUM] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
