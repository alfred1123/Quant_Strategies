-- BT.SP_GET_RESULT — one result row.
--
-- Two lookups, one procedure. A job view passes IN_QUEUE_ID and reads what
-- that submission produced. The live path passes IN_STRATEGY_ID and
-- IN_STRATEGY_VID and reads the current row of that version. STRATEGY_ID and
-- STRATEGY_VID are denormalized onto BT.RESULT, with
-- IX_RESULT_STRATEGY_CURRENT, so the live path does not walk BT.QUEUE.
--
-- Each filter is appended only when its input is present. A predicate of the
-- form "IN_X IS NULL OR col = IN_X" is not used: that OR hides which index
-- the call wants. Dynamic SQL is the same shape as SP_GET_QUEUE.
--
-- A queue lookup returns the newest row for that QUEUE_ID (CREATED_AT DESC).
-- A strategy lookup returns the current row (IS_CURRENT_IND = 'Y',
-- RESULT_VID DESC). Re-backtesting a version bumps RESULT_VID and flips the
-- prior row, so the live path follows the latest backtest.
CREATE OR REPLACE PROCEDURE BT.SP_GET_RESULT(
    IN  IN_QUEUE_ID         UUID,
    IN  IN_STRATEGY_ID      UUID,
    IN  IN_STRATEGY_VID     INTEGER,
    OUT OUT_RESULT          REFCURSOR,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_custom_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_SQL        TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_QUEUE_ID=' || COALESCE(IN_QUEUE_ID::TEXT, '')
                 || ', IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '');

    IF IN_QUEUE_ID IS NULL AND IN_STRATEGY_ID IS NULL THEN
        RAISE EXCEPTION 'SP_GET_RESULT needs IN_QUEUE_ID or IN_STRATEGY_ID';
    END IF;

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_result_cursor';

    V_SQL := 'SELECT RESULT_ID,'
          || '       QUEUE_ID,'
          || '       STRATEGY_ID,'
          || '       STRATEGY_VID,'
          || '       RESULT_VID,'
          || '       IS_CURRENT_IND,'
          || '       PAYLOAD_JSON,'
          || '       TOTAL_RETURN,'
          || '       ANNUALIZED_RETURN,'
          || '       SHARPE_RATIO,'
          || '       MAX_DRAWDOWN,'
          || '       CALMAR_RATIO,'
          || '       CREATED_AT'
          || '  FROM BT.RESULT'
          || ' WHERE 1=1';

    IF IN_QUEUE_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND QUEUE_ID = %L::uuid', IN_QUEUE_ID);
    END IF;

    IF IN_STRATEGY_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND STRATEGY_ID = %L::uuid', IN_STRATEGY_ID);
    END IF;

    IF IN_STRATEGY_VID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND STRATEGY_VID = %s', IN_STRATEGY_VID);
    END IF;

    IF IN_QUEUE_ID IS NULL THEN
        V_SQL := V_SQL || ' AND IS_CURRENT_IND = ''Y'''
                      || ' ORDER BY RESULT_VID DESC';
    ELSE
        V_SQL := V_SQL || ' ORDER BY CREATED_AT DESC';
    END IF;

    V_SQL := V_SQL || ' LIMIT 1';

    OPEN OUT_RESULT FOR EXECUTE V_SQL;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_RESULT', V_LOG_START, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_RESULT] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
