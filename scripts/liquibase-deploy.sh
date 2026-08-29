#!/usr/bin/env bash
# Apply pending Liquibase migrations (prod deploy or local).
#
# Usage:
#   ./scripts/liquibase-deploy.sh                   # prod — Aurora via SSM tunnel
#   DB_TARGET=local ./scripts/liquibase-deploy.sh   # local — laptop Postgres
#   APP_ENV=prod USE_SSM=1 ./scripts/liquibase-deploy.sh   # EC2: load /quant/prod/* from SSM
#
# LIQUIBASE_CONTEXTS restricts the run to changesets carrying one of the listed
# contexts. Unset (the default) applies every pending changeset, which is what
# manual runs want. The deploy workflow sets it to prod-deploy so only changesets
# explicitly marked for automatic release are applied.
#
# Where each target points is declared in config/db-targets.json, not here.
#
# An explicit DB_TARGET is authoritative: if LIQUIBASE_COMMAND_URL is also set and
# points somewhere else, the run aborts instead of silently following the URL. To
# aim at a database the config does not describe, set the URL and leave DB_TARGET
# unset.
#
# Order: master (schemas) → per-schema DDL/procs → core_admin grants refresh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/db-target.sh
source "${ROOT_DIR}/scripts/lib/db-target.sh"
LB_ROOT="${ROOT_DIR}/db/liquidbase"
APP_ENV="${APP_ENV:-prod}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
LB_ARGS=()
[[ -n "${LIQUIBASE_CONTEXTS:-}" ]] && LB_ARGS+=("--context-filter=${LIQUIBASE_CONTEXTS}")

log() { echo "[liquibase-deploy] $*"; }
die() { echo "[liquibase-deploy] ERROR: $*" >&2; exit 1; }

ensure_prereqs() {
  log "Checking Java + Liquibase (Liquibase requires Java 11+)"
  bash "${ROOT_DIR}/aws/scripts/install-liquibase.sh"
}

load_env() {
  # Preserve caller overrides set before this script sources .env.
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

  # config/db-targets.json decides where DB_TARGET points, for both ends.
  db_target_env || die "could not resolve DB_TARGET"
  log "Target ${DB_TARGET} — ${DB_HOST}:${DB_PORT}/${DB_NAME} (sslmode=${DB_SSLMODE})"

  local resolved_url
  resolved_url="$(db_target_jdbc_url)"

  # A stale LIQUIBASE_COMMAND_URL must never quietly outrank the target the
  # caller named. A leftover prod tunnel URL exported in a shell once turned
  # DB_TARGET=local into a run against production, and only a closed tunnel
  # stopped it. So an explicit DB_TARGET wins, and a URL that disagrees with it
  # is a conflict to report rather than a preference to honour. The URL is still
  # an escape hatch on its own — set it and leave DB_TARGET unset.
  if [[ -n "${_db_target_override}" ]]; then
    if [[ -n "${_lb_url_override}" && "${_lb_url_override}" != "${resolved_url}" ]]; then
      die "LIQUIBASE_COMMAND_URL=${_lb_url_override} contradicts DB_TARGET=${DB_TARGET} (${resolved_url}). Unset LIQUIBASE_COMMAND_URL, or leave DB_TARGET unset to use the URL as-is."
    fi
    export LIQUIBASE_COMMAND_URL="${resolved_url}"
  else
    export LIQUIBASE_COMMAND_URL="${_lb_url_override:-${resolved_url}}"
    if [[ "${LIQUIBASE_COMMAND_URL}" != "${resolved_url}" ]]; then
      log "NOTE: LIQUIBASE_COMMAND_URL overrides target ${DB_TARGET} (${resolved_url})"
    fi
  fi
  export LIQUIBASE_COMMAND_USERNAME="${LIQUIBASE_COMMAND_USERNAME:-${DB_USER:?DB_USER required}}"
  export LIQUIBASE_COMMAND_PASSWORD="${LIQUIBASE_COMMAND_PASSWORD:-${DB_PASSWORD:?DB_PASSWORD required — set QUANTDB_PASSWORD}}"
}

APPLIED_LABELS=()
APPLIED_COUNTS=()

run_update() {
  local dir="$1"
  local label="$2"
  local out count
  out="$(mktemp)"
  log "── ${label} ──"
  (
    cd "${LB_ROOT}/${dir}"
    liquibase --defaults-file=liquibase.properties update ${LB_ARGS[@]+"${LB_ARGS[@]}"}
  ) | tee "${out}"
  # Liquibase reports what it applied in an UPDATE SUMMARY block. No block at
  # all means it had nothing pending to report.
  count="$(awk '/^Run:/ {print $2; exit}' "${out}")"
  APPLIED_LABELS+=("${label}")
  APPLIED_COUNTS+=("${count:-0}")
  rm -f "${out}"
}

print_summary() {
  local total=0 i line
  local -a lines=("── MIGRATION SUMMARY (contexts: ${LIQUIBASE_CONTEXTS:-<all>}) ──")
  for i in "${!APPLIED_LABELS[@]}"; do
    lines+=("$(printf '  %-34s %3s applied' "${APPLIED_LABELS[$i]}" "${APPLIED_COUNTS[$i]}")")
    total=$((total + APPLIED_COUNTS[i]))
  done
  lines+=("$(printf '  %-34s %3d applied' 'TOTAL' "${total}")")
  printf '%s\n' "${lines[@]}" | while IFS= read -r line; do log "${line}"; done

  # The deploy workflow only prints the tail of this script's output, and the
  # container startup that follows would push the migration off the top. It
  # re-reads this file at the very end so the result stays visible.
  if [[ -n "${MIGRATION_SUMMARY_FILE:-}" ]]; then
    printf '%s\n' "${lines[@]}" > "${MIGRATION_SUMMARY_FILE}"
  fi
}

main() {
  ensure_prereqs
  load_env

  log "Target: ${LIQUIBASE_COMMAND_URL} (user=${LIQUIBASE_COMMAND_USERNAME})"
  log "Contexts: ${LIQUIBASE_CONTEXTS:-<all>}"

  # Phase 0 — schemas + extensions (public.databasechangelog)
  run_update "." "MASTER (schemas)"

  # Schema DDL/procs (core_admin first pass — grants changeset may run before BT/INST exist)
  run_update core_admin "CORE_ADMIN (tables + procedures)"
  run_update refdata "REFDATA"
  run_update bt "BT"
  run_update trade "TRADE"
  run_update market_data "MARKET_DATA"
  run_update inst "INST"

  # Second pass — GRANTS.sql has runOnChange=true; picks up objects created above
  run_update core_admin "CORE_ADMIN (grants refresh)"

  print_summary
  log "Done — all pending release migrations applied"
}

main "$@"
