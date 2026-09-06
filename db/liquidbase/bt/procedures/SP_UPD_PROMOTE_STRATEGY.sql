-- Promote a specific VID to IS_BEST_IND = 'Y' within a STRATEGY_ID.
--
-- Enforces the exactly-one-best invariant: demotes the current best
-- then promotes the target VID.  No-op if the target is already best.
--
-- When IN_STRATEGY_VID IS NULL → demote-only: sets IS_BEST_IND = 'N'
-- on the current best without promoting a replacement (strategy has
-- no qualified best after hard-gate failure).
CREATE OR REPLACE PROCEDURE BT.SP_UPD_PROMOTE_STRATEGY(
    IN  IN_STRATEGY_ID   UUID,
    IN  IN_STRATEGY_VID  INTEGER,
    IN  IN_USER_ID       TEXT,
    OUT OUT_SQLSTATE      TEXT,
    OUT OUT_SQLMSG        TEXT,
    OUT OUT_SQLERRMC      TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_EXISTS     BOOLEAN;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '');

    -- Step 10: Validate inputs.
    OUT_SQLMSG := '10';
    IF IN_STRATEGY_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_STRATEGY_ID is required';
        RETURN;
    END IF;

    -- Step 15: Demote-only mode (IN_STRATEGY_VID IS NULL).
    OUT_SQLMSG := '15';
    IF IN_STRATEGY_VID IS NULL THEN
        UPDATE BT.STRATEGY
           SET IS_BEST_IND = 'N',
               UPDATED_AT  = NOW() AT TIME ZONE 'UTC'
         WHERE STRATEGY_ID = IN_STRATEGY_ID
           AND IS_BEST_IND = 'Y';

        -- Fallback: VID 1 is always the default best when none qualifies.
        UPDATE BT.STRATEGY
           SET IS_BEST_IND = 'Y',
               UPDATED_AT  = NOW() AT TIME ZONE 'UTC'
         WHERE STRATEGY_ID  = IN_STRATEGY_ID
           AND STRATEGY_VID = 1
           AND NOT EXISTS (
                   SELECT 1
                     FROM BT.STRATEGY
                    WHERE STRATEGY_ID = IN_STRATEGY_ID
                      AND IS_BEST_IND = 'Y'
               );

        OUT_SQLERRMC := 'Demoted current best — VID 1 restored as default best when needed';

        OUT_SQLMSG := '16';
        CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_UPD_PROMOTE_STRATEGY', V_LOG_START, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);
        RETURN;
    END IF;

    -- Step 20: Verify target VID exists.
    OUT_SQLMSG := '20';
    SELECT EXISTS(
        SELECT 1 FROM BT.STRATEGY
         WHERE STRATEGY_ID  = IN_STRATEGY_ID
           AND STRATEGY_VID = IN_STRATEGY_VID
    ) INTO V_EXISTS;

    IF NOT V_EXISTS THEN
        OUT_SQLSTATE := '02000';
        OUT_SQLERRMC := 'Target VID does not exist for this STRATEGY_ID';
        RETURN;
    END IF;

    -- Step 30: Check if already best — no-op.
    OUT_SQLMSG := '30';
    SELECT EXISTS(
        SELECT 1 FROM BT.STRATEGY
         WHERE STRATEGY_ID  = IN_STRATEGY_ID
           AND STRATEGY_VID = IN_STRATEGY_VID
           AND IS_BEST_IND  = 'Y'
    ) INTO V_EXISTS;

    IF V_EXISTS THEN
        OUT_SQLERRMC := 'Target VID is already the best — no change';
        RETURN;
    END IF;

    -- Step 40: Demote current best.
    OUT_SQLMSG := '40';
    UPDATE BT.STRATEGY
       SET IS_BEST_IND = 'N',
           UPDATED_AT  = NOW() AT TIME ZONE 'UTC'
     WHERE STRATEGY_ID = IN_STRATEGY_ID
       AND IS_BEST_IND = 'Y';

    -- Step 50: Promote target VID.
    OUT_SQLMSG := '50';
    UPDATE BT.STRATEGY
       SET IS_BEST_IND = 'Y',
           UPDATED_AT  = NOW() AT TIME ZONE 'UTC'
     WHERE STRATEGY_ID  = IN_STRATEGY_ID
       AND STRATEGY_VID = IN_STRATEGY_VID;

    -- Step 60: Audit log.
    OUT_SQLMSG := '60';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_UPD_PROMOTE_STRATEGY', V_LOG_START, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_UPD_PROMOTE_STRATEGY] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
