-- Append one broker-confirmed fill row.
--
-- IN_TRANSACTION_ID supplied by caller (UUID).
-- Validation lives in Python (TradeRepo).
CREATE OR REPLACE PROCEDURE TRADE.SP_INS_TRANSACTION(
    IN  IN_TRANSACTION_ID    UUID,
    IN  IN_DEPLOYMENT_ID     UUID,
    IN  IN_APP_ID            INTEGER,
    IN  IN_ORDER_STATE_ID    INTEGER,
    IN  IN_TRANS_STATE_ID    INTEGER,
    IN  IN_INTERNAL_CUSIP    TEXT,
    IN  IN_VENDOR_SYMBOL     TEXT,
    IN  IN_BUY_SELL_CD       TEXT,
    IN  IN_TRANS_CCY_CD      TEXT,
    IN  IN_QUANTITY          NUMERIC,
    IN  IN_PRICE             NUMERIC,
    IN  IN_NOTIONAL_AMT      NUMERIC,
    IN  IN_FEE_AMT           NUMERIC,
    IN  IN_VENDOR_ORDER_ID   TEXT,
    IN  IN_USER_ID           TEXT,
    OUT OUT_SQLSTATE         TEXT,
    OUT OUT_SQLMSG           TEXT,
    OUT OUT_SQLERRMC         TEXT
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

    V_OTHER_TEXT := 'IN_TRANSACTION_ID=' || COALESCE(IN_TRANSACTION_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '');

    OUT_SQLMSG := '10';
    INSERT INTO TRADE.TRANSACTION (
        TRANSACTION_ID,
        DEPLOYMENT_ID,
        APP_ID,
        ORDER_STATE_ID,
        TRANS_STATE_ID,
        INTERNAL_CUSIP,
        VENDOR_SYMBOL,
        BUY_SELL_CD,
        TRANS_CCY_CD,
        QUANTITY,
        PRICE,
        NOTIONAL_AMT,
        FEE_AMT,
        VENDOR_ORDER_ID,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_TRANSACTION_ID,
        IN_DEPLOYMENT_ID,
        IN_APP_ID,
        IN_ORDER_STATE_ID,
        IN_TRANS_STATE_ID,
        IN_INTERNAL_CUSIP,
        IN_VENDOR_SYMBOL,
        IN_BUY_SELL_CD,
        IN_TRANS_CCY_CD,
        IN_QUANTITY,
        IN_PRICE,
        IN_NOTIONAL_AMT,
        IN_FEE_AMT,
        IN_VENDOR_ORDER_ID,
        IN_USER_ID,
        NOW() AT TIME ZONE 'UTC'
    );

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_INS_TRANSACTION', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_TRANSACTION] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_INS_TRANSACTION(
        UUID, UUID, INTEGER, INTEGER, INTEGER, TEXT, TEXT, TEXT, TEXT,
        NUMERIC, NUMERIC, NUMERIC, NUMERIC, TEXT, TEXT,
        OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
