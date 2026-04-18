CREATE OR REPLACE PROCEDURE INST.SP_GET_PRODUCT_XREF(
    IN  IN_PRODUCT_XREF_ID  INTEGER,
    IN  IN_PRODUCT_ID       INTEGER,
    IN  IN_APP_ID           INTEGER,
    OUT OUT_RESULT          REFCURSOR,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
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

    V_OTHER_TEXT := 'IN_PRODUCT_XREF_ID=' || COALESCE(IN_PRODUCT_XREF_ID::TEXT, '')
                 || ', IN_PRODUCT_ID=' || COALESCE(IN_PRODUCT_ID::TEXT, '')
                 || ', IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '');

    -- Step 10: Return current rows using explicit filter branches
    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_product_xref_cursor';

    IF IN_PRODUCT_XREF_ID IS NULL AND IN_PRODUCT_ID IS NULL AND IN_APP_ID IS NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
            INNER JOIN INST.PRODUCT p
                ON p.PRODUCT_ID = x.PRODUCT_ID
               AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
            ORDER BY x.PRODUCT_XREF_ID;

    ELSIF IN_PRODUCT_XREF_ID IS NOT NULL AND IN_PRODUCT_ID IS NULL AND IN_APP_ID IS NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.PRODUCT_XREF_ID = IN_PRODUCT_XREF_ID
            ORDER BY x.PRODUCT_XREF_ID;

    ELSIF IN_PRODUCT_XREF_ID IS NULL AND IN_PRODUCT_ID IS NOT NULL AND IN_APP_ID IS NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.PRODUCT_ID = IN_PRODUCT_ID
            ORDER BY x.PRODUCT_XREF_ID;

    ELSIF IN_PRODUCT_XREF_ID IS NULL AND IN_PRODUCT_ID IS NULL AND IN_APP_ID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.APP_ID = IN_APP_ID
            ORDER BY x.PRODUCT_XREF_ID;

    ELSIF IN_PRODUCT_XREF_ID IS NOT NULL AND IN_PRODUCT_ID IS NOT NULL AND IN_APP_ID IS NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.PRODUCT_XREF_ID = IN_PRODUCT_XREF_ID
              AND x.PRODUCT_ID = IN_PRODUCT_ID
            ORDER BY x.PRODUCT_XREF_ID;

    ELSIF IN_PRODUCT_XREF_ID IS NOT NULL AND IN_PRODUCT_ID IS NULL AND IN_APP_ID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.PRODUCT_XREF_ID = IN_PRODUCT_XREF_ID
              AND x.APP_ID = IN_APP_ID
            ORDER BY x.PRODUCT_XREF_ID;

    ELSIF IN_PRODUCT_XREF_ID IS NULL AND IN_PRODUCT_ID IS NOT NULL AND IN_APP_ID IS NOT NULL THEN
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.PRODUCT_ID = IN_PRODUCT_ID
              AND x.APP_ID = IN_APP_ID
            ORDER BY x.PRODUCT_XREF_ID;

    ELSE
        OPEN OUT_RESULT FOR
            SELECT
                x.PRODUCT_XREF_ID,
                x.PRODUCT_XREF_VID,
                x.PRODUCT_ID,
                p.INTERNAL_CUSIP,
                p.DISPLAY_NM,
                x.APP_ID,
                x.VENDOR_SYMBOL,
                x.TRANSACT_FROM_TS,
                x.TRANSACT_TO_TS,
                'Y' AS IS_CURRENT_IND
            FROM INST.PRODUCT_XREF x
                        INNER JOIN INST.PRODUCT p
                                ON p.PRODUCT_ID = x.PRODUCT_ID
                             AND p.IS_CURRENT_IND = 'Y'
            WHERE x.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
              AND x.PRODUCT_XREF_ID = IN_PRODUCT_XREF_ID
              AND x.PRODUCT_ID = IN_PRODUCT_ID
              AND x.APP_ID = IN_APP_ID
            ORDER BY x.PRODUCT_XREF_ID;
    END IF;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('INST', 'SP_GET_PRODUCT_XREF', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_PRODUCT_XREF] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
