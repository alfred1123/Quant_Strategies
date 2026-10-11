-- Take a product off the current list without deleting its history.
--
-- Flips the current INST.PRODUCT row to IS_CURRENT_IND = 'N' and closes
-- every open INST.PRODUCT_XREF for that product. No successor row is
-- inserted, so SP_GET_PRODUCT stops returning it. A later insert of the
-- same cusip is a new PRODUCT_ID: the partial unique index only covers
-- current rows.
--
-- A cusip that is already not current is a no-op.
CREATE OR REPLACE PROCEDURE INST.SP_UPD_PRODUCT_IS_CURRENT(
    IN  IN_INTERNAL_CUSIP  TEXT,
    IN  IN_USER_ID         TEXT,
    OUT OUT_SQLSTATE       TEXT,
    OUT OUT_SQLMSG         TEXT,
    OUT OUT_SQLERRMC       TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_PRODUCT_ID INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '');

    OUT_SQLMSG := '10';
    SELECT PRODUCT_ID
      INTO V_PRODUCT_ID
      FROM INST.PRODUCT
     WHERE INTERNAL_CUSIP = IN_INTERNAL_CUSIP
       AND IS_CURRENT_IND = 'Y';

    IF V_PRODUCT_ID IS NULL THEN
        OUT_SQLERRMC := 'no current product — skipped';
        RETURN;
    END IF;

    OUT_SQLMSG := '20';
    UPDATE INST.PRODUCT_XREF
       SET TRANSACT_TO_TS = V_START_TS
     WHERE PRODUCT_ID     = V_PRODUCT_ID
       AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    OUT_SQLMSG := '30';
    UPDATE INST.PRODUCT
       SET IS_CURRENT_IND = 'N'
     WHERE PRODUCT_ID     = V_PRODUCT_ID
       AND IS_CURRENT_IND = 'Y';

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'INST', 'SP_UPD_PRODUCT_IS_CURRENT', V_LOG_START, NULL, V_OTHER_TEXT,
        IN_USER_ID, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_UPD_PRODUCT_IS_CURRENT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
