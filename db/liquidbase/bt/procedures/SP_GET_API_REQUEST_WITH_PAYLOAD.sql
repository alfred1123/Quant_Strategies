CREATE OR REPLACE PROCEDURE BT.SP_GET_API_REQUEST_WITH_PAYLOAD(
    IN  IN_API_REQ_ID   UUID,
    OUT OUT_RESULT       REFCURSOR,
    OUT OUT_SQLSTATE     TEXT,
    OUT OUT_SQLMSG       TEXT,
    OUT OUT_SQLERRMC     TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    V_OTHER_TEXT := 'IN_API_REQ_ID=' || COALESCE(IN_API_REQ_ID::TEXT, 'ALL');

    -- Step 10: Open cursor — join current API_REQUEST with latest payload VID
    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_api_request_with_payload_cursor';

    OPEN OUT_RESULT FOR
        SELECT
            r.API_REQ_ID,
            r.API_REQ_VID,
            r.APP_ID,
            r.APP_METRIC_ID,
            r.TM_INTERVAL_ID,
            r.SYMBOL,
            r.FULL_RANGE_START,
            r.FULL_RANGE_END,
            p.RANGE_START_TS,
            p.RANGE_END_TS,
            p.PAYLOAD
          FROM BT.API_REQUEST r
          LEFT JOIN BT.API_REQUEST_PAYLOAD p
            ON  p.API_REQ_ID  = r.API_REQ_ID
            AND p.API_REQ_VID = r.API_REQ_VID
         WHERE r.IS_CURRENT_IND = 'Y'
           AND r.API_REQ_ID     = IN_API_REQ_ID;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC('BT', 'SP_GET_API_REQUEST_WITH_PAYLOAD', V_START_TS, NULL, V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG);

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

            RAISE WARNING '[SP_GET_API_REQUEST_WITH_PAYLOAD] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$$;
