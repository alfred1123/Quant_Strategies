#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/log/run"
LOG_DIR="$ROOT_DIR/log"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
TUNNEL_PID_FILE="$RUN_DIR/tunnel.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"
TUNNEL_LOG_FILE="$LOG_DIR/tunnel.log"
BACKEND_PORT=8000
DEV_FRONTEND_PORT=5173
DB_PORT=5433

# AWS SSM port-forward target (override via .env if needed).
SSM_TARGET_INSTANCE="${SSM_TARGET_INSTANCE:-i-096f85bf84852cce3}"
SSM_RDS_HOST="${SSM_RDS_HOST:-quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com}"
SSM_REMOTE_PORT="${SSM_REMOTE_PORT:-5432}"
SSM_AWS_PROFILE="${SSM_AWS_PROFILE:-alfcheun}"

MODE="${1:-}"
ACTION="${2:-}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/appctl <dev|prod> <start|stop|kill|restart|status>
  ./scripts/appctl dev tunnel <start|stop|kill|restart|status>

Examples:
  ./scripts/appctl dev tunnel start  # start AWS SSM port-forward to RDS (5433)
  ./scripts/appctl dev start         # local dev (uvicorn + Vite). Refuses to
                                     # start if the SSM tunnel / DB is down.
  ./scripts/appctl dev kill
  ./scripts/appctl prod start        # Docker Compose (redis + coordinator + api + nginx)
  ./scripts/appctl prod status

Self-test (after prod start — from project root, .env loaded for compose):
  curl -sS "http://127.0.0.1:8000/health/ready"
  curl -sS "http://127.0.0.1:${COORDINATOR_PORT:-3001}/health"
  curl -sS "http://127.0.0.1:${COORDINATOR_PORT:-3001}/api/v1/jobs"

Notes:
  - dev mode runs FastAPI with --reload and Vite dev server (no Docker).
    Redis is optional locally — REFDATA endpoints will 503 until coordinator
    publishes, but auth/login work fine without it.
  - 'dev tunnel' manages a single canonical AWS SSM port-forward to RDS so you
    only ever have one reconnect loop running (avoids races on port 5433).
  - prod mode loads ./.env when present (set -a) so docker compose can substitute
    QUANTDB_URL, JWT_SECRET, REDIS_URL, COORDINATOR_PORT, etc. The coordinator
    container needs QUANTDB_URL + JWT_SECRET; FastAPI loads SSM inside the api
    container when USE_SSM=1.
  - prod compose matches deploy: docker-compose.yml + docker-compose.prod.yml,
    up -d --build --remove-orphans.
  - PIDs are stored under log/run/ and logs under log/.
EOF
}

if [[ "$MODE" != "dev" && "$MODE" != "prod" ]]; then
  usage
  exit 1
fi

if [[ "$ACTION" != "start" && "$ACTION" != "stop" && "$ACTION" != "kill" && "$ACTION" != "restart" && "$ACTION" != "status" && "$ACTION" != "tunnel" ]]; then
  usage
  exit 1
fi

cd "$ROOT_DIR"

