-- Append one intent: the target position a deployment asked for on one apply.
--
-- Written before the order. IN_TARGET_QTY is signed SIGNAL_VALUE × QTY.
-- IN_TRANSACT_AT is the apply's tick time, shared with that pass's
-- EXECUTION_EVENT rows. IN_BAR_TIMESTAMP is the bar the signal was computed on.
-- Caller supplies IN_INTENT_ID. Validation lives in Python (TradeRepo).
CREATE OR REPLACE PROCEDURE TRADE.SP_INS_INTENT(
    IN  IN_INTENT_ID        UUID,
    IN  IN_DEPLOYMENT_ID    UUID,
    IN  IN_DEPLOYMENT_VID   INTEGER,
    IN  IN_TM_INTERVAL_ID   INTEGER,
    IN  IN_BAR_TIMESTAMP    TIMESTAMPTZ,
    IN  IN_BAR_SOURCE       TEXT,
    IN  IN_SIGNAL_VALUE     NUMERIC,
    IN  IN_TARGET_QTY       NUMERIC,
    IN  IN_TRANSACT_AT      TIMESTAMPTZ,
    IN  IN_USER_ID          TEXT,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
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

    V_OTHER_TEXT := 'IN_INTENT_ID=' || COALESCE(IN_INTENT_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_ID=' || COALESCE(IN_DEPLOYMENT_ID::TEXT, '')
                 || ', IN_DEPLOYMENT_VID=' || COALESCE(IN_DEPLOYMENT_VID::TEXT, '');

    OUT_SQLMSG := '20';
    INSERT INTO TRADE.INTENT (
        INTENT_ID,
        DEPLOYMENT_ID,
        DEPLOYMENT_VID,
        TM_INTERVAL_ID,
        BAR_TIMESTAMP,
        BAR_SOURCE,
        SIGNAL_VALUE,
        TARGET_QTY,
        TRANSACT_AT,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_INTENT_ID,
        IN_DEPLOYMENT_ID,
        IN_DEPLOYMENT_VID,
        IN_TM_INTERVAL_ID,
        IN_BAR_TIMESTAMP,
        IN_BAR_SOURCE,
        IN_SIGNAL_VALUE,
        IN_TARGET_QTY,
        IN_TRANSACT_AT,
        IN_USER_ID,
        NOW()
    );

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'TRADE', 'SP_INS_INTENT', V_LOG_START, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_INTENT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
