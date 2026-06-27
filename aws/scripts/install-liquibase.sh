#!/usr/bin/env bash
# Install and verify Java + Liquibase + PostgreSQL JDBC (idempotent).
#
# Liquibase is a Java CLI — both must be present before liquibase-deploy.sh runs.
# Usage:
#   sudo bash aws/scripts/install-liquibase.sh          # install if missing
#   bash aws/scripts/install-liquibase.sh --check-only    # verify; exit 1 if broken
set -euo pipefail

LIQUIBASE_VERSION="${LIQUIBASE_VERSION:-4.29.2}"
LIQUIBASE_HOME="${LIQUIBASE_HOME:-/opt/liquibase}"
JDBC_VERSION="${JDBC_VERSION:-42.7.5}"
CHECK_ONLY=false
[[ "${1:-}" == "--check-only" ]] && CHECK_ONLY=true

log() { echo "[install-liquibase] $*"; }
die() { echo "[install-liquibase] ERROR: $*" >&2; exit 1; }

java_major_version() {
  # Parses `java -version` (stderr) — works for OpenJDK / Corretto.
  java -version 2>&1 | awk -F '[".-]' '/version/ {
    if ($2 == 1) print $3; else print $2; exit
  }'
}

ensure_java() {
  if command -v java >/dev/null 2>&1; then
    local major
    major="$(java_major_version)" || die "java -version failed"
    if [[ -z "$major" || "$major" -lt 11 ]]; then
      die "Java 11+ required for Liquibase (found major version: ${major:-unknown})"
    fi
    log "Java OK (major=${major}): $(java -version 2>&1 | head -1)"
    return 0
  fi

  [[ "$CHECK_ONLY" == true ]] && die "java not found (Liquibase requires Java 11+)"

  log "Java not found — installing OpenJDK 17"
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y java-17-amazon-corretto-headless
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y openjdk-17-jre-headless
  else
    die "Java 17+ required — install manually (dnf/apt not available)"
  fi

  command -v java >/dev/null || die "Java install completed but java not on PATH"
  ensure_java
}

ensure_jdbc_driver() {
  local jar="${LIQUIBASE_HOME}/lib/postgresql-${JDBC_VERSION}.jar"
  if [[ -f "$jar" ]]; then
    return 0
  fi
  # Liquibase tarball ships a postgresql*.jar — use it instead of duplicating drivers.
  local bundled
  bundled=$(find "${LIQUIBASE_HOME}/lib" -maxdepth 1 -name 'postgresql*.jar' -print -quit 2>/dev/null || true)
  if [[ -n "$bundled" ]]; then
    log "JDBC OK (bundled): $(basename "$bundled")"
    return 0
  fi
  [[ "$CHECK_ONLY" == true ]] && die "PostgreSQL JDBC driver missing under ${LIQUIBASE_HOME}/lib"
  mkdir -p "${LIQUIBASE_HOME}/lib"
  log "Downloading PostgreSQL JDBC ${JDBC_VERSION}"
  curl -fsSL \
    "https://jdbc.postgresql.org/download/postgresql-${JDBC_VERSION}.jar" \
    -o "$jar"
}

install_liquibase() {
  if [[ -x "${LIQUIBASE_HOME}/liquibase" ]]; then
    return 0
  fi
  [[ "$CHECK_ONLY" == true ]] && die "Liquibase not installed at ${LIQUIBASE_HOME}/liquibase"

  log "Installing Liquibase ${LIQUIBASE_VERSION} -> ${LIQUIBASE_HOME}"
  mkdir -p "${LIQUIBASE_HOME}"
  # Stream extract — no mktemp/rm; nothing shared under /tmp to track or clean up.
  curl -fsSL \
    "https://github.com/liquibase/liquibase/releases/download/v${LIQUIBASE_VERSION}/liquibase-${LIQUIBASE_VERSION}.tar.gz" \
    | tar -xzf - -C "${LIQUIBASE_HOME}"

  chmod +x "${LIQUIBASE_HOME}/liquibase"
  ln -sf "${LIQUIBASE_HOME}/liquibase" /usr/local/bin/liquibase
}

verify_liquibase_cli() {
  command -v liquibase >/dev/null || die "liquibase not on PATH"
  local out
  out="$(liquibase --version 2>&1)" || die "liquibase --version failed (is Java working?)"
  log "Liquibase OK: $(echo "$out" | head -1)"
}

main() {
  ensure_java
  install_liquibase
  ensure_jdbc_driver

  if [[ ! -x "${LIQUIBASE_HOME}/liquibase" ]] && [[ "$CHECK_ONLY" != true ]]; then
    ln -sf "${LIQUIBASE_HOME}/liquibase" /usr/local/bin/liquibase 2>/dev/null || true
  fi

  verify_liquibase_cli
  log "Prerequisites ready (Java + Liquibase + JDBC)"
}

main "$@"
