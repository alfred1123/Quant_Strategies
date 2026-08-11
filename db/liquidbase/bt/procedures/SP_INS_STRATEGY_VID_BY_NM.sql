-- Strategy VID-by-name insert (release 1.10.0).
-- Replaces pre-1.10 SP_INS_STRATEGY signature — see 1.10.0-strategy-vid-versioning.xml.
-- Canonical live definition; 1.6.0 runOnChange still pins procedures/SP_INS_STRATEGY.sql (frozen).
--
-- Resolves STRATEGY_ID from (IN_USER_ID, IN_STRATEGY_NM); bumps STRATEGY_VID.
-- Returns OUT_STRATEGY_ID + OUT_STRATEGY_VID for SP_INS_QUEUE.
CREATE OR REPLACE PROCEDURE BT.SP_INS_STRATEGY(
    IN  IN_STRATEGY_ID    UUID,
    IN  IN_STRATEGY_NM    TEXT,
    IN  IN_CONFIG_JSON    JSONB,
    IN  IN_USER_ID        TEXT,
    OUT OUT_SQLSTATE      TEXT,
    OUT OUT_SQLMSG        TEXT,
    OUT OUT_SQLERRMC      TEXT,
    OUT OUT_STRATEGY_ID   UUID,
    OUT OUT_STRATEGY_VID  INTEGER
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_START_TS    TIMESTAMPTZ := CURRENT_TIMESTAMP;
    -- V_START_TS is the transaction timestamp and stamps the version window;
    -- the log needs wall-clock, which CURRENT_TIMESTAMP does not advance.
    V_LOG_START   TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT  TEXT;
    V_STRATEGY_ID UUID;
    V_VID         INTEGER;
    V_LOG_STATE   TEXT;
    V_LOG_MSG     TEXT;
BEGIN
    OUT_SQLSTATE     := '00000';
    OUT_SQLMSG       := '0';
    OUT_SQLERRMC     := 'Stored Procedure completed successfully';
    OUT_STRATEGY_ID  := NULL;
    OUT_STRATEGY_VID := NULL;

    V_OTHER_TEXT := 'IN_STRATEGY_ID=' || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_STRATEGY_NM=' || COALESCE(IN_STRATEGY_NM, '')
                 || ', IN_USER_ID='     || COALESCE(IN_USER_ID, '');

    OUT_SQLMSG := '05';
    IF IN_STRATEGY_NM IS NULL OR BTRIM(IN_STRATEGY_NM) = '' THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_STRATEGY_NM is required';
        RETURN;
    END IF;
    IF IN_USER_ID IS NULL OR BTRIM(IN_USER_ID) = '' THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_USER_ID is required';
        RETURN;
    END IF;

    OUT_SQLMSG := '07';
    PERFORM pg_advisory_xact_lock(
        hashtextextended(IN_USER_ID || '|' || IN_STRATEGY_NM, 0)
    );

    OUT_SQLMSG := '10';
    SELECT STRATEGY_ID
      INTO V_STRATEGY_ID
      FROM BT.STRATEGY
     WHERE USER_ID     = IN_USER_ID
       AND STRATEGY_NM = IN_STRATEGY_NM
     ORDER BY STRATEGY_VID DESC
     LIMIT 1;

    IF V_STRATEGY_ID IS NULL THEN
        V_STRATEGY_ID := COALESCE(IN_STRATEGY_ID, gen_random_uuid());
    END IF;

    OUT_SQLMSG := '15';
    SELECT COALESCE(MAX(STRATEGY_VID), 0) + 1
      INTO V_VID
      FROM BT.STRATEGY
     WHERE STRATEGY_ID = V_STRATEGY_ID;

    OUT_SQLMSG := '20';
    UPDATE BT.STRATEGY
       SET TRANSACT_TO_TS = V_START_TS
     WHERE STRATEGY_ID    = V_STRATEGY_ID
       AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

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
        V_STRATEGY_ID,
        V_VID,
        IN_STRATEGY_NM,
        IN_CONFIG_JSON,
        IN_USER_ID,
        V_START_TS,
        V_START_TS,
        TIMESTAMPTZ '9999-12-31 00:00:00+00',
        CASE WHEN V_VID = 1 THEN 'Y' ELSE 'N' END
    );

    OUT_STRATEGY_ID  := V_STRATEGY_ID;
    OUT_STRATEGY_VID := V_VID;

    OUT_SQLMSG := '40';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'BT', 'SP_INS_STRATEGY', V_LOG_START, NULL, V_OTHER_TEXT, IN_USER_ID,
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

            RAISE WARNING '[SP_INS_STRATEGY] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
