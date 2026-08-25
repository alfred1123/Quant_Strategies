# Resolve DB_TARGET → connection settings, from config/db-targets.json.
#
# That file is the single source of truth for what 'local' and 'prod' mean.
# quant/shared/config.py reads it for Python entry points; this reads it for
# appctl.sh, dbctl.sh and liquibase-deploy.sh, so the two cannot drift.
#
#   DB_TARGET=prod   → Aurora (laptop: SSM tunnel on 127.0.0.1:5433;
#                              EC2: cluster endpoint on 5432 via SSM)
#   DB_TARGET=local  → laptop Postgres 17 on 127.0.0.1:5432
#
# Three resolvers, because the callers want different things: dump/restore
# needs *both* ends at once (it copies prod into local), while the app and
# Liquibase want whichever end DB_TARGET names.
#
#   db_local_env   → DB_LOCAL_*
#   db_prod_env    → DB_PROD_*
#   db_target_env  → DB_* for the selected target
#
# shellcheck shell=bash

_DB_TARGET_LIB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB_TARGETS_JSON="${DB_TARGETS_JSON:-$_DB_TARGET_LIB_ROOT/config/db-targets.json}"

# Emit `KEY=value` lines for one target, applying the same env-var precedence
# the Python side uses. Kept in python3 rather than jq: jq is not a documented
# prerequisite anywhere else in this repo, python3 is.
_db_emit() {
  local target="$1" prefix="$2"
  DB_TARGETS_JSON="$DB_TARGETS_JSON" python3 -c '
import json, os, sys, shlex

target, prefix = sys.argv[1], sys.argv[2]
with open(os.environ["DB_TARGETS_JSON"], encoding="utf-8") as fh:
    spec = json.load(fh)

try:
    entry = spec["targets"][target]
except KeyError:
    sys.exit(f"unknown DB target {target!r}")

out = {"SSLMODE": entry["sslmode"]}
for field, rule in entry["fields"].items():
    value = next((os.environ[v] for v in rule["env"] if os.environ.get(v)), rule["default"])
    out[field.upper()] = "" if value is None else str(value)

for key, value in out.items():
    print(f"{prefix}{key}={shlex.quote(value)}")
' "$target" "$prefix"
}

db_local_env() {
  local assignments
  assignments="$(_db_emit local DB_LOCAL_)" || return 1
  eval "$assignments"
  export DB_LOCAL_HOST DB_LOCAL_PORT DB_LOCAL_DBNAME DB_LOCAL_USER \
         DB_LOCAL_PASSWORD DB_LOCAL_SSLMODE
  # Alias: callers predate the json field name.
  DB_LOCAL_NAME="$DB_LOCAL_DBNAME"; export DB_LOCAL_NAME
}

db_prod_env() {
  local assignments
  assignments="$(_db_emit prod DB_PROD_)" || return 1
  eval "$assignments"
  export DB_PROD_HOST DB_PROD_PORT DB_PROD_DBNAME DB_PROD_USER \
         DB_PROD_PASSWORD DB_PROD_SSLMODE
  DB_PROD_NAME="$DB_PROD_DBNAME"; export DB_PROD_NAME
}

# One field's declared default, ignoring the environment. For callers that
# know which end they want and must not inherit an override meant for another
# (dbctl.sh always tunnels to prod, whatever QUANTDB_PORT the app is using).
db_field() {
  DB_TARGETS_JSON="$DB_TARGETS_JSON" python3 -c '
import json, os, sys
target, field = sys.argv[1], sys.argv[2]
with open(os.environ["DB_TARGETS_JSON"], encoding="utf-8") as fh:
    spec = json.load(fh)
value = spec["targets"][target]["fields"][field]["default"]
print("" if value is None else value)
' "$1" "$2"
}

db_default_target() {
  DB_TARGETS_JSON="$DB_TARGETS_JSON" python3 -c '
import json, os
with open(os.environ["DB_TARGETS_JSON"], encoding="utf-8") as fh:
    print(json.load(fh)["default_target"])
'
}

db_target_env() {
  local default_target
  default_target="$(db_default_target)" || return 1
  DB_TARGET="$(printf '%s' "${DB_TARGET:-$default_target}" | tr '[:upper:]' '[:lower:]')"

  local assignments
  assignments="$(_db_emit "$DB_TARGET" DB_)" || {
    echo "ERROR: DB_TARGET must be 'local' or 'prod', got '${DB_TARGET}'" >&2
    return 1
  }
  eval "$assignments"
  DB_NAME="$DB_DBNAME"
  export DB_TARGET DB_HOST DB_PORT DB_DBNAME DB_NAME DB_USER DB_PASSWORD DB_SSLMODE

  if [ "$DB_TARGET" = prod ]; then
    db_assert_not_local "$DB_HOST" "$DB_PORT" || return 1
  fi
}

# Refuse a host:port that claims to be prod but is the local database —
# reachable through a stale QUANTDB_PORT in .env, and the failure it prevents
# is the worst kind: writes labelled prod landing in the laptop dump, or a
# "prod check" reporting local rows. Loopback *and* the local port together can
# only be the laptop, so this never fires on EC2, where prod is the Aurora
# endpoint rather than loopback. Mirrors _reject_local_masquerading_as_prod()
# in quant/shared/config.py.
db_assert_not_local() {
  local host="$1" port="$2"
  db_local_env || return 1
  case "$host" in
    127.0.0.1|localhost|::1) ;;
    *) return 0 ;;
  esac
  [ "$port" = "$DB_LOCAL_PORT" ] || return 0
  cat >&2 <<EOF
ERROR: a prod connection resolved to ${host}:${port}, which is the local
       database (port ${DB_LOCAL_PORT}). Prod on a laptop goes through the SSM
       tunnel — see config/db-targets.json. Unset QUANTDB_PORT in .env, or
       select the local target explicitly if that is what you meant.
EOF
  return 1
}

# libpq DSN for the selected target.
db_target_conninfo() {
  db_target_env || return 1
  printf 'host=%s port=%s dbname=%s user=%s password=%s sslmode=%s' \
    "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASSWORD" "$DB_SSLMODE"
}

# Liquibase wants a JDBC URL rather than a DSN.
db_target_jdbc_url() {
  db_target_env || return 1
  printf 'jdbc:postgresql://%s:%s/%s?sslmode=%s' \
    "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_SSLMODE"
}
