-- Range read of normalized bars for live signal computation.
--
-- Scoped to one SOURCE_APP_ID: venues sharing an INTERNAL_CUSIP quote different
-- prices, so an unscoped read would hand the caller a blend of order books.
CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_GET_PRICE_BAR(
    IN  IN_INTERNAL_CUSIP   TEXT,
    IN  IN_TM_INTERVAL_ID  INTEGER,
    IN  IN_SOURCE_APP_ID    INTEGER,
    IN  IN_RANGE_START_TS   TIMESTAMPTZ,
    IN  IN_RANGE_END_TS     TIMESTAMPTZ,
    OUT OUT_RESULT          REFCURSOR,
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
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '')
                 || ', IN_TM_INTERVAL_ID=' || COALESCE(IN_TM_INTERVAL_ID::TEXT, '')
                 || ', IN_SOURCE_APP_ID=' || COALESCE(IN_SOURCE_APP_ID::TEXT, '')
                 || ', IN_RANGE_START_TS=' || COALESCE(IN_RANGE_START_TS::TEXT, '')
                 || ', IN_RANGE_END_TS=' || COALESCE(IN_RANGE_END_TS::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_price_bar_cursor';

    OPEN OUT_RESULT FOR
        SELECT BAR_TIMESTAMP,
               OPEN_PX,
               HIGH_PX,
               LOW_PX,
               CLOSE_PX,
               VOLUME,
               SOURCE_APP_ID
          FROM MARKET_DATA.PRICE_BAR
         WHERE INTERNAL_CUSIP = IN_INTERNAL_CUSIP
           AND TM_INTERVAL_ID = IN_TM_INTERVAL_ID
           AND SOURCE_APP_ID  = IN_SOURCE_APP_ID
           AND BAR_TIMESTAMP >= IN_RANGE_START_TS
           AND BAR_TIMESTAMP <= IN_RANGE_END_TS
         ORDER BY BAR_TIMESTAMP ASC;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_GET_PRICE_BAR', V_START_TS, NULL, V_OTHER_TEXT,
        NULL, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_PRICE_BAR] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

-- The pre-source signature would linger as an overload and keep serving blended
-- reads to any caller that still matches it.
DROP PROCEDURE IF EXISTS MARKET_DATA.SP_GET_PRICE_BAR(
    TEXT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ,
    OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_GET_PRICE_BAR(
        TEXT, INTEGER, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ,
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