# ── Prod mode delegates to Docker Compose ─────────────────────────────
if [[ "$MODE" == "prod" ]]; then
  COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
  # Export vars from ./.env so ${QUANTDB_URL}, ${JWT_SECRET}, … interpolate in YAML
  # (matches what you set manually on EC2 before `docker compose up`).
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT_DIR/.env"
    set +a
    echo "Loaded $ROOT_DIR/.env for compose variable substitution."
  else
    echo "No .env at repo root — compose will use only exported shell env vars." >&2
  fi

  _coord_port="${COORDINATOR_PORT:-3001}"
  _preflight_coordinator() {
    if [[ -z "${QUANTDB_URL:-}" || -z "${JWT_SECRET:-}" ]]; then
      echo "" >&2
      echo "WARN: QUANTDB_URL and/or JWT_SECRET unset — coordinator container will fail." >&2
      echo "      Set them in .env (or export) for local prod stack tests. FastAPI may still start." >&2
      echo "" >&2
    fi
  }

  case "$ACTION" in
    start)
      _preflight_coordinator
      echo "Starting production containers..."
      docker compose $COMPOSE_FILES up -d --build --remove-orphans
      echo ""
      echo "Mode: prod (Docker Compose)"
      echo "Nginx → api:  http://127.0.0.1/ (port 80)  |  api direct: http://127.0.0.1:8000"
      echo "Coordinator:  http://127.0.0.1:${_coord_port}"
      echo "Site (TLS):   https://${DOMAIN:-<set DOMAIN for certbot profile>}"
      echo "Logs:         docker compose $COMPOSE_FILES logs -f"
      echo ""
      echo "Smoke (optional):"
      echo "  curl -sS \"http://127.0.0.1:8000/health/ready\""
      echo "  curl -sS \"http://127.0.0.1:${_coord_port}/health\""
      echo "  curl -sS \"http://127.0.0.1:${_coord_port}/api/v1/jobs\""
      ;;
    stop)
      docker compose $COMPOSE_FILES down
      echo "Stopped production containers."
      ;;
    kill)
      docker compose $COMPOSE_FILES down --remove-orphans
      echo "Killed production containers."
      ;;
    restart)
      _preflight_coordinator
      docker compose $COMPOSE_FILES down
      docker compose $COMPOSE_FILES up -d --build --remove-orphans
      echo "Restarted production containers."
      ;;
    status)
      echo "Mode: prod (Docker Compose)"
      docker compose $COMPOSE_FILES ps
      ;;
  esac
  exit 0
fi

# ── Dev mode runs bare processes ──────────────────────────────────────
mkdir -p "$RUN_DIR" "$LOG_DIR"

if [[ ! -f "$ROOT_DIR/env/bin/activate" ]]; then
  echo "Missing virtualenv at env/. Run ./setup.sh first." >&2
  exit 1
fi

source "$ROOT_DIR/env/bin/activate"

backend_command() {
  # Scope --reload to source dirs only. Watching the repo root made WatchFiles
  # restart the worker every time backend.log / tunnel.log / *.pid changed,
  # which prevented the API from ever finishing startup.
  # --host 0.0.0.0: WSL2 (mirrored networking) does not always route 127.0.0.1
  # connections back to a process that bound only to loopback. Binding to all
  # interfaces makes the API reachable from inside WSL, from Windows, and via
  # the Vite proxy regardless of network mode.
  printf '%s' "cd '$ROOT_DIR' && source '$ROOT_DIR/env/bin/activate' && uvicorn api.main:app --reload --reload-dir '$ROOT_DIR/api' --reload-dir '$ROOT_DIR/src' --host 0.0.0.0 --port 8000"
}

frontend_command() {
  printf '%s' "cd '$ROOT_DIR/frontend' && npm run dev -- --host 0.0.0.0"
}

frontend_port() {
  printf '%s' "$DEV_FRONTEND_PORT"
}

tunnel_command() {
  # Single canonical reconnect loop. Logs each cycle to $TUNNEL_LOG_FILE.
  local params
  params=$(printf '{"host":["%s"],"portNumber":["%s"],"localPortNumber":["%s"]}' \
    "$SSM_RDS_HOST" "$SSM_REMOTE_PORT" "$DB_PORT")
  printf '%s' "while true; do echo \"[\$(date '+%Y-%m-%d %H:%M:%S')] starting SSM port-forward...\"; aws ssm start-session --target '$SSM_TARGET_INSTANCE' --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '$params' --profile '$SSM_AWS_PROFILE'; echo \"[\$(date '+%Y-%m-%d %H:%M:%S')] SSM session ended (exit \$?). Reconnecting in 5s...\"; sleep 5; done"
}

db_reachable() {
  # Real TCP handshake check (don't keep the socket open — SSM port-forward
  # would tunnel the empty connection through to RDS and stall).
  python3 - <<PY 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(("127.0.0.1", $DB_PORT))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
}

pid_is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pids_from_port() {
  # All PIDs (parent + children) listening on the port. One per line.
  local port="$1"
  lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file"
  fi
}

