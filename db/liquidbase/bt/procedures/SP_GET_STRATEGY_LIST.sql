-- List BT.STRATEGY rows for the Trade strategy picker (Phase 1.6).
--
-- IN_USER_ID      required — caller's identity; only that owner's rows are returned.
-- IN_LIMIT        optional — row cap (defaults to 200 when NULL).
-- IN_IS_BEST_IND  optional — pass 'Y' for best VID per strategy only; NULL for all VIDs.
--
-- Shredded metrics from the current BT.RESULT row (IS_CURRENT_IND = 'Y')
-- for the same (STRATEGY_ID, STRATEGY_VID).
CREATE OR REPLACE PROCEDURE BT.SP_GET_STRATEGY_LIST(
    IN  IN_USER_ID       TEXT,
    IN  IN_LIMIT         INTEGER,
    IN  IN_IS_BEST_IND   CHAR(1),
    OUT OUT_RESULT       REFCURSOR,
    OUT OUT_SQLSTATE     TEXT,
    OUT OUT_SQLMSG       TEXT,
    OUT OUT_SQLERRMC     TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LIMIT      INTEGER := COALESCE(IN_LIMIT, 200);
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_USER_ID=' || COALESCE(IN_USER_ID, '')
                 || ', IN_LIMIT='  || COALESCE(IN_LIMIT::TEXT, '')
                 || ', IN_IS_BEST_IND=' || COALESCE(IN_IS_BEST_IND, '');

    OUT_SQLMSG := '10';
    IF IN_USER_ID IS NULL OR TRIM(IN_USER_ID) = '' THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_USER_ID is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_strategy_list_cursor';

    OPEN OUT_RESULT FOR
        SELECT S.STRATEGY_ID,
               S.STRATEGY_VID,
               S.STRATEGY_NM,
               S.IS_BEST_IND,
               S.CREATED_AT,
               R.SHARPE_RATIO,
               R.CALMAR_RATIO,
               R.MAX_DRAWDOWN,
               R.TOTAL_RETURN,
               R.ANNUALIZED_RETURN
          FROM BT.STRATEGY S
          LEFT JOIN BT.RESULT R
            ON R.STRATEGY_ID     = S.STRATEGY_ID
           AND R.STRATEGY_VID    = S.STRATEGY_VID
           AND R.IS_CURRENT_IND  = 'Y'
         WHERE S.USER_ID = IN_USER_ID
           AND (IN_IS_BEST_IND IS DISTINCT FROM 'Y' OR S.IS_BEST_IND = 'Y')
         ORDER BY S.CREATED_AT DESC, S.STRATEGY_NM ASC, S.STRATEGY_VID DESC
         LIMIT V_LIMIT;

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'BT', 'SP_GET_STRATEGY_LIST', V_START_TS, NULL, V_OTHER_TEXT, NULL,
        V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_STRATEGY_LIST] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
