CREATE OR REPLACE PROCEDURE INST.SP_GET_PRODUCT(
    IN  IN_PRODUCT_ID      INTEGER,
    IN  IN_INTERNAL_CUSIP  TEXT,
    OUT OUT_RESULT         REFCURSOR,
    OUT OUT_SQLSTATE       TEXT,
    OUT OUT_SQLMSG         TEXT,
    OUT OUT_SQLERRMC       TEXT
)
LANGUAGE plpgsql
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

    V_OTHER_TEXT := 'IN_PRODUCT_ID=' || COALESCE(IN_PRODUCT_ID::TEXT, '')
                 || ', IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '');

    -- Step 10: Return current rows using explicit filter branches
    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_product_cursor';

    IF IN_PRODUCT_ID IS NULL AND IN_INTERNAL_CUSIP IS NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                p.PRODUCT_ID,
                p.PRODUCT_VID,
                p.IS_CURRENT_IND,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                p.ASSET_TYPE_ID,
                p.EXCHANGE,
                p.CCY,
                p.DESCRIPTION
            FROM INST.PRODUCT p
            WHERE p.IS_CURRENT_IND = 'Y';

    ELSIF IN_PRODUCT_ID IS NOT NULL AND IN_INTERNAL_CUSIP IS NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                p.PRODUCT_ID,
                p.PRODUCT_VID,
                p.IS_CURRENT_IND,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                p.ASSET_TYPE_ID,
                p.EXCHANGE,
                p.CCY,
                p.DESCRIPTION
            FROM INST.PRODUCT p
            WHERE p.IS_CURRENT_IND = 'Y'
              AND p.PRODUCT_ID = IN_PRODUCT_ID;

    ELSIF IN_PRODUCT_ID IS NULL AND IN_INTERNAL_CUSIP IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                p.PRODUCT_ID,
                p.PRODUCT_VID,
                p.IS_CURRENT_IND,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                p.ASSET_TYPE_ID,
                p.EXCHANGE,
                p.CCY,
                p.DESCRIPTION
            FROM INST.PRODUCT p
            WHERE p.IS_CURRENT_IND = 'Y'
              AND p.INTERNAL_CUSIP = IN_INTERNAL_CUSIP;

        ELSE
                OPEN OUT_RESULT FOR
                        SELECT
                                p.PRODUCT_ID,
                                p.PRODUCT_VID,
                                p.IS_CURRENT_IND,
                                p.INTERNAL_CUSIP,
                                p.DISPLAY_NM,
                                p.ASSET_TYPE_ID,
                                p.EXCHANGE,
                                p.CCY,
                                p.DESCRIPTION
                        FROM INST.PRODUCT p
                        WHERE p.IS_CURRENT_IND = 'Y'
                            AND p.PRODUCT_ID = IN_PRODUCT_ID
                            AND p.INTERNAL_CUSIP = IN_INTERNAL_CUSIP;
    END IF;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('INST', 'SP_GET_PRODUCT', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_PRODUCT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
