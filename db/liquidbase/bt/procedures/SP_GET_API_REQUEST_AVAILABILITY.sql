-- Current API_REQUEST windows, without the JSON body.
-- A header whose payload is gone still comes back, with HAS_PAYLOAD_IND = N.
-- There is no user filter. The series is shared.

CREATE OR REPLACE PROCEDURE BT.SP_GET_API_REQUEST_AVAILABILITY(
    OUT OUT_RESULT    REFCURSOR,
    OUT OUT_SQLSTATE  TEXT,
    OUT OUT_SQLMSG    TEXT,
    OUT OUT_SQLERRMC  TEXT
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';

    OUT_SQLMSG := '10';
    OUT_RESULT := 'sp_get_api_request_availability_cursor';
    OPEN OUT_RESULT FOR
        SELECT
            r.APP_ID,
            r.APP_METRIC_ID,
            r.TM_INTERVAL_ID,
            r.INTERNAL_CUSIP,
            r.RANGE_START_TS,
            r.RANGE_END_TS,
            CASE WHEN lp.API_REQ_ID IS NULL THEN 'N' ELSE 'Y' END AS HAS_PAYLOAD_IND
        FROM BT.API_REQUEST r
        LEFT JOIN BT.API_REQUEST_PAYLOAD lp
            ON lp.API_REQ_ID = r.API_REQ_ID
           AND lp.API_REQ_VID = r.API_REQ_VID
        WHERE r.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
        ORDER BY r.INTERNAL_CUSIP, r.APP_ID, r.APP_METRIC_ID;

    OUT_SQLMSG := '20';
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'BT', 'SP_GET_API_REQUEST_AVAILABILITY', V_LOG_START, NULL,
        NULL, NULL, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_GET_API_REQUEST_AVAILABILITY] % (SQLSTATE: %). Detail: %. Context: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT;
        END;
END;
$$;
