#!/usr/bin/env bash
# Capture EC2 / host capacity for Phase 0.2 planning.
#
# Run on the production box (SSH or SSM session as ec2-user):
#   bash aws/scripts/capacity_snapshot.sh
#
# Or from repo root on EC2 (/opt/quant):
#   cd /opt/quant && bash aws/scripts/capacity_snapshot.sh
#
# Remotely via SSM (replace instance id / profile / region):
#   aws ssm send-command --instance-ids i-026d3c6d323144663 \
#     --document-name AWS-RunShellScript \
#     --parameters 'commands=["cd /opt/quant && bash aws/scripts/capacity_snapshot.sh"]' \
#     --region ap-southeast-1
#
# Paste output into docs/archive/phase-0/phase-0.2-capacity.md §Live capture.

set -euo pipefail

echo "=== CAPACITY SNAPSHOT $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo

echo "=== HOST ==="
echo "hostname: $(hostname)"
echo "arch: $(uname -m)"
echo "cpus: $(nproc 2>/dev/null || echo '?')"
free -h
echo "load: $(uptime)"
echo

echo "=== DISK ==="
df -h / /var/lib/docker 2>/dev/null || df -h /
echo

echo "=== DOCKER COMPOSE (if /opt/quant) ==="
if [ -d /opt/quant ]; then
  (cd /opt/quant && docker compose ps 2>/dev/null) || true
else
  docker compose ps 2>/dev/null || docker ps --format 'table {{.Names}}\t{{.Status}}'
fi
echo

echo "=== DOCKER STATS (point-in-time) ==="
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' 2>/dev/null \
  || echo "(docker stats unavailable)"
echo

echo "=== NON-DOCKER PROCESSES (bybit / trade / uvicorn) ==="
ps aux | egrep -i 'bybit|trade|uvicorn|worker_loop|python.*worker' | grep -v grep || echo "none matched"
echo

echo "=== CGROUP MEMORY SUMMARY ==="
if [ -f /sys/fs/cgroup/memory.current ]; then
  echo "cgroup v2 — root memory.current: $(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo n/a)"
fi
echo "done."
