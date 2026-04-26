#!/usr/bin/env bash
# Cursor sessionStart hook: launches an SSM port-forward (RDS quantdb 5432 -> local 5433)
# in the background, idempotently. Returns immediately so the agent session is not blocked.
#
# Mirrors the VS Code task "SSM Port Forward (quantdb:5433)" with runOn: folderOpen.

set -uo pipefail

# Drain stdin (hook input JSON) — we don't need it, but consume cleanly.
cat >/dev/null 2>&1 || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$LOG_DIR/ssm-port-forward.pid"
LOG_FILE="$LOG_DIR/ssm-port-forward.log"
LOOP_SCRIPT="$SCRIPT_DIR/ssm-port-forward-loop.sh"

mkdir -p "$LOG_DIR"

emit_ok() {
  # sessionStart accepts no special output fields; emit empty JSON to stay valid.
  printf '{}\n'
  exit 0
}

# Idempotency: if a previous loop is still alive, do nothing.
if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${existing_pid:-}" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    emit_ok
  fi
  rm -f "$PID_FILE"
fi

# Fail open if the AWS CLI isn't installed — don't block the session.
if ! command -v aws >/dev/null 2>&1; then
  echo "[$(date '+%F %T')] aws CLI not found on PATH; skipping SSM port-forward." >>"$LOG_FILE"
  emit_ok
fi

if [[ ! -x "$LOOP_SCRIPT" ]]; then
  chmod +x "$LOOP_SCRIPT" 2>/dev/null || true
fi

echo "[$(date '+%F %T')] sessionStart: launching SSM port-forward loop." >>"$LOG_FILE"

# Fully detach the reconnect loop from the agent process group.
# setsid + nohup ensures it survives Cursor session end.
if command -v setsid >/dev/null 2>&1; then
  setsid nohup bash "$LOOP_SCRIPT" >>"$LOG_FILE" 2>&1 </dev/null &
else
  nohup bash "$LOOP_SCRIPT" >>"$LOG_FILE" 2>&1 </dev/null &
fi
loop_pid=$!
disown "$loop_pid" 2>/dev/null || true
echo "$loop_pid" >"$PID_FILE"

emit_ok
