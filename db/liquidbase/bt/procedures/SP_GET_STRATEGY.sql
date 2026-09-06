-- Read BT.STRATEGY rows.
--
-- IN_STRATEGY_ID   required — scope to one logical strategy.
-- IN_STRATEGY_VID  optional — when supplied, returns that exact frozen
--                   version. When NULL, behaviour depends on IN_IS_BEST_IND.
-- IN_IS_BEST_IND   optional — when 'Y' (and VID is NULL), returns the
--                   IS_BEST_IND='Y' row. When NULL (and VID is NULL),
--                   returns the active row (TRANSACT_TO_TS = 9999-12-31).
--
-- Cursor columns: STRATEGY_ID, STRATEGY_VID, STRATEGY_NM, CONFIG_JSON,
-- USER_ID, CREATED_AT, TRANSACT_FROM_TS, TRANSACT_TO_TS, IS_BEST_IND,
-- LOGICAL_DELETE_IND.
CREATE OR REPLACE PROCEDURE BT.SP_GET_STRATEGY(
    IN  IN_STRATEGY_ID   UUID,
    IN  IN_STRATEGY_VID  INTEGER,
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
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_STRATEGY_ID='    || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '')
                 || ', IN_IS_BEST_IND='  || COALESCE(IN_IS_BEST_IND, '');

    -- Step 10: Validate required input.
    OUT_SQLMSG := '10';
    IF IN_STRATEGY_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_STRATEGY_ID is required';
        RETURN;
    END IF;

    -- Step 20: Open cursor.
    OUT_SQLMSG := '20';
    OUT_RESULT := 'sp_get_strategy_cursor';

    IF IN_STRATEGY_VID IS NOT NULL THEN
        -- Mode 1: exact VID (frozen snapshot).
        OPEN OUT_RESULT FOR
            SELECT STRATEGY_ID,
                   STRATEGY_VID,
                   STRATEGY_NM,
                   CONFIG_JSON,
                   USER_ID,
                   CREATED_AT,
                   TRANSACT_FROM_TS,
                   TRANSACT_TO_TS,
                   IS_BEST_IND,
                   LOGICAL_DELETE_IND
              FROM BT.STRATEGY
             WHERE STRATEGY_ID  = IN_STRATEGY_ID
               AND STRATEGY_VID = IN_STRATEGY_VID;
    ELSIF IN_IS_BEST_IND = 'Y' THEN
        -- Mode 2: best-performing VID.
        OPEN OUT_RESULT FOR
            SELECT STRATEGY_ID,
                   STRATEGY_VID,
                   STRATEGY_NM,
                   CONFIG_JSON,
                   USER_ID,
                   CREATED_AT,
                   TRANSACT_FROM_TS,
                   TRANSACT_TO_TS,
                   IS_BEST_IND,
                   LOGICAL_DELETE_IND
              FROM BT.STRATEGY
             WHERE STRATEGY_ID = IN_STRATEGY_ID
               AND IS_BEST_IND = 'Y';
    ELSE
        -- Mode 3: active/latest (TRANSACT_TO_TS = 9999-12-31).
        OPEN OUT_RESULT FOR
            SELECT STRATEGY_ID,
                   STRATEGY_VID,
                   STRATEGY_NM,
                   CONFIG_JSON,
                   USER_ID,
                   CREATED_AT,
                   TRANSACT_FROM_TS,
                   TRANSACT_TO_TS,
                   IS_BEST_IND,
                   LOGICAL_DELETE_IND
              FROM BT.STRATEGY
             WHERE STRATEGY_ID  = IN_STRATEGY_ID
               AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';
    END IF;

    -- Step 30: Audit log.
    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_STRATEGY', V_LOG_START, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_STRATEGY] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
