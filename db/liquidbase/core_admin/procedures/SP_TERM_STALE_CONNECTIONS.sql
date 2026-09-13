-- Terminate client backends that have been idle longer than IN_IDLE_SECONDS.
--
-- Aurora and long-lived app pools (InstrumentCache, BacktestCache) leave
-- sessions in pg_stat_activity as idle; when the server drops one side of
-- the link the client keeps using a dead socket until the next call fails.
-- This sweeps quant_app-owned idle sessions so they do not accumulate for
-- days. quant_app may terminate backends owned by the same role.
CREATE OR REPLACE PROCEDURE CORE_ADMIN.SP_TERM_STALE_CONNECTIONS(
    IN  IN_USER_ID          TEXT,
    IN  IN_IDLE_SECONDS     INTEGER,
    OUT OUT_SQLSTATE        TEXT,
    OUT OUT_SQLMSG          TEXT,
    OUT OUT_SQLERRMC        TEXT,
    OUT OUT_STALE_CNT       INTEGER,
    OUT OUT_TERMINATED_CNT  INTEGER
)
LANGUAGE plpgsql
SET plan_cache_mode = 'force_generic_plan'
AS $$
DECLARE
    V_IDLE_CUTOFF TIMESTAMPTZ;
    V_PID         INTEGER;
BEGIN
    OUT_SQLSTATE       := '00000';
    OUT_SQLMSG         := 'SUCCESS';
    OUT_SQLERRMC       := NULL;
    OUT_STALE_CNT      := 0;
    OUT_TERMINATED_CNT := 0;

    IF IN_IDLE_SECONDS IS NULL OR IN_IDLE_SECONDS < 1 THEN
        OUT_SQLSTATE := '22023';
        OUT_SQLMSG   := 'ERROR';
        OUT_SQLERRMC := 'IN_IDLE_SECONDS must be a positive integer';
        RETURN;
    END IF;

    V_IDLE_CUTOFF := clock_timestamp() - make_interval(secs => IN_IDLE_SECONDS);

    SELECT COUNT(*)
      INTO OUT_STALE_CNT
      FROM pg_stat_activity sa
     WHERE sa.pid <> pg_backend_pid()
       AND sa.datname = current_database()
       AND sa.backend_type = 'client backend'
       AND sa.usename = current_user
       AND sa.state IN ('idle', 'idle in transaction')
       AND sa.state_change < V_IDLE_CUTOFF;

    FOR V_PID IN
        SELECT sa.pid
          FROM pg_stat_activity sa
         WHERE sa.pid <> pg_backend_pid()
           AND sa.datname = current_database()
           AND sa.backend_type = 'client backend'
           AND sa.usename = current_user
           AND sa.state IN ('idle', 'idle in transaction')
           AND sa.state_change < V_IDLE_CUTOFF
    LOOP
        IF pg_terminate_backend(V_PID) THEN
            OUT_TERMINATED_CNT := OUT_TERMINATED_CNT + 1;
        END IF;
    END LOOP;

EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            OUT_SQLSTATE = RETURNED_SQLSTATE,
            OUT_SQLERRMC = MESSAGE_TEXT;
        OUT_SQLMSG := 'ERROR';
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_TERM_STALE_CONNECTIONS(
        TEXT, INTEGER, OUT TEXT, OUT TEXT, OUT TEXT, OUT INTEGER, OUT INTEGER
    ) TO quant_app;
  END IF;
END $$;
