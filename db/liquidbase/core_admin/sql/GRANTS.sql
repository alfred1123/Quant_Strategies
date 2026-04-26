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
-- ⚠️  DEPLOYMENT ORDER:
--   This changeset (099-core-admin-grants) names CORE_ADMIN.SP_* procedures
--   that are added later (SP_GET_APP_USER_BY_USERNAME, SP_INS_APP_USER, etc.).
--   It will FAIL on first deploy until those proc changesets are added to
--   core_admin-changelog.xml. That ordering is intentional — grants must run
--   AFTER the procs they reference exist.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- quant_app : the runtime application
--   USAGE on schemas + EXECUTE on app-facing procs only. No table access.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA CORE_ADMIN, REFDATA, BT, INST, TRADE TO quant_app;

-- EXECUTE on every business-schema routine.
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA REFDATA TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA BT      TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA INST    TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA TRADE   TO quant_app;

-- CORE_ADMIN: app may execute ONLY the two auth-related procs.
-- (Listed by name so admin SPs are NOT granted by an "ALL ROUTINES" sweep.)
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_APP_USER_BY_USERNAME(TEXT, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT) TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_APP_USER_BY_ID(UUID, OUT REFCURSOR, OUT TEXT, OUT TEXT, OUT TEXT)       TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_LAST_LOGIN(UUID, OUT TEXT, OUT TEXT, OUT TEXT)             TO quant_app;

-- ---------------------------------------------------------------------------
-- quant_admin : the human admin via psql (user-management only)
-- ---------------------------------------------------------------------------
GRANT USAGE  ON SCHEMA CORE_ADMIN     TO quant_admin;
GRANT SELECT ON CORE_ADMIN.APP_USER   TO quant_admin;

GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_INS_APP_USER(TEXT, TEXT, TEXT, OUT UUID, OUT TEXT, OUT TEXT, OUT TEXT)         TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_PASSWORD(TEXT, TEXT, TEXT, OUT TEXT, OUT TEXT, OUT TEXT)          TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_ACTIVE(TEXT, CHAR, TEXT, OUT TEXT, OUT TEXT, OUT TEXT)            TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_BUMP_TOKEN(TEXT, TEXT, OUT TEXT, OUT TEXT, OUT TEXT)              TO quant_admin;
