-- Insert a new product, or version an existing one (soft-versioned).
--
-- IN_PRODUCT_ID NULL => new instrument: the SP assigns the next PRODUCT_ID
--                       (MAX+1 globally), and the VID resolves to 1.
-- IN_PRODUCT_ID set  => amend: flip the current row to 'N', insert VID+1.
--
-- Allocating the id is here because it is the one part the caller cannot do:
-- application code is barred from raw SELECT on application tables, so "what is
-- the next PRODUCT_ID" is a question only the procedure can answer -- the same
-- reason SP_INS_API_CREDENTIAL allocates its own. MAX+1 races under concurrent
-- inserts, but the composite primary key rejects the loser rather than merging
-- two instruments, and this is an admin action measured in rows per month.
--
-- Input validation is deliberately absent. NOT NULL on the columns and
-- UQ_PRODUCT_CUSIP_CURRENT already reject bad input, and the handler below
-- reports whatever SQLSTATE they raise; restating those rules in plpgsql would
-- be a second copy to keep in step with the DDL.
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
    OUT OUT_SQLERRMC      TEXT,
    OUT OUT_PRODUCT_ID    INTEGER,
    OUT OUT_PRODUCT_VID   INTEGER
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE    := '00000';
    OUT_SQLMSG      := '0';
    OUT_SQLERRMC    := 'Stored Procedure completed successfully';
    OUT_PRODUCT_ID  := IN_PRODUCT_ID;
    OUT_PRODUCT_VID := NULL;

    V_OTHER_TEXT := 'IN_PRODUCT_ID=' || COALESCE(IN_PRODUCT_ID::TEXT, '')
                 || ', IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '')
                 || ', IN_DISPLAY_NM=' || COALESCE(IN_DISPLAY_NM, '');

    -- Step 05: A new instrument arrives without an id — take the next one.
    OUT_SQLMSG := '05';
    IF OUT_PRODUCT_ID IS NULL THEN
        SELECT COALESCE(MAX(PRODUCT_ID), 0) + 1
          INTO OUT_PRODUCT_ID
          FROM INST.PRODUCT;
    END IF;

    -- Step 10: Resolve VID — get current max, or start at 1
    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(PRODUCT_VID), 0) + 1
      INTO V_VID
      FROM INST.PRODUCT
     WHERE PRODUCT_ID = OUT_PRODUCT_ID;
    OUT_PRODUCT_VID := V_VID;

    -- Step 20: Flip old current row(s) to 'N'
    OUT_SQLMSG := '20';
    UPDATE INST.PRODUCT
       SET IS_CURRENT_IND = 'N'
     WHERE PRODUCT_ID     = OUT_PRODUCT_ID
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
        OUT_PRODUCT_ID,
        V_VID,
        'Y',
        IN_INTERNAL_CUSIP,
        IN_DISPLAY_NM,
        IN_ASSET_TYPE_ID,
        IN_EXCHANGE,
        IN_CCY,
        IN_DESCRIPTION,
        IN_USER_ID,
        NOW() AT TIME ZONE 'UTC'
    );

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('INST', 'SP_INS_PRODUCT', V_LOG_START, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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
