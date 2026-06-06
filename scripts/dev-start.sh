#!/usr/bin/env bash
# Quick dev startup — runs tunnel + backend + frontend in correct order.
# Usage: ./scripts/dev-start.sh

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Quant Strategies Dev Startup ==="

# 1. Kill any existing processes
echo "[1/5] Stopping existing processes..."
./scripts/appctl.sh dev kill 2>/dev/null || true
./scripts/appctl.sh dev tunnel kill 2>/dev/null || true
pkill -f "quant.queue.worker_loop" 2>/dev/null || true
sleep 2

# 2. Start SSM tunnel and wait for DB
echo "[2/5] Starting SSM tunnel to AWS RDS..."
./scripts/appctl.sh dev tunnel start
if ! ./scripts/appctl.sh dev tunnel start 2>&1 | grep -q "DB reachable"; then
    echo "ERROR: DB not reachable on port 5433. Check AWS SSO login." >&2
    echo "  Run: aws sso login --profile loki99-art" >&2
    exit 1
fi
sleep 2

# 3. Start backend + frontend
echo "[3/5] Starting backend and frontend..."
./scripts/appctl.sh dev start

# 4. Start worker (processes backtest queue)
echo "[4/5] Starting backtest worker..."
source "$ROOT_DIR/env/bin/activate"
pkill -f "quant.queue.worker_loop" 2>/dev/null || true
nohup python -m quant.queue.worker_loop >> "$ROOT_DIR/log/worker.log" 2>&1 &
WORKER_PID=$!
echo "$WORKER_PID" > "$ROOT_DIR/log/run/worker.pid"
echo "Started worker (pid $WORKER_PID)"

# 5. Wait and verify
echo "[5/5] Verifying backend health..."
sleep 5
for i in 1 2 3 4 5; do
    if curl -s --max-time 3 http://127.0.0.1:8000/health | grep -q '"status":"ok"'; then
        echo ""
        echo "=== SUCCESS ==="
        echo "Backend:  http://127.0.0.1:8000  ✓"
        echo "Frontend: http://127.0.0.1:5173  ✓"
        echo "Worker:   Running (processes backtest jobs)  ✓"
        echo "DB:       Connected via SSM tunnel (port 5433)  ✓"
        echo ""
        echo "Note: If dropdowns are empty, Redis is not running."
        echo "      Install: sudo apt install redis-server && sudo systemctl start redis-server"
        echo ""
        echo "Logs:"
        echo "  tail -f log/backend.log"
        echo "  tail -f log/worker.log"
        exit 0
    fi
    echo "  Waiting for backend... (attempt $i/5)"
    sleep 3
done

echo ""
echo "WARNING: Backend may not be fully ready. Check logs:"
echo "  tail -50 log/backend.log"
