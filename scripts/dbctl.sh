#!/usr/bin/env bash
# =============================================================================
# dbctl.sh — local Postgres management for dev practice
#
# Usage:
#   ./scripts/dbctl.sh dump              # dump Aurora → db/dumps/
#   ./scripts/dbctl.sh restore [file]    # restore latest (or named) dump → local
#   ./scripts/dbctl.sh reset             # drop + recreate local quantdb
#   ./scripts/dbctl.sh status            # show local cluster + DB state
#   ./scripts/dbctl.sh psql              # open psql on local quantdb
#
# restore and reset need the local DB to themselves, so both STOP THE DEV STACK
# (backend, frontend, worker) and evict any remaining sessions first — see
# claim_local_db. Restart it afterwards with ./scripts/appctl.sh dev start.
#
# Prerequisites:
#   - SSM tunnel running: ./scripts/appctl.sh dev tunnel start
#   - Local PG17 server running: sudo systemctl start postgresql
#   - .env with QUANTDB_PASSWORD set (Aurora password)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUMP_DIR="$ROOT_DIR/db/dumps"
PG_DUMP_BIN="/usr/lib/postgresql/17/bin/pg_dump"

# dump/restore is the one command that spans both ends — it copies prod into
# local — so it resolves both rather than switching on DB_TARGET.
# shellcheck source=lib/db-target.sh
source "$ROOT_DIR/scripts/lib/db-target.sh"
db_local_env
db_prod_env

# Aurora, always via the SSM tunnel: this script only ever runs on a laptop,
# so the host is loopback whatever QUANTDB_HOST says, and the port is the
# tunnel's rather than the QUANTDB_PORT the app may point at a local server.
RDS_HOST=127.0.0.1
RDS_PORT="${PROD_DB_PORT:-$(db_field prod port)}"
RDS_USER="${DB_PROD_USER}"
RDS_DB="${DB_PROD_NAME}"
db_assert_not_local "$RDS_HOST" "$RDS_PORT" || exit 1

# Local
LOCAL_HOST="${DB_LOCAL_HOST}"
LOCAL_PORT="${DB_LOCAL_PORT}"
LOCAL_USER="${DB_LOCAL_USER}"
LOCAL_DB="${DB_LOCAL_NAME}"
LOCAL_PASSWORD="${DB_LOCAL_PASSWORD}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[dbctl] $*"; }
error() { echo "[dbctl] ERROR: $*" >&2; exit 1; }

require_tunnel() {
  python3 -c "
import socket, sys
s = socket.socket(); s.settimeout(10)
try:
    s.connect(('$RDS_HOST', $RDS_PORT)); s.close()
except Exception:
    sys.exit(1)
" || error "SSM tunnel is not running on :$RDS_PORT. Start it with: ./scripts/appctl.sh dev tunnel start"
}

require_local_pg() {
  pg_isready -h "$LOCAL_HOST" -p "$LOCAL_PORT" -q 2>/dev/null \
    || error "Local Postgres is not running. Start it with: sudo systemctl start postgresql"
}

load_rds_password() {
  # shellcheck source=../.env
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a; source "$ROOT_DIR/.env"; set +a
  fi
  [[ -n "${QUANTDB_PASSWORD:-}" ]] \
    || error ".env missing QUANTDB_PASSWORD. Cannot connect to Aurora."
  export PGPASSWORD="$QUANTDB_PASSWORD"
}

latest_dump() {
  ls -t "$DUMP_DIR"/quantdb_*.dump 2>/dev/null | head -1
}

local_psql() {
  PGPASSWORD="$LOCAL_PASSWORD" psql \
    -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" "$@"
}

# Sessions on the local DB other than our own. Any failure counts as zero: if
# the DB does not exist yet (reset) there is nothing to evict.
local_backends() {
  local_psql -tAc \
    "SELECT count(*) FROM pg_stat_activity
      WHERE datname = '$LOCAL_DB' AND pid <> pg_backend_pid();" 2>/dev/null \
    | tr -d '[:space:]' || true
}

