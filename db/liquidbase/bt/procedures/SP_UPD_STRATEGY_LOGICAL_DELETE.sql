-- Flip LOGICAL_DELETE_IND on BT.STRATEGY (in-place, not a new VID).
--
-- Orthogonal to IS_BEST_IND (quality) and TRANSACT_TO_TS (temporal current).
-- 'Y' retires the row from the Trade picker, Recommended banner, and new
-- deploys. Promotion history stays so the decision can still be inspected.
--
-- IN_STRATEGY_VID NULL → every VID of IN_STRATEGY_ID (retire/restore the
-- lineage). A named VID flips that row only.
CREATE OR REPLACE PROCEDURE BT.SP_UPD_STRATEGY_LOGICAL_DELETE(
    IN  IN_STRATEGY_ID         UUID,
    IN  IN_STRATEGY_VID        INTEGER,
    IN  IN_LOGICAL_DELETE_IND  CHAR(1),
    IN  IN_USER_ID             TEXT,
    OUT OUT_SQLSTATE           TEXT,
    OUT OUT_SQLMSG             TEXT,
    OUT OUT_SQLERRMC           TEXT
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
                 || ', IN_STRATEGY_VID=' || COALESCE(IN_STRATEGY_VID::TEXT, '')
                 || ', IN_LOGICAL_DELETE_IND=' || COALESCE(IN_LOGICAL_DELETE_IND, '');

    OUT_SQLMSG := '10';
    IF IN_STRATEGY_ID IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_STRATEGY_ID is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '15';
    IF IN_LOGICAL_DELETE_IND IS NULL THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_LOGICAL_DELETE_IND is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '20';
    IF IN_STRATEGY_VID IS NOT NULL THEN
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

        UPDATE BT.STRATEGY
           SET LOGICAL_DELETE_IND = IN_LOGICAL_DELETE_IND,
               UPDATED_AT         = NOW() AT TIME ZONE 'UTC'
         WHERE STRATEGY_ID  = IN_STRATEGY_ID
           AND STRATEGY_VID = IN_STRATEGY_VID;
    ELSE
        SELECT EXISTS(
            SELECT 1 FROM BT.STRATEGY
             WHERE STRATEGY_ID = IN_STRATEGY_ID
        ) INTO V_EXISTS;

        IF NOT V_EXISTS THEN
            OUT_SQLSTATE := '02000';
            OUT_SQLERRMC := 'STRATEGY_ID does not exist';
            RETURN;
        END IF;

        UPDATE BT.STRATEGY
           SET LOGICAL_DELETE_IND = IN_LOGICAL_DELETE_IND,
               UPDATED_AT         = NOW() AT TIME ZONE 'UTC'
         WHERE STRATEGY_ID = IN_STRATEGY_ID;
    END IF;

    OUT_SQLMSG := '30';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_UPD_STRATEGY_LOGICAL_DELETE', V_LOG_START, NULL, V_OTHER_TEXT, IN_USER_ID, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_UPD_STRATEGY_LOGICAL_DELETE] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE BT.SP_UPD_STRATEGY_LOGICAL_DELETE(
        IN UUID, IN INTEGER, IN CHAR, IN TEXT, OUT TEXT, OUT TEXT, OUT TEXT
    ) TO quant_app;
  END IF;
END $$;
