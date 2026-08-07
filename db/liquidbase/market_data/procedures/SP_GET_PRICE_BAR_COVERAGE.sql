-- Stored bar bounds for catch-up and freshness — two edge probes, no partition scan.
--
-- Used after host down / crash: compare MIN/MAX to required window, fetch gaps, insert.
-- Edge probes on IX_PRICE_BAR_LATEST:
--   MIN: ORDER BY BAR_TIMESTAMP ASC LIMIT 1
--   MAX: ORDER BY BAR_TIMESTAMP DESC LIMIT 1
-- Gap row count: derive in app from MIN/MAX + interval; no COUNT(*) scan.
--
-- Scoped to one SOURCE_APP_ID. Unscoped, a venue that had already stored the
-- newest bar would make every other venue look fresh, so the second venue would
-- skip its fetch and price its signal off the first venue's prints.
CREATE OR REPLACE PROCEDURE MARKET_DATA.SP_GET_PRICE_BAR_COVERAGE(
    IN  IN_INTERNAL_CUSIP   TEXT,
    IN  IN_TM_INTERVAL_ID  INTEGER,
    IN  IN_SOURCE_APP_ID    INTEGER,
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
                 || ', IN_SOURCE_APP_ID=' || COALESCE(IN_SOURCE_APP_ID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_price_bar_coverage_cursor';

    OPEN OUT_RESULT FOR
        SELECT (
                   SELECT p.BAR_TIMESTAMP
                     FROM MARKET_DATA.PRICE_BAR p
                    WHERE p.INTERNAL_CUSIP = IN_INTERNAL_CUSIP
                      AND p.TM_INTERVAL_ID = IN_TM_INTERVAL_ID
                      AND p.SOURCE_APP_ID  = IN_SOURCE_APP_ID
                    ORDER BY p.BAR_TIMESTAMP ASC
                    LIMIT 1
               ) AS MIN_BAR_TIMESTAMP,
               (
                   SELECT p.BAR_TIMESTAMP
                     FROM MARKET_DATA.PRICE_BAR p
                    WHERE p.INTERNAL_CUSIP = IN_INTERNAL_CUSIP
                      AND p.TM_INTERVAL_ID = IN_TM_INTERVAL_ID
                      AND p.SOURCE_APP_ID  = IN_SOURCE_APP_ID
                    ORDER BY p.BAR_TIMESTAMP DESC
                    LIMIT 1
               ) AS MAX_BAR_TIMESTAMP;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'MARKET_DATA', 'SP_GET_PRICE_BAR_COVERAGE', V_START_TS, NULL, V_OTHER_TEXT,
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

            RAISE WARNING '[SP_GET_PRICE_BAR_COVERAGE] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

-- The pre-source signature would linger as an overload and keep reporting one
-- venue's bars as another's freshness.
DROP PROCEDURE IF EXISTS MARKET_DATA.SP_GET_PRICE_BAR_COVERAGE(
    TEXT, INTEGER,
    OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE MARKET_DATA.SP_GET_PRICE_BAR_COVERAGE(
        TEXT, INTEGER, INTEGER,
        OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
