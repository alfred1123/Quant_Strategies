CREATE OR REPLACE FUNCTION BT.FN_GET_QUEUE(
    IN  IN_QUEUE_ID          UUID    DEFAULT NULL,
    IN  IN_STRATEGY_ID       UUID    DEFAULT NULL,
    IN  IN_QUEUE_STATUS_ID   INTEGER DEFAULT NULL,
    IN  IN_USER_ID           TEXT    DEFAULT NULL,
    IN  IN_LIMIT             INTEGER DEFAULT 50
)
RETURNS TABLE (
    QUEUE_ID         UUID,
    QUEUE_VID        INTEGER,
    STRATEGY_ID      UUID,
    STRATEGY_VID     INTEGER,
    TRANSACT_FROM_TS TIMESTAMPTZ,
    QUEUE_STATUS_ID  INTEGER,
    QUEUE_STATUS     TEXT,
    PRIORITY         INTEGER,
    ERROR_TEXT       TEXT,
    USER_ID          TEXT
)
LANGUAGE plpgsql
VOLATILE
AS $$
/*
 * Dynamic SQL avoids the catch-all query anti-pattern.
 * Optional predicates are only appended when the parameter is non-null,
 * so the planner sees a small, precise WHERE clause per call and can
 * pick the right index (IX_QUEUE_STRATEGY, IX_QUEUE_STATUS_CURRENT, etc.)
 *
 * QUEUE_ID mode:  returns ALL VIDs for that job (full history, no sentinel).
 * Default mode:   active rows only (TRANSACT_TO_TS sentinel), other params optional.
 */
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_SQL        TEXT;
    V_LIMIT      INTEGER := COALESCE(IN_LIMIT, 50);
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    V_OTHER_TEXT := 'IN_QUEUE_ID='        || COALESCE(IN_QUEUE_ID::TEXT, '')
                 || ', IN_STRATEGY_ID='   || COALESCE(IN_STRATEGY_ID::TEXT, '')
                 || ', IN_QUEUE_STATUS_ID=' || COALESCE(IN_QUEUE_STATUS_ID::TEXT, '')
                 || ', IN_USER_ID='       || COALESCE(IN_USER_ID, '')
                 || ', IN_LIMIT='         || V_LIMIT::TEXT;

    -- Fixed USING positions: $1=IN_QUEUE_ID, $2=IN_STRATEGY_ID, $3=IN_QUEUE_STATUS_ID, $4=IN_USER_ID, $5=V_LIMIT
    -- Unused $N args are silently ignored by PostgreSQL.
    V_SQL :=
        'SELECT q.QUEUE_ID,'
        '       q.QUEUE_VID,'
        '       q.STRATEGY_ID,'
        '       q.STRATEGY_VID,'
        '       q.TRANSACT_FROM_TS,'
        '       q.QUEUE_STATUS_ID,'
        '       rs.NAME AS QUEUE_STATUS,'
        '       q.PRIORITY,'
        '       q.ERROR_TEXT,'
        '       q.USER_ID'
        '  FROM BT.QUEUE q'
        '  JOIN REFDATA.QUEUE_STATUS rs ON rs.QUEUE_STATUS_ID = q.QUEUE_STATUS_ID'
        ' WHERE 1=1';

    IF IN_QUEUE_ID IS NOT NULL THEN
        -- Full history for this specific job; no sentinel filter.
        V_SQL := V_SQL || ' AND q.QUEUE_ID = $1';
    ELSE
        -- Active rows only.
        V_SQL := V_SQL || ' AND q.TRANSACT_TO_TS = TIMESTAMPTZ ''9999-12-31''';
    END IF;

    IF IN_STRATEGY_ID IS NOT NULL THEN
        V_SQL := V_SQL || ' AND q.STRATEGY_ID = $2';
    END IF;

    IF IN_QUEUE_STATUS_ID IS NOT NULL THEN
        V_SQL := V_SQL || ' AND q.QUEUE_STATUS_ID = $3';
    END IF;

    IF IN_USER_ID IS NOT NULL THEN
        V_SQL := V_SQL || ' AND q.USER_ID = $4';
    END IF;

    V_SQL := V_SQL || ' ORDER BY q.QUEUE_ID ASC, q.QUEUE_VID ASC LIMIT $5';

    -- Audit log before executing — RETURN QUERY exits immediately after.
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'FN_GET_QUEUE', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

    RETURN QUERY EXECUTE V_SQL USING IN_QUEUE_ID, IN_STRATEGY_ID, IN_QUEUE_STATUS_ID, IN_USER_ID, V_LIMIT;

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

            RAISE WARNING '[FN_GET_QUEUE] % (SQLSTATE: %). Detail: %. Context: %. Params: %. SQL: %',
                V_MSG, V_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT, V_SQL;

            -- Re-raise so caller sees the failure (functions can't return OUT status).
            RAISE;
        END;
END;
$$;
