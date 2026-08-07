-- ===========================================================================
-- GRANTs for quant_app (the FastAPI app) and quant_admin (you, via psql).
--
-- Idempotent: GRANT is idempotent in Postgres. Run as cluster master.
-- runOnChange=true so newly added procs in any schema get EXECUTE on every
-- deploy.
--
-- Strict policy: quant_app has NO direct table access (no SELECT/INSERT/
-- UPDATE/DELETE) and NO default-privileges entries. Every read AND write
-- goes through a stored procedure. See docs/design/login.md §7.4.
--
-- ⚠️  DEPLOYMENT ORDER — only name a CORE_ADMIN proc here once it already exists.
--   This file runs from 1.3.0-grants-refresh, which is runAlways and is included
--   BEFORE the later release files. Naming a procedure here that one of those
--   releases creates deadlocks a database that does not have it yet: the GRANT
--   raises "procedure does not exist", which aborts the run before the CREATE it
--   was waiting on, so the proc can never appear. It is not self-healing —
--   every subsequent deploy fails the same way.
--
--   For a NEW CORE_ADMIN proc that quant_app needs, put a guarded grant at the
--   foot of the procedure's own .sql file instead (see SP_INS_LOG_PROC_SUMMARY,
--   or the MARKET_DATA procs). The grant then follows its CREATE in the same
--   file and cannot be ordered wrongly. The names below predate that convention
--   and are safe only because they are long since deployed.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- quant_app : the runtime application
--   USAGE on schemas + EXECUTE on app-facing procs only. No table access.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA CORE_ADMIN, REFDATA, BT, INST, TRADE, MARKET_DATA TO quant_app;

-- EXECUTE on every business-schema routine.
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA REFDATA TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA BT      TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA INST    TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA TRADE   TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA MARKET_DATA TO quant_app;

-- CORE_ADMIN: app may execute ONLY the auth-related procs below.
-- (Listed by name so admin SPs are NOT granted by an "ALL ROUTINES" sweep.)
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_APP_USER_BY_USERNAME(TEXT, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT) TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_APP_USER_BY_ID(UUID, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT)       TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_LAST_LOGIN(UUID, OUT TEXT, OUT TEXT, OUT TEXT)             TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_INS_API_CREDENTIAL(UUID, INTEGER, TEXT, TEXT, TEXT, INTEGER, OUT INTEGER, OUT INTEGER, OUT TEXT, OUT TEXT, OUT TEXT) TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_API_CREDENTIAL(UUID, INTEGER, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT) TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_API_CREDENTIAL_REVOKE(UUID, INTEGER, OUT INTEGER, OUT TEXT, OUT TEXT, OUT TEXT) TO quant_app;
-- SP_INS_LOG_PROC_SUMMARY is granted by its own file — see the ordering note above.

-- ---------------------------------------------------------------------------
-- quant_admin : the human admin via psql (user-management only)
-- ---------------------------------------------------------------------------
GRANT USAGE  ON SCHEMA CORE_ADMIN     TO quant_admin;
GRANT SELECT ON CORE_ADMIN.APP_USER   TO quant_admin;

GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_INS_APP_USER(TEXT, TEXT, TEXT, OUT UUID, OUT TEXT, OUT TEXT, OUT TEXT)         TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_PASSWORD(TEXT, TEXT, TEXT, OUT TEXT, OUT TEXT, OUT TEXT)          TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_ACTIVE(TEXT, CHAR, TEXT, OUT TEXT, OUT TEXT, OUT TEXT)            TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_BUMP_TOKEN(TEXT, TEXT, OUT TEXT, OUT TEXT, OUT TEXT)              TO quant_admin;
