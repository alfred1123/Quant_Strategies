-- Read BT.PROMOTION decision-log rows (newest first).
--
-- IN_STRATEGY_ID  optional — when supplied, scopes to one strategy's
--                  promotion history. When NULL, returns the global log.
-- IN_LIMIT        optional — row cap (defaults to 200 when NULL).
--
-- STRATEGY_NM, live IS_BEST_IND, and LOGICAL_DELETE_IND are resolved via a
-- LEFT JOIN on the frozen BT.STRATEGY snapshot (STRATEGY_ID + STRATEGY_VID).
-- The
-- candidate's shredded performance metrics are pulled from the latest
-- BT.RESULT row for the decision's QUEUE_ID so the Promotion tab can
-- rank VIDs and reconstruct the soft-metric comparison without N+1
-- round-trips. GATE_RESULTS carries the point-in-time {name, passed,
-- value, threshold} hard-gate snapshot.
CREATE OR REPLACE PROCEDURE BT.SP_GET_PROMOTION(
    IN  IN_STRATEGY_ID   UUID,
    IN  IN_LIMIT         INTEGER,
    OUT OUT_RESULT       REFCURSOR,
    OUT OUT_SQLSTATE     TEXT,
    OUT OUT_SQLMSG       TEXT,
    OUT OUT_SQLERRMC     TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_LIMIT      INTEGER := COALESCE(IN_LIMIT, 200);
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_LIMIT='     || COALESCE(IN_LIMIT::TEXT, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_promotion_cursor';

    OPEN OUT_RESULT FOR
        SELECT P.PROMOTION_ID,
               P.QUEUE_ID,
               P.STRATEGY_ID,
               P.STRATEGY_VID,
               S.STRATEGY_NM,
               S.IS_BEST_IND,
               S.LOGICAL_DELETE_IND,
               P.OUTCOME,
               P.COMPARED_VID,
               P.GATE_RESULTS,
               R.SHARPE_RATIO,
               R.CALMAR_RATIO,
               R.MAX_DRAWDOWN,
               R.TOTAL_RETURN,
               R.ANNUALIZED_RETURN,
               P.USER_ID,
               P.CREATED_AT
          FROM BT.PROMOTION P
          LEFT JOIN BT.STRATEGY S
                 ON S.STRATEGY_ID  = P.STRATEGY_ID
                AND S.STRATEGY_VID = P.STRATEGY_VID
          LEFT JOIN LATERAL (
                 SELECT SHARPE_RATIO, CALMAR_RATIO, MAX_DRAWDOWN,
                        TOTAL_RETURN, ANNUALIZED_RETURN
                   FROM BT.RESULT
                  WHERE QUEUE_ID = P.QUEUE_ID
                  ORDER BY CREATED_AT DESC
                  LIMIT 1
               ) R ON TRUE
         WHERE IN_STRATEGY_ID IS NULL
            OR P.STRATEGY_ID = IN_STRATEGY_ID
         ORDER BY P.CREATED_AT DESC
         LIMIT V_LIMIT;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_PROMOTION', V_LOG_START, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_PROMOTION] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