# Send a signal to the entire process group of $pid (uvicorn --reload spawns
# a child worker; killing only the parent leaves the worker holding the port).
kill_pgid() {
  local sig="$1"
  local pid="$2"
  local pgid
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')" || true
  if [[ -n "$pgid" ]]; then
    kill "-$sig" -- "-$pgid" 2>/dev/null || true
  else
    kill "-$sig" "$pid" 2>/dev/null || true
  fi
}

# Kill anything still bound to $port (orphaned reload workers etc.).
sweep_port() {
  local sig="$1"
  local port="$2"
  local p
  while read -r p; do
    [[ -z "$p" ]] && continue
    kill "-$sig" "$p" 2>/dev/null || true
  done < <(pids_from_port "$port")
}

port_is_free() {
  local port="$1"
  [[ -z "$(pids_from_port "$port")" ]]
}

start_service() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  local command="$4"
  local port="$5"
  local existing_pid existing_port_pids

  existing_pid="$(read_pid "$pid_file")"
  existing_port_pids="$(pids_from_port "$port")"

  if pid_is_running "$existing_pid" || [[ -n "$existing_port_pids" ]]; then
    if [[ -n "$existing_port_pids" ]]; then
      # Reconcile pid file with whatever owns the port today.
      echo "$existing_port_pids" | head -n 1 >"$pid_file"
      echo "$name already running (pid(s) $(echo $existing_port_pids | tr '\n' ' '))"
    else
      echo "$name already running (pid $existing_pid)"
    fi
    return 0
  fi

  rm -f "$pid_file"
  # setsid -> new session/process group; the recorded PID == PGID, so we can
  # later kill -PGID and reap parent + all children (uvicorn reload worker, etc.).
  setsid nohup bash -lc "$command" >>"$log_file" 2>&1 < /dev/null &
  local started=$!
  echo "$started" >"$pid_file"
  echo "Started $name (pid $started)"
}

_terminate_service() {
  # $1 name, $2 pid_file, $3 port, $4 grace_seconds
  local name="$1" pid_file="$2" port="$3" grace="$4"
  local pid
  pid="$(read_pid "$pid_file")"

  local had_anything=0
  if pid_is_running "$pid"; then
    had_anything=1
    kill_pgid TERM "$pid"
  fi
  if [[ -n "$(pids_from_port "$port")" ]]; then
    had_anything=1
    sweep_port TERM "$port"
  fi

  if [[ "$had_anything" -eq 0 ]]; then
    rm -f "$pid_file"
    echo "$name not running"
    return 0
  fi

  local i
  for ((i = 0; i < grace; i++)); do
    if ! pid_is_running "$pid" && port_is_free "$port"; then
      rm -f "$pid_file"
      echo "Stopped $name"
      return 0
    fi
    sleep 1
  done

  # Escalate to SIGKILL on the process group and any port stragglers.
  if pid_is_running "$pid"; then
    kill_pgid KILL "$pid"
  fi
  sweep_port KILL "$port"
  sleep 1
  rm -f "$pid_file"
  if port_is_free "$port"; then
    echo "Force-stopped $name"
  else
    echo "WARN: $name port $port still bound after SIGKILL — check 'lsof -i tcp:$port'" >&2
  fi
}

stop_service() {
  _terminate_service "$1" "$2" "$3" 10
}

kill_service() {
  # 'kill' = no grace period: SIGKILL the group + sweep port immediately.
  local name="$1" pid_file="$2" port="$3"
  local pid
  pid="$(read_pid "$pid_file")"

  if ! pid_is_running "$pid" && port_is_free "$port"; then
    rm -f "$pid_file"
    echo "$name not running"
    return 0
  fi

  if pid_is_running "$pid"; then
    kill_pgid KILL "$pid"
  fi
  sweep_port KILL "$port"
  sleep 1
  rm -f "$pid_file"
  if port_is_free "$port"; then
    echo "Killed $name"
  else
    echo "WARN: $name port $port still bound — check 'lsof -i tcp:$port'" >&2
  fi
}

