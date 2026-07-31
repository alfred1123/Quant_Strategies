#!/usr/bin/env bash
# Dry-run Liquibase checks — validate changelogs and preview SQL without applying DDL.
#
# Usage:
#   ./scripts/liquibase-verify.sh              # validate + status + update-sql (needs DB)
#   ./scripts/liquibase-verify.sh --offline    # validate XML only (no database)
#   DB_TARGET=local ./scripts/liquibase-verify.sh
#
# Ports (set in .env or env):
#   DB_TARGET=local  → LOCAL_DB_HOST / LOCAL_DB_PORT  (default 127.0.0.1:5432)
#   DB_TARGET=prod   → QUANTDB_HOST / PROD_DB_PORT    (default localhost:5433)
#
# Liquibase commands used (none of these run update):
#   validate    — parse the changelog tree: XML, include/sqlFile targets, duplicate ids
#   status      — SELECT databasechangelog; list pending changesets
#   update-sql  — print SQL that update WOULD run; does not execute it
#   --offline   — validate + update-sql against url=offline:postgresql (no DB)
#
# Convention rules Liquibase has no opinion on — a changeset missing its context,
# or a procedure without splitStatements="false" — live in
# tests/unit/test_liquibase_changelogs.py, since the policy engine
# (`liquibase checks`) is a Pro-only feature.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LB_ROOT="${ROOT_DIR}/db/liquidbase"
APP_ENV="${APP_ENV:-prod}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
OFFLINE=false
[[ "${1:-}" == "--offline" ]] && OFFLINE=true

log() { echo "[liquibase-verify] $*"; }
die() { echo "[liquibase-verify] ERROR: $*" >&2; exit 1; }

# Same schema order as liquibase-deploy.sh
SCHEMA_DIRS=(core_admin refdata bt trade market_data inst)

ensure_prereqs() {
  bash "${ROOT_DIR}/aws/scripts/install-liquibase.sh"
}

load_env() {
  local _db_target_override="${DB_TARGET:-}"
  local _lb_url_override="${LIQUIBASE_COMMAND_URL:-}"

  if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +a
  fi

  if [[ -n "${_db_target_override}" ]]; then
    export DB_TARGET="${_db_target_override}"
  fi

  if [[ "${USE_SSM:-}" == "1" ]]; then
    log "Loading SSM parameters from /quant/${APP_ENV}/"
    local prefix="/quant/${APP_ENV}/"
    while IFS=$'\t' read -r name value; do
      [[ -z "$name" ]] && continue
      key="${name#"${prefix}"}"
      [[ "$key" == "$name" ]] && continue
      export "${key}=${value}"
    done < <(
      aws ssm get-parameters-by-path \
        --path "${prefix}" \
        --with-decryption \
        --recursive \
        --region "${AWS_REGION}" \
        --query 'Parameters[*].[Name,Value]' \
        --output text
    )
  fi

  if [[ "${DB_TARGET:-prod}" == "local" ]]; then
    export QUANTDB_HOST="${LOCAL_DB_HOST:-127.0.0.1}"
    export QUANTDB_PORT="${LOCAL_DB_PORT:-5432}"
    export QUANTDB_USERNAME="${LOCAL_DB_USER:-quant_admin}"
    export QUANTDB_PASSWORD="${LOCAL_DB_PASSWORD:-LetsGetRich888}"
    SSLMODE=disable
  else
    export QUANTDB_HOST="${QUANTDB_HOST:-localhost}"
    export QUANTDB_PORT="${PROD_DB_PORT:-${QUANTDB_PORT:-5433}}"
    SSLMODE=require
  fi

  if [[ -n "${_lb_url_override}" ]]; then
    export LIQUIBASE_COMMAND_URL="${_lb_url_override}"
  else
    export LIQUIBASE_COMMAND_URL="jdbc:postgresql://${QUANTDB_HOST}:${QUANTDB_PORT}/quantdb?sslmode=${SSLMODE}"
  fi
  export LIQUIBASE_COMMAND_USERNAME="${LIQUIBASE_COMMAND_USERNAME:-${QUANTDB_USERNAME:?QUANTDB_USERNAME required}}"
  export LIQUIBASE_COMMAND_PASSWORD="${LIQUIBASE_COMMAND_PASSWORD:-${QUANTDB_PASSWORD:?QUANTDB_PASSWORD required}}"
}