# Take the local DB for exclusive use before rewriting it.
#
# pg_restore --clean needs ACCESS EXCLUSIVE on every table it drops, and
# DROP DATABASE needs the database empty of sessions. The dev API holds
# persistent connections (two cache classes, by design), so one of them sitting
# idle-in-transaction is enough to make a restore queue behind it **forever** —
# no error, no output, just a hang that looks like slowness. That cost nine
# minutes once; clearing the way is part of the job, not a thing to remember.
claim_local_db() {
  local n; n=$(local_backends)
  [[ -z "$n" || "$n" == "0" ]] && return 0

  info "$n other session(s) hold $LOCAL_DB — stopping the dev stack first."
  # Terminating alone would only open a race: the app reconnects on its next
  # query and can re-take a lock halfway through the restore. Stop the owners,
  # then sweep up whatever else is left (stray psql, an editor's connection).
  DB_TARGET=local "$ROOT_DIR/scripts/appctl.sh" dev stop 2>&1 | sed 's/^/  /' || true

  local_psql -q -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
      WHERE datname = '$LOCAL_DB' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true

  n=$(local_backends)
  [[ -z "$n" || "$n" == "0" ]] \
    || error "$n session(s) still hold $LOCAL_DB. Close them and retry — restoring now would hang, not fail."
  info "$LOCAL_DB is free. Restart the app afterwards with: ./scripts/appctl.sh dev start"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

# Nothing is excluded from the dump, deliberately.
#
# CORE_ADMIN.LOG_PROC_DETAIL is the obvious candidate — 33 MB of 53, and the
# SSM tunnel drops with a broken pipe on long transfers, so leaving it out cut
# a run from 7.6 MB/102s to 4.6 MB/60s and halved the window in which that can
# happen. It is still copied: the timings are the only record of how production
# actually behaves under load, and a local mirror missing them cannot be used
# to go looking for a problem that has not been named yet. Pay the transfer.
cmd_dump() {
  require_tunnel
  load_rds_password
  export PGSSLMODE=require
  mkdir -p "$DUMP_DIR"
  local outfile="$DUMP_DIR/quantdb_$(date +%Y%m%d_%H%M%S).dump"

  info "Dumping Aurora quantdb → $outfile"
  # A dump that died leaves a 0-byte file behind, and `restore` with no
  # argument takes the *latest* — which would then be the empty one, silently
  # preferred over the last good dump. Remove it on the way out instead.
  if ! "$PG_DUMP_BIN" \
    -h "$RDS_HOST" -p "$RDS_PORT" \
    -U "$RDS_USER" -d "$RDS_DB" \
    -Fc -Z 6 -v \
    -f "$outfile"; then
    rm -f "$outfile"
    error "pg_dump failed (the tunnel drops on long transfers — retry). Removed $outfile"
  fi
  info "Done. $(du -sh "$outfile" | cut -f1) written to $outfile"
}

cmd_restore() {
  require_local_pg
  local dumpfile="${1:-$(latest_dump)}"
  [[ -n "$dumpfile" ]] || error "No dump file found in $DUMP_DIR. Run: ./scripts/dbctl.sh dump"
  [[ -f "$dumpfile" ]] || error "File not found: $dumpfile"
  claim_local_db

  info "Restoring $dumpfile → local $LOCAL_DB"
  export PGPASSWORD="$LOCAL_PASSWORD"
  pg_restore \
    -h "$LOCAL_HOST" -p "$LOCAL_PORT" \
    -U "$LOCAL_USER" -d "$LOCAL_DB" \
    --no-owner --no-privileges \
    --clean --if-exists \
    -j 4 -v \
    "$dumpfile" 2>&1 | grep -v "^pg_restore: warning: errors ignored"
  info "Restore complete."
  info "Local dump omits cluster roles — run: ./scripts/dbctl.sh bootstrap-roles"
}

cmd_bootstrap_roles() {
  require_local_pg
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a; source "$ROOT_DIR/.env"; set +a
  fi
  local app_pw="${QUANTDB_PASSWORD_APP:-LetsGetRich888App}"
  info "Creating quant_app login role (matches Aurora) if missing..."
  sudo -u postgres psql -d "$LOCAL_DB" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quant_app') THEN
    CREATE ROLE quant_app LOGIN PASSWORD '${app_pw}';
    RAISE NOTICE 'Created role quant_app';
  ELSE
    RAISE NOTICE 'Role quant_app already exists';
  END IF;
END \$\$;
GRANT USAGE ON SCHEMA CORE_ADMIN, REFDATA, BT, INST, TRADE, MARKET_DATA TO quant_app;
SQL
  info "Done. Re-run: DB_TARGET=local ./scripts/liquibase-deploy.sh"
}

cmd_reset() {
  require_local_pg
  claim_local_db
  info "Dropping and recreating local '$LOCAL_DB' owned by '$LOCAL_USER'..."
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS $LOCAL_DB;
DROP USER IF EXISTS $LOCAL_USER;
CREATE USER $LOCAL_USER WITH PASSWORD '$LOCAL_PASSWORD';
CREATE DATABASE $LOCAL_DB OWNER $LOCAL_USER;
GRANT ALL PRIVILEGES ON DATABASE $LOCAL_DB TO $LOCAL_USER;
SQL
  info "Database reset. Ready for restore."
}

cmd_status() {
  echo "=== Local Postgres cluster ==="
  pg_lsclusters 2>/dev/null || echo "pg_lsclusters not found"

  echo ""
  echo "=== Local DB check ==="
  export PGPASSWORD="$LOCAL_PASSWORD"
  if psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" \
       -c "\dn" 2>/dev/null; then
    psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" \
       -c "SELECT schemaname, count(*) AS tables FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') GROUP BY schemaname ORDER BY schemaname;"
  else
    echo "Cannot connect to local DB (run ./scripts/dbctl.sh reset first?)"
  fi

  echo ""
  echo "=== Latest dump ==="
  local f; f=$(latest_dump)
  if [[ -n "$f" ]]; then
    ls -lh "$f"
  else
    echo "No dumps in $DUMP_DIR"
  fi
}

cmd_psql() {
  require_local_pg
  export PGPASSWORD="$LOCAL_PASSWORD"
  psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
  dump)    cmd_dump ;;
  restore) cmd_restore "${2:-}" ;;
  reset)   cmd_reset ;;
  bootstrap-roles) cmd_bootstrap_roles ;;
  status)  cmd_status ;;
  psql)    cmd_psql ;;
  *)
    echo "Usage: $0 {dump|restore [file]|reset|bootstrap-roles|status|psql}"
    exit 1
    ;;
esac