status_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local pid port_pids

  pid="$(read_pid "$pid_file")"
  port_pids="$(pids_from_port "$port")"
  if ! pid_is_running "$pid" && [[ -n "$port_pids" ]]; then
    pid="$(echo "$port_pids" | head -n 1)"
  fi
  if pid_is_running "$pid"; then
    echo "$pid" >"$pid_file"
    if [[ -n "$port_pids" ]]; then
      echo "$name: running (pid(s) $(echo $port_pids | tr '\n' ' '), port $port)"
    else
      echo "$name: running (pid $pid)"
    fi
  else
    echo "$name: stopped"
  fi
}

SELF_CMD="${APPCTL_ENTRYPOINT:-$(basename "$0")}" 

case "$ACTION" in
  tunnel)
    # Manage just the SSM port-forward.  Sub-command in $3 (default: start).
    SUB="${3:-start}"
    case "$SUB" in
      start)
        start_service "tunnel" "$TUNNEL_PID_FILE" "$TUNNEL_LOG_FILE" "$(tunnel_command)" "$DB_PORT"
        # Wait briefly for the tunnel to bind 5433.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
          db_reachable && { echo "DB reachable on 127.0.0.1:$DB_PORT"; exit 0; }
          sleep 1
        done
        echo "WARN: tunnel started but DB not reachable yet — check $TUNNEL_LOG_FILE" >&2
        ;;
      stop|kill)
        kill_service "tunnel" "$TUNNEL_PID_FILE" "$DB_PORT"
        ;;
      status)
        status_service "tunnel" "$TUNNEL_PID_FILE" "$DB_PORT"
        if db_reachable; then
          echo "DB: reachable on 127.0.0.1:$DB_PORT"
        else
          echo "DB: UNREACHABLE on 127.0.0.1:$DB_PORT"
        fi
        ;;
      restart)
        "$0" dev tunnel kill
        "$0" dev tunnel start
        ;;
      *) echo "Usage: $0 dev tunnel <start|stop|kill|restart|status>" >&2; exit 1 ;;
    esac
    exit 0
    ;;
  start)
    # Pre-flight: API lifespan blocks on DB; refuse to start if tunnel is dead.
    if ! db_reachable; then
      echo "DB on 127.0.0.1:$DB_PORT is NOT reachable." >&2
      echo "Start the SSM tunnel first:  ./scripts/appctl.sh dev tunnel start" >&2
      exit 2
    fi
    start_service "backend" "$BACKEND_PID_FILE" "$BACKEND_LOG_FILE" "$(backend_command)" "$BACKEND_PORT"
    start_service "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_LOG_FILE" "$(frontend_command)" "$(frontend_port)"
    echo "Mode: dev"
    echo "Backend:  http://127.0.0.1:8000"
    echo "Frontend: http://127.0.0.1:5173"
    ;;
  stop)
    stop_service "frontend" "$FRONTEND_PID_FILE" "$(frontend_port)"
    stop_service "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT"
    ;;
  kill)
    kill_service "frontend" "$FRONTEND_PID_FILE" "$(frontend_port)"
    kill_service "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT"
    ;;
  restart)
    "$0" "$MODE" stop
    "$0" "$MODE" start
    ;;
  status)
    echo "Mode: dev"
    echo "Command: ./scripts/$SELF_CMD dev <start|stop|kill|restart|status|tunnel>"
    status_service "tunnel"   "$TUNNEL_PID_FILE"   "$DB_PORT"
    status_service "backend"  "$BACKEND_PID_FILE"  "$BACKEND_PORT"
    status_service "frontend" "$FRONTEND_PID_FILE" "$(frontend_port)"
    if db_reachable; then
      echo "DB: reachable on 127.0.0.1:$DB_PORT"
    else
      echo "DB: UNREACHABLE on 127.0.0.1:$DB_PORT"
    fi
    echo "Backend log:  $BACKEND_LOG_FILE"
    echo "Frontend log: $FRONTEND_LOG_FILE"
    echo "Tunnel log:   $TUNNEL_LOG_FILE"
    ;;
esac