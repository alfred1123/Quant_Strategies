-- BT.SP_GET_RESULT_BY_STRATEGY — current result for one strategy version.
--
-- SP_GET_RESULT reaches a result through its QUEUE_ID, which ties the live
-- trading path to transient work-tracking data: purging BT.QUEUE left every
-- deployment unable to find its own optimized parameters, and a live dry-run
-- failed with "no optimization result found" while the payload sat in
-- BT.RESULT intact. STRATEGY_ID and STRATEGY_VID are denormalized onto
-- BT.RESULT for exactly this lookup, with IX_RESULT_STRATEGY_CURRENT to serve
-- it, so read them directly and let the queue be purged freely.
--
-- A separate procedure rather than extra parameters on SP_GET_RESULT: adding
-- IN parameters would overload it rather than replace it, leaving two
-- procedures behind and repeating the signature clash that broke an earlier
-- deploy.
--
-- IS_CURRENT_IND = 'Y' selects the newest RESULT_VID: re-backtesting a
-- strategy version bumps RESULT_VID and flips the prior row, so the live path
-- follows the most recent backtest without needing to know its version.
CREATE OR REPLACE PROCEDURE BT.SP_GET_RESULT_BY_STRATEGY(
    IN  IN_STRATEGY_ID      UUID,
    IN  IN_STRATEGY_VID     INTEGER,
    OUT OUT_RESULT          REFCURSOR,
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

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_result_by_strategy_cursor';

    OPEN OUT_RESULT FOR
        SELECT RESULT_ID,
               QUEUE_ID,
               STRATEGY_ID,
               STRATEGY_VID,
               RESULT_VID,
               IS_CURRENT_IND,
               PAYLOAD_JSON,
               TOTAL_RETURN,
               ANNUALIZED_RETURN,
               SHARPE_RATIO,
               MAX_DRAWDOWN,
               CALMAR_RATIO,
               CREATED_AT
          FROM BT.RESULT
         WHERE STRATEGY_ID = IN_STRATEGY_ID
           AND STRATEGY_VID = IN_STRATEGY_VID
           AND IS_CURRENT_IND = 'Y'
         ORDER BY RESULT_VID DESC
         LIMIT 1;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_RESULT_BY_STRATEGY', V_LOG_START, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_RESULT_BY_STRATEGY] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE BT.SP_GET_RESULT_BY_STRATEGY(
        IN UUID, IN INTEGER, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
