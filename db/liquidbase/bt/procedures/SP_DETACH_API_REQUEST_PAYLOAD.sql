-- Detach and drop a payload partition whose range ended before the
-- retention window. The partition bound decides. API_REQUEST is not read
-- and not written.

CREATE OR REPLACE PROCEDURE BT.SP_DETACH_API_REQUEST_PAYLOAD(
    IN  IN_RETENTION_DAYS INTEGER,
    OUT OUT_SQLSTATE      TEXT,
    OUT OUT_SQLMSG        TEXT,
    OUT OUT_SQLERRMC      TEXT,
    OUT OUT_DROPPED       INTEGER
)
LANGUAGE plpgsql
AS $proc$
DECLARE
    V_START_TS   TIMESTAMPTZ := CURRENT_TIMESTAMP;
    V_LOG_START  TIMESTAMPTZ := clock_timestamp();
    V_OTHER_TEXT TEXT;
    V_LOG_STATE  TEXT;
    V_LOG_MSG    TEXT;
    V_CUTOFF     TIMESTAMPTZ;
    V_PART       RECORD;
BEGIN
    OUT_SQLSTATE := '00000';
    OUT_SQLMSG   := '0';
    OUT_SQLERRMC := 'Stored Procedure completed successfully';
    OUT_DROPPED  := 0;

    IF IN_RETENTION_DAYS IS NULL OR IN_RETENTION_DAYS < 1 THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLERRMC := 'IN_RETENTION_DAYS must be at least 1';
        RETURN;
    END IF;

    V_OTHER_TEXT := 'IN_RETENTION_DAYS=' || IN_RETENTION_DAYS::TEXT;
    V_CUTOFF := V_START_TS - (IN_RETENTION_DAYS * INTERVAL '1 day');

    OUT_SQLMSG := '10';
    FOR V_PART IN
        SELECT c.relname,
               (regexp_match(pg_get_expr(c.relpartbound, c.oid), $re$TO \('([^']+)'\)$re$))[1]::timestamptz AS hi
          FROM pg_inherits i
          JOIN pg_class c ON c.oid = i.inhrelid
          JOIN pg_class parent ON parent.oid = i.inhparent
          JOIN pg_namespace n ON n.oid = parent.relnamespace
         WHERE n.nspname = 'bt'
           AND parent.relname = 'api_request_payload'
           AND pg_get_expr(c.relpartbound, c.oid) LIKE 'FOR VALUES FROM%'
    LOOP
        IF V_PART.hi > V_CUTOFF THEN
            CONTINUE;
        END IF;

        EXECUTE format(
            'ALTER TABLE bt.api_request_payload DETACH PARTITION bt.%I',
            V_PART.relname
        );
        EXECUTE format('DROP TABLE bt.%I', V_PART.relname);
        OUT_DROPPED := OUT_DROPPED + 1;
    END LOOP;

    OUT_SQLMSG := '20';
    V_OTHER_TEXT := V_OTHER_TEXT || ', OUT_DROPPED=' || OUT_DROPPED::TEXT;
    CALL CORE_ADMIN.CORE_INS_LOG_PROC(
        'BT', 'SP_DETACH_API_REQUEST_PAYLOAD', V_LOG_START, NULL,
        V_OTHER_TEXT, NULL, V_LOG_STATE, V_LOG_MSG
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

            RAISE WARNING '[SP_DETACH_API_REQUEST_PAYLOAD] % (SQLSTATE: %). Detail: %. Context: %. Params: %',
                OUT_SQLERRMC, OUT_SQLSTATE, V_DETAIL, V_CONTEXT, V_OTHER_TEXT;
        END;
END;
$proc$;
