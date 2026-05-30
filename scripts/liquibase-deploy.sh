#!/usr/bin/env bash
# Apply pending Liquibase migrations (prod deploy or local).
#
# Usage:
#   ./scripts/liquibase-deploy.sh              # Aurora tunnel :5433 (DB_TARGET=prod)
#   DB_TARGET=local ./scripts/liquibase-deploy.sh   # local Postgres :5432
#   APP_ENV=prod USE_SSM=1 ./scripts/liquibase-deploy.sh   # EC2: load /quant/prod/* from SSM
#
# Order: master (schemas) → per-schema DDL/procs → core_admin grants refresh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LB_ROOT="${ROOT_DIR}/db/liquidbase"
APP_ENV="${APP_ENV:-prod}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"

log() { echo "[liquibase-deploy] $*"; }
die() { echo "[liquibase-deploy] ERROR: $*" >&2; exit 1; }

ensure_prereqs() {
  log "Checking Java + Liquibase (Liquibase requires Java 11+)"
  bash "${ROOT_DIR}/aws/scripts/install-liquibase.sh"
}

load_env() {
  # Preserve DB_TARGET when caller set it before sourcing .env (e.g. DB_TARGET=prod ./scripts/…)
  local _db_target_override="${DB_TARGET:-}"

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

  # Same target selection as liquibase-verify.sh / appctl.sh DB_TARGET
  if [[ "${DB_TARGET:-prod}" == "local" ]]; then
    export QUANTDB_HOST="${LOCAL_DB_HOST:-127.0.0.1}"
    export QUANTDB_PORT="${LOCAL_DB_PORT:-5432}"
    export QUANTDB_USERNAME="${LOCAL_DB_USER:-quant_admin}"
    export QUANTDB_PASSWORD="${LOCAL_DB_PASSWORD:-LetsGetRich888}"
    SSLMODE=disable
  else
    : "${QUANTDB_HOST:?QUANTDB_HOST required (or set DB_TARGET=local)}"
    QUANTDB_PORT="${QUANTDB_PORT:-5433}"
    SSLMODE=require
  fi

  export LIQUIBASE_COMMAND_URL="jdbc:postgresql://${QUANTDB_HOST}:${QUANTDB_PORT}/quantdb?sslmode=${SSLMODE}"
  export LIQUIBASE_COMMAND_USERNAME="${LIQUIBASE_COMMAND_USERNAME:-${QUANTDB_USERNAME:?QUANTDB_USERNAME required}}"
  export LIQUIBASE_COMMAND_PASSWORD="${LIQUIBASE_COMMAND_PASSWORD:-${QUANTDB_PASSWORD:?QUANTDB_PASSWORD required}}"
}

run_update() {
  local dir="$1"
  local label="$2"
  log "── ${label} ──"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties update
  )
}

main() {
  ensure_prereqs
  load_env

  log "Target: ${LIQUIBASE_COMMAND_URL} (user=${LIQUIBASE_COMMAND_USERNAME})"

  # Phase 0 — schemas + extensions (public.databasechangelog)
  (
    cd "${LB_ROOT}"
    liquibase --defaults-file=liquibase.properties update
  )

  # Schema DDL/procs (core_admin first pass — grants changeset may run before BT/INST exist)
  run_update core_admin "CORE_ADMIN (tables + procedures)"
  run_update refdata "REFDATA"
  run_update bt "BT"
  run_update trade "TRADE"
  run_update inst "INST"

  # Second pass — GRANTS.sql has runOnChange=true; picks up objects created above
  run_update core_admin "CORE_ADMIN (grants refresh)"

  log "Done — all pending release migrations applied"
}

main "$@"
