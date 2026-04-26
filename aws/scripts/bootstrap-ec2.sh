#!/usr/bin/env bash
# One-time setup for a fresh EC2 instance after CloudFormation provisioning.
# Run as ec2-user: bash bootstrap-ec2.sh
set -euo pipefail

REPO_URL="git@github.com:alfred1123/Quant_Strategies.git"
APP_DIR="/opt/quant"

echo "=== Waiting for user-data to finish ==="
while [ ! -f /var/log/user-data-done.log ]; do
  echo "  user-data still running, waiting 10s..."
  sleep 10
done
echo "  user-data complete."

echo "=== Verifying Docker ==="
docker --version
docker compose version

echo "=== Cloning repo ==="
if [ -d "$APP_DIR/.git" ]; then
  echo "  repo already exists, pulling latest..."
  cd "$APP_DIR"
  git pull origin main
else
  sudo chown ec2-user:ec2-user "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

echo "=== Building and starting containers (HTTP-only) ==="
docker compose up -d --build

echo "=== Verifying ==="
sleep 10
docker compose ps
echo ""

API_STATUS=$(docker inspect --format='{{.State.Health.Status}}' quant-api 2>/dev/null || echo "unknown")
echo "API health: $API_STATUS"

echo ""
echo "=== Bootstrap complete ==="
echo "App running at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo ""
echo "To switch to HTTPS (requires domain):"
echo "  export DOMAIN=yourdomain.com"
echo "  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
