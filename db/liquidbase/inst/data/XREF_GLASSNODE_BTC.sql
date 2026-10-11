-- Glassnode xref for btcusdt.crypto.
--
-- VENDOR_SYMBOL is the Glassnode asset (decision #21): BTC, not BTCUSDT.
-- The daily fill walks current xrefs for this app. Add instrument cannot
-- write this row: that dialog lists exchange apps only.
--
-- Idempotent: a current (product, app) row is left alone. A missing product
-- or a missing Glassnode app fails the changeset instead of recording success.
DO $$
DECLARE
    V_PRODUCT_ID INTEGER;
    V_APP_ID     INTEGER;
    V_SQLSTATE   TEXT;
    V_SQLMSG     TEXT;
    V_SQLERRMC   TEXT;
    V_XREF_ID    INTEGER;
    V_XREF_VID   INTEGER;
BEGIN
    SELECT APP_ID
      INTO V_APP_ID
      FROM REFDATA.APP
     WHERE NAME = 'glassnode';
    IF V_APP_ID IS NULL THEN
        RAISE EXCEPTION 'REFDATA.APP has no glassnode row';
    END IF;

    SELECT PRODUCT_ID
      INTO V_PRODUCT_ID
      FROM INST.PRODUCT
     WHERE INTERNAL_CUSIP = 'btcusdt.crypto'
       AND IS_CURRENT_IND = 'Y';
    IF V_PRODUCT_ID IS NULL THEN
        RAISE EXCEPTION 'INST.PRODUCT has no current btcusdt.crypto row';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM INST.PRODUCT_XREF
         WHERE PRODUCT_ID = V_PRODUCT_ID
           AND APP_ID = V_APP_ID
           AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
    ) THEN
        RAISE NOTICE 'Glassnode xref for btcusdt.crypto already exists — skipped';
        RETURN;
    END IF;

    CALL INST.SP_INS_PRODUCT_XREF(
        NULL,
        V_PRODUCT_ID,
        V_APP_ID,
        'BTC',
        'liquibase',
        V_SQLSTATE,
        V_SQLMSG,
        V_SQLERRMC,
        V_XREF_ID,
        V_XREF_VID
    );

    IF V_SQLSTATE <> '00000' THEN
        RAISE EXCEPTION 'SP_INS_PRODUCT_XREF failed for btcusdt.crypto: % (%)',
            V_SQLERRMC, V_SQLSTATE;
    END IF;

    RAISE NOTICE 'Inserted Glassnode xref for btcusdt.crypto (xref_id=%)', V_XREF_ID;
END $$;
