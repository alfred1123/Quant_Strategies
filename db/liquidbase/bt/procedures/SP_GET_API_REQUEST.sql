CREATE OR REPLACE PROCEDURE BT.SP_GET_API_REQUEST(
    IN  IN_APP_ID          INTEGER,
    IN  IN_APP_METRIC_ID   INTEGER,
    IN  IN_TM_INTERVAL_ID  INTEGER,
    IN  IN_INTERNAL_CUSIP  TEXT,
    OUT OUT_RESULT         REFCURSOR,
    OUT OUT_SQLSTATE       TEXT,
    OUT OUT_SQLMSG         TEXT,
    OUT OUT_SQLERRMC       TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_SQL        TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_APP_ID=' || COALESCE(IN_APP_ID::TEXT, '')
                 || ', IN_APP_METRIC_ID=' || COALESCE(IN_APP_METRIC_ID::TEXT, '')
                 || ', IN_TM_INTERVAL_ID=' || COALESCE(IN_TM_INTERVAL_ID::TEXT, '')
                 || ', IN_INTERNAL_CUSIP=' || COALESCE(IN_INTERNAL_CUSIP, '');

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_api_request_cursor';

    V_SQL := '
        SELECT
            r.API_REQ_ID,
            r.APP_ID,
            r.APP_METRIC_ID,
            r.TM_INTERVAL_ID,
            r.INTERNAL_CUSIP,
            r.PRODUCT_GRP_ID,
            r.RANGE_START_TS,
            r.RANGE_END_TS,
            lp.PAYLOAD
        FROM BT.API_REQUEST r
        INNER JOIN BT.API_REQUEST_PAYLOAD lp
            ON r.API_REQ_ID = lp.API_REQ_ID
           AND r.API_REQ_VID = lp.API_REQ_VID
        WHERE r.TRANSACT_TO_TS = TIMESTAMPTZ ''9999-12-31''';

    IF IN_APP_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND r.APP_ID = %s', IN_APP_ID);
    END IF;

    IF IN_APP_METRIC_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND r.APP_METRIC_ID = %s', IN_APP_METRIC_ID);
    END IF;

    IF IN_TM_INTERVAL_ID IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND r.TM_INTERVAL_ID = %s', IN_TM_INTERVAL_ID);
    END IF;

    IF IN_INTERNAL_CUSIP IS NOT NULL THEN
        V_SQL := V_SQL || format(' AND r.INTERNAL_CUSIP = %L', IN_INTERNAL_CUSIP);
    END IF;

    OPEN OUT_RESULT FOR EXECUTE V_SQL;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_API_REQUEST', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_API_REQUEST] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;