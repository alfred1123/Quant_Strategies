CREATE OR REPLACE FUNCTION BT.FN_GET_QUEUE_FOR_TERMINAL(
    IN  IN_USER_ID           TEXT    DEFAULT NULL,
    IN  IN_QUEUE_STATUS_ID   INTEGER DEFAULT NULL
)
RETURNS TABLE (
    QUEUE_ID          UUID,
    STRATEGY_ID       UUID,
    STRATEGY_VID      INTEGER,
    STRATEGY_NM       TEXT,
    STRAT_CURRENT_IND CHAR(1),
    IS_BEST_IND       CHAR(1),
    TRANSACT_FROM_TS  TIMESTAMPTZ,
    QUEUE_STATUS      TEXT,
    PRIORITY          INTEGER,
    USER_ID           TEXT,
    CONFIG_JSON       JSONB,
    ERROR_TEXT        TEXT
)
LANGUAGE plpgsql
VOLATILE
AS $$
/*
 * Dynamic SQL so optional USER_ID and QUEUE_STATUS_ID predicates only appear
 * when supplied — planner gets a precise WHERE clause and can use
 * IX_QUEUE_USER_CURRENT or IX_QUEUE_STATUS_CURRENT accordingly.
 *
 * Default: all active rows with status IN (1,2,3) across all users.
 */
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_SQL        TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    V_OTHER_TEXT := 'IN_USER_ID='          || COALESCE(IN_USER_ID, '')
                 || ', IN_QUEUE_STATUS_ID=' || COALESCE(IN_QUEUE_STATUS_ID::TEXT, '');

    -- Fixed USING positions: $1=IN_USER_ID, $2=IN_QUEUE_STATUS_ID
    -- Unused $N args are silently ignored by PostgreSQL.
    V_SQL :=
        'SELECT q.QUEUE_ID,'
        '       q.STRATEGY_ID,'
        '       q.STRATEGY_VID,'
        '       s.STRATEGY_NM,'
        '       CASE WHEN s.TRANSACT_TO_TS = TIMESTAMPTZ ''9999-12-31 00:00:00+00'' THEN ''Y'' ELSE ''N'' END AS STRAT_CURRENT_IND,'
        '       s.IS_BEST_IND,'
        '       q.TRANSACT_FROM_TS,'
        '       (SELECT NAME FROM REFDATA.QUEUE_STATUS WHERE QUEUE_STATUS_ID = q.QUEUE_STATUS_ID) AS QUEUE_STATUS,'
        '       q.PRIORITY,'
        '       q.USER_ID,'
        '       s.CONFIG_JSON,'
        '       q.ERROR_TEXT'
        '  FROM BT.QUEUE q'
        '  JOIN BT.STRATEGY s ON s.STRATEGY_ID  = q.STRATEGY_ID'
        '                    AND s.STRATEGY_VID = q.STRATEGY_VID'
        ' WHERE q.TRANSACT_TO_TS = TIMESTAMPTZ ''9999-12-31 00:00:00+00''';

    IF IN_QUEUE_STATUS_ID IS NOT NULL THEN
        V_SQL := V_SQL || ' AND q.QUEUE_STATUS_ID = $2';
    ELSE
        V_SQL := V_SQL || ' AND q.QUEUE_STATUS_ID IN (1, 2, 3)';
    END IF;

    IF IN_USER_ID IS NOT NULL THEN
        V_SQL := V_SQL || ' AND q.USER_ID = $1';
    END IF;

    V_SQL := V_SQL || ' ORDER BY q.PRIORITY ASC, q.TRANSACT_FROM_TS ASC';

    -- Audit log before executing — RETURN QUERY exits immediately after.
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'FN_GET_QUEUE_FOR_TERMINAL', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

    RETURN QUERY EXECUTE V_SQL USING IN_USER_ID, IN_QUEUE_STATUS_ID;

EXCEPTION
    WHEN OTHERS THEN
        DECLARE
            V_SQLSTATE TEXT;
            V_MSG      TEXT;
            V_DETAIL   TEXT;
            V_CONTEXT  TEXT;
        BEGIN
            GET STACKED DIAGNOSTICS
                V_SQLSTATE = RETURNED_SQLSTATE,
                V_MSG      = MESSAGE_TEXT,
                V_DETAIL   = PG_EXCEPTION_DETAIL,
                V_CONTEXT  = PG_EXCEPTION_CONTEXT;

            RAISE WARNING '[FN_GET_QUEUE_FOR_TERMINAL] % (SQLSTATE: %). Detail: %. Context: %. Params: %. SQL: %',
                V_MSG, V_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT, V_SQL;

            -- Re-raise so caller sees the failure (functions can't return OUT status).
            RAISE;
        END;
END;
$$;
