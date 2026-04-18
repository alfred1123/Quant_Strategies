CREATE OR REPLACE PROCEDURE INST.SP_INS_PRODUCT(
    IN  IN_PRODUCT_ID     INTEGER,
    IN  IN_INTERNAL_CUSIP TEXT,
    IN  IN_DISPLAY_NM     TEXT,
    IN  IN_ASSET_TYPE_ID  INTEGER,
    IN  IN_EXCHANGE       TEXT,
    IN  IN_CCY            TEXT,
    IN  IN_DESCRIPTION    TEXT,
    IN  IN_USER_ID        TEXT,
    OUT OUT_SQLSTATE      TEXT,
    OUT OUT_SQLMSG        TEXT,
    OUT OUT_SQLERRMC      TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_PRODUCT_ID=' || COALESCE(IN_PRODUCT_ID::TEXT, '')
                 || ', IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '')
                 || ', IN_DISPLAY_NM=' || COALESCE(IN_DISPLAY_NM, '');

    -- Step 10: Resolve VID — get current max, or start at 1
    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(PRODUCT_VID), 0) + 1
      INTO V_VID
      FROM INST.PRODUCT
     WHERE PRODUCT_ID = IN_PRODUCT_ID;

    -- Step 20: Flip old current row(s) to 'N'
    OUT_SQLMSG := '20';
    UPDATE INST.PRODUCT
       SET IS_CURRENT_IND = 'N'
     WHERE PRODUCT_ID     = IN_PRODUCT_ID
       AND IS_CURRENT_IND = 'Y';

    -- Step 30: Insert new version as current
    OUT_SQLMSG := '30';
    INSERT INTO INST.PRODUCT (
        PRODUCT_ID,
        PRODUCT_VID,
        IS_CURRENT_IND,
        INTERNAL_CUSIP,
        DISPLAY_NM,
        ASSET_TYPE_ID,
        EXCHANGE,
        CCY,
        DESCRIPTION,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_PRODUCT_ID,
        V_VID,
        'Y',
        IN_INTERNAL_CUSIP,
        IN_DISPLAY_NM,
        IN_ASSET_TYPE_ID,
        IN_EXCHANGE,
        IN_CCY,
        IN_DESCRIPTION,
        IN_USER_ID,
        NOW()
    );

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('INST', 'SP_INS_PRODUCT', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_PRODUCT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
