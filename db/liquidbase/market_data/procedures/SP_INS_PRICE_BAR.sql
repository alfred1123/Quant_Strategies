-- Insert one OHLCV bar — no sync row, no conflict handling.
--
-- Caller inserts only missing bars (one CALL per bar). Plain INSERT;
-- duplicate PK raises unique_violation. Batch backfill loops in the app.
CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_INS_PRICE_BAR(
    IN  IN_INTERNAL_CUSIP   TEXT,
    IN  IN_TM_INTERVAL_ID   INTEGER,
    IN  IN_SOURCE_APP_ID    INTEGER,
    IN  IN_BAR_TIMESTAMP    TIMESTAMPTZ,
    IN  IN_OPEN_PX          DECIMAL,
    IN  IN_HIGH_PX          DECIMAL,
    IN  IN_LOW_PX           DECIMAL,
    IN  IN_CLOSE_PX         DECIMAL,
    IN  IN_VOLUME           DECIMAL,
    IN  IN_USER_ID          TEXT,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_NOW        TIMESTAMPTZ := NOW();
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '')
                 || ', IN_TM_INTERVAL_ID=' || COALESCE(IN_TM_INTERVAL_ID::TEXT, '')
                 || ', IN_BAR_TIMESTAMP=' || COALESCE(IN_BAR_TIMESTAMP::TEXT, '')
                 || ', IN_SOURCE_APP_ID=' || COALESCE(IN_SOURCE_APP_ID::TEXT, '');

    OUT_SQLMSG := '10';
    INSERT INTO MARKET_DATA.PRICE_BAR (
        INTERNAL_CUSIP,
        TM_INTERVAL_ID,
        BAR_TIMESTAMP,
        OPEN_PX,
        HIGH_PX,
        LOW_PX,
        CLOSE_PX,
        VOLUME,
        SOURCE_APP_ID,
        USER_ID,
        CREATED_AT
    ) VALUES (
        IN_INTERNAL_CUSIP,
        IN_TM_INTERVAL_ID,
        IN_BAR_TIMESTAMP,
        IN_OPEN_PX,
        IN_HIGH_PX,
        IN_LOW_PX,
        IN_CLOSE_PX,
        IN_VOLUME,
        IN_SOURCE_APP_ID,
        IN_USER_ID,
        V_NOW
    );

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_INS_PRICE_BAR', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_INS_PRICE_BAR] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_INS_PRICE_BAR(
        TEXT, INTEGER, INTEGER, TIMESTAMPTZ,
        DECIMAL, DECIMAL, DECIMAL, DECIMAL, DECIMAL, TEXT,
        OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
