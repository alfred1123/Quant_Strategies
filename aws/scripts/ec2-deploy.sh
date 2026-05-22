#!/usr/bin/env bash
# Pull ECR images and start the prod stack on EC2 (no build on host).
#
# Usage (on instance):
#   cd /opt/quant && bash aws/scripts/ec2-deploy.sh
#   IMAGE_TAG=<git-sha> bash aws/scripts/ec2-deploy.sh
#
# SSM (safe — no fragile JSON escaping):
#   aws ssm send-command --instance-ids <id> --document-name AWS-RunShellScript \
#     --parameters file://aws/scripts/ssm-ec2-deploy.json
set -euo pipefail

ROOT="${DEPLOY_ROOT:-/opt/quant}"
REGION="${AWS_REGION:-ap-southeast-1}"
ECR_REGISTRY="${ECR_REGISTRY:-539163478329.dkr.ecr.ap-southeast-1.amazonaws.com}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

log() { echo "[ec2-deploy] $*"; }

ecr_tag_exists() {
  aws ecr describe-images \
    --repository-name "$1" \
    --image-ids "imageTag=$2" \
    --region "$REGION" >/dev/null 2>&1
}

resolve_tag() {
  local repo="$1"
  if ecr_tag_exists "$repo" "$IMAGE_TAG"; then
    echo "$IMAGE_TAG"
  elif ecr_tag_exists "$repo" latest; then
    log "$repo:$IMAGE_TAG missing — using latest"
    echo latest
  else
    log "ERROR: no $repo image for tag $IMAGE_TAG or latest"
    exit 1
  fi
}

main() {
  cd "$ROOT"

  log "Disk before deploy:"
  df -h / || true

  log "Prune unused Docker data (keep running containers)..."
  docker builder prune -af 2>/dev/null || true
  docker image prune -af 2>/dev/null || true

  APP_TAG="$(resolve_tag quant-app)"
  NGINX_TAG="$(resolve_tag quant-nginx)"
  export APP_IMAGE="${ECR_REGISTRY}/quant-app:${APP_TAG}"
  export NGINX_IMAGE="${ECR_REGISTRY}/quant-nginx:${NGINX_TAG}"
  log "APP_IMAGE=$APP_IMAGE"
  log "NGINX_IMAGE=$NGINX_IMAGE"

  aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"

  COMPOSE_PARALLEL_LIMIT=1 "${COMPOSE[@]}" pull
  "${COMPOSE[@]}" up -d --no-build --remove-orphans

  log "Waiting for API /health/ready..."
  for _ in $(seq 1 24); do
    if curl -sf http://127.0.0.1:8000/health/ready >/dev/null; then
      log "API ready"
      break
    fi
    sleep 5
  done

  curl -sf http://127.0.0.1:8000/health/ready >/dev/null && log "health check OK" \
    || log "WARN: API health check failed"

  "${COMPOSE[@]}" ps
  df -h /
}

main "$@"
