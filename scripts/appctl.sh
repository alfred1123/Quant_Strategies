#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/log/run"
LOG_DIR="$ROOT_DIR/log"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"
BACKEND_PORT=8000
DEV_FRONTEND_PORT=5173

MODE="${1:-}"
ACTION="${2:-}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/appctl <dev|prod> <start|stop|kill|restart|status>
  ./scripts/appctl.sh <dev|prod> <start|stop|kill|restart|status>

Examples:
  ./scripts/appctl dev start       # local dev (uvicorn + Vite)
  ./scripts/appctl dev kill
  ./scripts/appctl prod start      # Docker Compose (api + nginx + certbot)
  ./scripts/appctl prod status

Notes:
  - dev mode runs FastAPI with --reload and Vite dev server (no Docker).
  - prod mode uses Docker Compose (api + nginx + TLS).
    Requires: docker, DOMAIN env var for TLS.
  - PIDs are stored under log/run/ and logs under log/.
EOF
}

if [[ "$MODE" != "dev" && "$MODE" != "prod" ]]; then
  usage
  exit 1
fi

if [[ "$ACTION" != "start" && "$ACTION" != "stop" && "$ACTION" != "kill" && "$ACTION" != "restart" && "$ACTION" != "status" ]]; then
  usage
  exit 1
fi

cd "$ROOT_DIR"

# ── Prod mode delegates to Docker Compose ─────────────────────────────
if [[ "$MODE" == "prod" ]]; then
  COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"

  case "$ACTION" in
    start)
      echo "Starting production containers..."
      docker compose $COMPOSE_FILES up -d --build
      echo ""
      echo "Mode: prod (Docker Compose)"
      echo "Site: https://${DOMAIN:-<set DOMAIN>}"
      echo "Logs: docker compose $COMPOSE_FILES logs -f"
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
      docker compose $COMPOSE_FILES down
      docker compose $COMPOSE_FILES up -d --build
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
  printf '%s' "cd '$ROOT_DIR' && source '$ROOT_DIR/env/bin/activate' && uvicorn api.main:app --reload --port 8000"
}

frontend_command() {
  printf '%s' "cd '$ROOT_DIR/frontend' && npm run dev -- --host 0.0.0.0"
}

frontend_port() {
  printf '%s' "$DEV_FRONTEND_PORT"
}

pid_is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_from_port() {
  local port="$1"
  lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file"
  fi
}

start_service() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  local command="$4"
  local port="$5"
  local existing_pid

  existing_pid="$(read_pid "$pid_file")"
  if ! pid_is_running "$existing_pid"; then
    existing_pid="$(pid_from_port "$port")"
  fi
  if pid_is_running "$existing_pid"; then
    echo "$existing_pid" >"$pid_file"
    echo "$name already running (pid $existing_pid)"
    return 0
  fi

  rm -f "$pid_file"
  nohup bash -lc "$command" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "Started $name (pid $(cat "$pid_file"))"
}

stop_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local pid

  pid="$(read_pid "$pid_file")"
  if ! pid_is_running "$pid"; then
    pid="$(pid_from_port "$port")"
  fi
  if ! pid_is_running "$pid"; then
    rm -f "$pid_file"
    echo "$name not running"
    return 0
  fi

  kill "$pid" 2>/dev/null || true

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! pid_is_running "$pid"; then
      rm -f "$pid_file"
      echo "Stopped $name"
      return 0
    fi
    sleep 1
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "Force-stopped $name"
}

kill_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local pid

  pid="$(read_pid "$pid_file")"
  if ! pid_is_running "$pid"; then
    pid="$(pid_from_port "$port")"
  fi
  if ! pid_is_running "$pid"; then
    rm -f "$pid_file"
    echo "$name not running"
    return 0
  fi

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "Killed $name"
}

status_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local pid

  pid="$(read_pid "$pid_file")"
  if ! pid_is_running "$pid"; then
    pid="$(pid_from_port "$port")"
  fi
  if pid_is_running "$pid"; then
    echo "$pid" >"$pid_file"
    echo "$name: running (pid $pid)"
  else
    echo "$name: stopped"
  fi
}

SELF_CMD="${APPCTL_ENTRYPOINT:-$(basename "$0")}" 

case "$ACTION" in
  start)
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
    echo "Command: ./scripts/$SELF_CMD dev <start|stop|kill|restart|status>"
    status_service "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT"
    status_service "frontend" "$FRONTEND_PID_FILE" "$(frontend_port)"
    echo "Backend log:  $BACKEND_LOG_FILE"
    echo "Frontend log: $FRONTEND_LOG_FILE"
    ;;
esac