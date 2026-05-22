#!/usr/bin/env bash
# Free Docker disk on EC2 after "no space left on device" deploy failures.
#
# Run on the instance (SSM session or):
#   aws ssm send-command --instance-ids <id> --document-name AWS-RunShellScript \
#     --parameters 'commands=["bash /opt/quant/aws/scripts/ec2-docker-recover.sh"]'
set -euo pipefail

log() { echo "[ec2-docker-recover] $*"; }

log "Disk before cleanup:"
df -h / || true
docker system df 2>/dev/null || true

log "Pruning build cache and unused images (keeps running containers)..."
docker builder prune -af 2>/dev/null || true
docker image prune -af 2>/dev/null || true
docker container prune -f 2>/dev/null || true

log "Disk after cleanup:"
df -h / || true
docker system df 2>/dev/null || true

log "Done — re-run deploy or: docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && up -d --no-build"
