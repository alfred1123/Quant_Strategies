#!/usr/bin/env bash
# Dry-run Liquibase checks — validate changelogs and preview SQL without applying DDL.
#
# Usage:
#   ./scripts/liquibase-verify.sh              # validate + status + update-sql (needs DB)
#   ./scripts/liquibase-verify.sh --offline    # validate XML only (no database)
#   DB_TARGET=local ./scripts/liquibase-verify.sh
#
# Liquibase commands used (none of these run update):
#   validate    — parse changelogs; compares checksums (Liquibase 5 needs DB)
#   status      — SELECT databasechangelog; list pending changesets
#   update-sql  — print SQL that update WOULD run; does not execute it
#   --offline   — Python XML + include checks only (no DB)
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
SCHEMA_DIRS=(core_admin refdata bt trade inst)

ensure_prereqs() {
  bash "${ROOT_DIR}/aws/scripts/install-liquibase.sh"
}

load_env() {
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +a
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

  # Honour DB_TARGET=local (same as appctl.sh)
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

validate_changelog_xml() {
  log "XML well-formedness"
  python3 - "${LB_ROOT}" <<'PY'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(sys.argv[1])
for path in sorted(root.rglob("*.xml")):
    ET.parse(path)
print(f"OK: {len(list(root.rglob('*.xml')))} well-formed XML files")
PY
}

main_offline() {
  log "Offline mode — XML + include checks only (no database, no Liquibase validate)"
  validate_changelog_xml
  check_include_paths
  log "Offline checks passed"
}

check_include_paths() {
  log "Include path resolution"
  python3 - "${LB_ROOT}" <<'PY'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"lb": "http://www.liquibase.org/xml/ns/dbchangelog"}
root = Path(sys.argv[1])
errors = []
checked = 0
for changelog in sorted(root.rglob("*-changelog.xml")):
    tree = ET.parse(changelog)
    for node in tree.getroot().findall("lb:include", NS):
        rel = node.get("file")
        if not rel:
            continue
        checked += 1
        target = (changelog.parent / rel).resolve()
        if not target.is_file():
            errors.append(f"{changelog.relative_to(root)}: missing include {rel}")
if errors:
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1)
print(f"OK: {checked} active include(s), all resolve")
PY
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
