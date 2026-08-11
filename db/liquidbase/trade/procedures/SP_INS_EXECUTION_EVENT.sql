-- Append one execution diary row (order submit, error, signal acted on).
--
-- IN_EXECUTION_EVENT_ID supplied by caller (UUID).
-- IN_TRANSACT_AT = when the apply tick occurred (diary only — not scheduler state).
-- Scheduler due-ness lives in TRADE.DEPLOYMENT_SCHEDULE_STATUS.
-- Validation lives in Python (TradeRepo).
CREATE OR REPLACE PROCEDURE TRADE.SP_INS_EXECUTION_EVENT(
    IN  IN_EXECUTION_EVENT_ID  UUID,
    IN  IN_DEPLOYMENT_ID       UUID,
    IN  IN_DEPLOYMENT_VID      INTEGER,
    IN  IN_SIGNAL_VALUE        NUMERIC,
    IN  IN_BUY_SELL_CD         TEXT,
    IN  IN_QUANTITY            NUMERIC,
    IN  IN_VENDOR_ORDER_ID     TEXT,
    IN  IN_IS_SUCCESS_IND      CHAR(1),
    IN  IN_USER_ID             TEXT,
    IN  IN_TRANSACT_AT         TIMESTAMPTZ,
    OUT OUT_SQLSTATE           TEXT,
    OUT OUT_SQLMSG             TEXT,
    OUT OUT_SQLERRMC           TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_EXECUTION_EVENT_ID=' || COALESCE(IN_EXECUTION_EVENT_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_VID=' || COALESCE(IN_DEPLOYMENT_VID::TEXT, '');

    OUT_SQLMSG := '20';
    INSERT INTO TRADE.EXECUTION_EVENT (
        EXECUTION_EVENT_ID,
        DEPLOYMENT_ID,
        DEPLOYMENT_VID,
        SIGNAL_VALUE,
        BUY_SELL_CD,
        QUANTITY,
        VENDOR_ORDER_ID,
        IS_SUCCESS_IND,
        TRANSACT_AT,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_EXECUTION_EVENT_ID,
        IN_DEPLOYMENT_ID,
        IN_DEPLOYMENT_VID,
        IN_SIGNAL_VALUE,
        IN_BUY_SELL_CD,
        IN_QUANTITY,
        IN_VENDOR_ORDER_ID,
        IN_IS_SUCCESS_IND,
        IN_TRANSACT_AT,
        IN_USER_ID,
        NOW()
    );

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_INS_EXECUTION_EVENT', V_LOG_START, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_EXECUTION_EVENT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE TRADE.SP_INS_EXECUTION_EVENT(
        UUID, UUID, INTEGER, NUMERIC, TEXT, NUMERIC, TEXT, CHAR(1), TEXT, TIMESTAMPTZ,
        OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
