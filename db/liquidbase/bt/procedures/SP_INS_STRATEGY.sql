-- Insert / version a backtest strategy definition.
--
-- If IN_STRATEGY_ID is new => inserts STRATEGY_VID=1 as active
-- (TRANSACT_TO_TS = 9999-12-31).
-- If IN_STRATEGY_ID already exists => closes the prior active row
-- (TRANSACT_TO_TS = now) and inserts the next VID as the new active row.
--
-- Returns OUT_STRATEGY_VID so the caller can reference this exact version
-- when enqueueing a job (SP_INS_QUEUE expects STRATEGY_ID + STRATEGY_VID).
CREATE OR REPLACE PROCEDURE BT.SP_INS_STRATEGY(
    IN  IN_STRATEGY_ID    UUID,
    IN  IN_STRATEGY_NM    TEXT,
    IN  IN_CONFIG_JSON    JSONB,
    IN  IN_USER_ID        TEXT,
    OUT OUT_SQLSTATE      TEXT,
    OUT OUT_SQLMSG        TEXT,
    OUT OUT_SQLERRMC      TEXT,
    OUT OUT_STRATEGY_VID  INTEGER
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_VID        INTEGER;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE     := '00000';
    OUT_SQLMSG       := '0';
    OUT_SQLERRMC     := 'Stored Procedure completed successfully';
    OUT_STRATEGY_VID := NULL;

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_NM=' || COALESCE(IN_STRATEGY_NM, '');

    -- Step 10: Resolve next VID.
    OUT_SQLMSG := '10';
    SELECT COALESCE(MAX(STRATEGY_VID), 0) + 1
      INTO V_VID
      FROM BT.STRATEGY
     WHERE STRATEGY_ID = IN_STRATEGY_ID;

    -- Step 20: Close prior active row — set TRANSACT_TO_TS to now.
    OUT_SQLMSG := '20';
    UPDATE BT.STRATEGY
       SET TRANSACT_TO_TS = V_START_TS
     WHERE STRATEGY_ID    = IN_STRATEGY_ID
       AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

    -- Step 30: Insert new version as active (TRANSACT_TO_TS = 9999-12-31).
    -- VID 1 is presumed best (no baseline); VID 2+ starts as not-best until promoted.
    OUT_SQLMSG := '30';
    INSERT INTO BT.STRATEGY (
        STRATEGY_ID,
        STRATEGY_VID,
        STRATEGY_NM,
        CONFIG_JSON,
        USER_ID,
        CREATED_AT,
        TRANSACT_FROM_TS,
        TRANSACT_TO_TS,
        IS_BEST_IND
    ) VALUES (
        IN_STRATEGY_ID,
        V_VID,
        IN_STRATEGY_NM,
        IN_CONFIG_JSON,
        IN_USER_ID,
        V_START_TS,
        V_START_TS,
        TIMESTAMPTZ '9999-12-31 00:00:00+00',
        CASE WHEN V_VID = 1 THEN 'Y' ELSE 'N' END
    );

    OUT_STRATEGY_VID := V_VID;

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_INS_STRATEGY', V_START_TS, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_INS_STRATEGY] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
