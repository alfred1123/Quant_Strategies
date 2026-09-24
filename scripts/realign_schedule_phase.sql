-- One-off DML: UPDATE current PENDING schedule cursors to bar-close phase.
--
-- Matches quant.shared.intervals.next_apply_slot using REFDATA.TM_INTERVAL +
-- REFDATA.APP_APPLY_TIMING (requires REFDATA 1.25.0+). Does not append a new
-- schedule version — only fixes SCHEDULED_TS on IS_CURRENT_IND = 'Y' rows.
--
-- Deliberate exception to the "no direct DML" rule: a one-off correction of a
-- cursor value, not an application write path. Do not promote this to an SP.
--
-- Local:
--   source .env && psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/realign_schedule_phase.sql
--
-- Prod (tunnel localhost:5433):
--   psql "postgresql://…@localhost:5433/quant" -v ON_ERROR_STOP=1 -f scripts/realign_schedule_phase.sql
--
-- Preview without writing (NOTICEs only):
--   psql … -v dry_run=true -f scripts/realign_schedule_phase.sql

\if :{?dry_run}
\else
\set dry_run 'false'
\endif

SET timezone = 'UTC';
SET client_min_messages = NOTICE;

-- psql does not interpolate :variables inside a dollar-quoted body, so the
-- flag is handed to the DO block through a GUC instead.
SET realign.dry_run = :'dry_run';

DO $realign$
DECLARE
    v_dry   boolean := current_setting('realign.dry_run', true) = 'true';
    v_after timestamptz := clock_timestamp();
    v_epoch timestamptz := timestamptz '1970-01-01 00:00:00+00';
    v_n     integer;
    r       record;
BEGIN
    CREATE TEMP TABLE _schedule_realign ON COMMIT DROP AS
    SELECT *
      FROM (
        SELECT
            ss.deployment_schedule_id,
            ss.deployment_schedule_vid,
            d.deployment_id,
            ss.scheduled_ts AS old_ts,
            CASE
                WHEN (b.boundary + ti.period_length - aat.execute_offset) > v_after
                THEN b.boundary + ti.period_length - aat.execute_offset
                ELSE b.boundary + (2 * ti.period_length) - aat.execute_offset
            END AS new_ts
        FROM trade.deployment d
        JOIN trade.deployment_schedule_status ss
          ON ss.deployment_id = d.deployment_id
         AND ss.is_current_ind = 'Y'
        JOIN refdata.tm_interval ti
          ON ti.tm_interval_id = d.schedule_tm_interval_id
        JOIN refdata.app_apply_timing aat
          ON aat.app_id = d.app_id
         AND aat.tm_interval_id = d.schedule_tm_interval_id
        CROSS JOIN LATERAL (
            SELECT v_epoch
                 + floor(
                       extract(epoch FROM (v_after - v_epoch))
                       / nullif(extract(epoch FROM ti.period_length), 0)
                   ) * ti.period_length AS boundary
        ) b
        WHERE d.schedule_tm_interval_id IS NOT NULL
          AND d.is_enabled_ind = 'Y'
          AND d.deployment_status NOT IN ('PAUSED', 'STOPPED')
          AND d.transact_to_ts = timestamptz '9999-12-31 00:00:00+00'
          AND ss.status = 'PENDING'
      ) s
     WHERE date_trunc('second', s.old_ts)
           IS DISTINCT FROM date_trunc('second', s.new_ts);

    SELECT count(*) INTO v_n FROM _schedule_realign;
    IF v_n = 0 THEN
        RAISE NOTICE 'no pending schedules need realignment (after=%)', v_after;
        RETURN;
    END IF;

    FOR r IN
        SELECT deployment_id, old_ts, new_ts
          FROM _schedule_realign
         ORDER BY old_ts
    LOOP
        RAISE NOTICE 'realign deployment=% % -> %',
            r.deployment_id, r.old_ts, r.new_ts;
    END LOOP;

    IF v_dry THEN
        RAISE NOTICE 'dry_run=true — % row(s) would be UPDATEd', v_n;
        RETURN;
    END IF;

    -- USER_ID is left as written: this corrects a cursor, it does not change
    -- who owns the version row.
    UPDATE trade.deployment_schedule_status ss
       SET scheduled_ts = t.new_ts
      FROM _schedule_realign t
     WHERE ss.deployment_schedule_id = t.deployment_schedule_id
       AND ss.deployment_schedule_vid = t.deployment_schedule_vid;

    GET DIAGNOSTICS v_n = ROW_COUNT;
    RAISE NOTICE 'done — updated % schedule row(s)', v_n;
END $realign$;