# An offline URL lets Liquibase parse the whole changelog tree and render every
# changeset's SQL with no database behind it, which is what makes these checks
# safe to run on a pull request.
DEPLOY_CONTEXT="${LIQUIBASE_CONTEXTS:-prod-deploy}"
OFFLINE_STATE_DIR=""

offline_url() {
  # An offline run records what it applied in a CSV and treats those changesets
  # as done next time. Left beside the changelog that turns every later run into
  # a no-op, so each run gets its own throwaway tracking file.
  echo "offline:postgresql?changeLogFile=${OFFLINE_STATE_DIR}/${1//\//_}.csv"
}

run_offline_validate() {
  local dir="$1"
  local label="$2"
  log "validate (offline): ${label}"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties --url="$(offline_url "$dir")" validate
  )
}

run_offline_update_sql() {
  local dir="$1"
  local label="$2"
  local outfile rendered
  outfile="${OFFLINE_STATE_DIR}/${dir//\//_}.sql"
  log "update-sql (offline, context=${DEPLOY_CONTEXT}): ${label}"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties --url="$(offline_url "$dir")" \
      update-sql --context-filter="${DEPLOY_CONTEXT}" --output-file="$outfile"
  )
  rendered="$(grep -c '^-- Changeset' "$outfile" 2>/dev/null || true)"
  log "  rendered ${rendered:-0} changeset(s)"
}

main_offline() {
  ensure_prereqs
  OFFLINE_STATE_DIR="$(mktemp -d)"
  trap 'rm -rf "${OFFLINE_STATE_DIR}"' EXIT
  log "Offline mode — no database, no DDL applied"

  # With a fresh tracking file nothing counts as applied, so this renders every
  # changeset rather than only the outstanding ones. That is the point: it proves
  # each one still parses, not what is pending.
  run_offline_validate "." "master (public)"
  run_offline_update_sql "." "master (public)"

  for schema in "${SCHEMA_DIRS[@]}"; do
    run_offline_validate "$schema" "${schema^^}"
    run_offline_update_sql "$schema" "${schema^^}"
  done

  log "Offline checks passed"
}

run_validate() {
  local dir="$1"
  local label="$2"
  log "validate: ${label}"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties validate
  )
}

run_status() {
  local dir="$1"
  local label="$2"
  log "status: ${label}"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties status --verbose
  )
}

run_update_sql() {
  local dir="$1"
  local label="$2"
  local outfile
  outfile="$(mktemp)"
  log "update-sql (dry run): ${label} → ${outfile}"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties update-sql --output-file="$outfile"
  )
  if [[ -s "$outfile" ]]; then
    log "Pending SQL for ${label}:"
    sed 's/^/    /' "$outfile"
  else
    log "No pending SQL for ${label}"
  fi
  rm -f "$outfile"
}

main_with_db() {
  ensure_prereqs
  load_env
  log "Target: ${LIQUIBASE_COMMAND_URL} (user=${LIQUIBASE_COMMAND_USERNAME})"

  run_validate "." "master (public)"
  run_status "." "master (public)"
  run_update_sql "." "master (public)"

  for schema in "${SCHEMA_DIRS[@]}"; do
    run_validate "$schema" "${schema^^}"
    run_status "$schema" "${schema^^}"
    run_update_sql "$schema" "${schema^^}"
  done

  # Grants refresh pass (core_admin only — same as deploy)
  log "status: CORE_ADMIN (grants refresh pass)"
  (
    cd "${LB_ROOT}/core_admin"
    liquibase --defaults-file=liquibase.properties status --verbose
  )

  log "Verify complete — no changes applied (validate + status + update-sql only)"
}

if [[ "$OFFLINE" == true ]]; then
  main_offline
else
  main_with_db
fi
