#!/usr/bin/env bash
# Post-deploy smoke test for Cloudflare HTTPS (see docs/guides/https-cloudflare.md).
#
# Usage:
#   DOMAIN=algodaemon.com bash aws/scripts/verify-https.sh
#
# Optional env:
#   ORIGIN_IP=52.221.3.230   (default: resolve quant-eip tag via AWS CLI)
#   APP_ENV=prod             (SSM prefix /quant/<env>/)
#   AWS_REGION=ap-southeast-1
#   SKIP_EDGE=true           (origin TLS only — skip Cloudflare edge checks)
set -euo pipefail

DOMAIN="${DOMAIN:-}"
APP_ENV="${APP_ENV:-prod}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
SSM_PREFIX="/quant/${APP_ENV}"
SKIP_EDGE="${SKIP_EDGE:-false}"

log() { echo "[verify-https] $*"; }
die() { echo "[verify-https] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null || die "$1 is required"
}

resolve_origin_ip() {
  if [[ -n "${ORIGIN_IP:-}" ]]; then
    echo "$ORIGIN_IP"
    return
  fi
  local ip
  ip="$(aws ec2 describe-addresses \
    --region "$AWS_REGION" \
    --filters "Name=tag:Name,Values=quant-eip" \
    --query 'Addresses[0].PublicIp' \
    --output text 2>/dev/null || true)"
  [[ -n "$ip" && "$ip" != "None" ]] || die "Could not resolve origin EIP (set ORIGIN_IP or tag quant-eip)"
  echo "$ip"
}

check_ssm_tls() {
  local cert key
  cert="$(aws ssm get-parameter \
    --name "${SSM_PREFIX}/ORIGIN_TLS_CERT" \
    --region "$AWS_REGION" \
    --query Parameter.Value --output text 2>/dev/null || true)"
  key="$(aws ssm get-parameter \
    --name "${SSM_PREFIX}/ORIGIN_TLS_KEY" \
    --with-decryption \
    --region "$AWS_REGION" \
    --query Parameter.Value --output text 2>/dev/null || true)"
  if [[ -z "$cert" || "$cert" == "None" || -z "$key" || "$key" == "None" ]]; then
    die "SSM missing ${SSM_PREFIX}/ORIGIN_TLS_{CERT,KEY}"
  fi
  log "SSM origin TLS: OK"
}

curl_code() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time "$1" "${@:2}"
}

main() {
  require_cmd curl
  require_cmd aws
  [[ -n "$DOMAIN" ]] || die "DOMAIN is required"

  log "Domain=$DOMAIN env=$APP_ENV skip_edge=$SKIP_EDGE"
  check_ssm_tls

  local origin_ip
  origin_ip="$(resolve_origin_ip)"
  log "Origin IP=$origin_ip"

  local code
  code="$(curl_code 25 --resolve "${DOMAIN}:443:${origin_ip}" "https://${DOMAIN}/health")"
  [[ "$code" == "200" ]] || die "Origin HTTPS https://${DOMAIN}/health via ${origin_ip}:443 returned HTTP ${code} (expected 200)"
  log "Origin HTTPS: OK (HTTP 200)"

  if [[ "$SKIP_EDGE" == "true" ]]; then
    log "Skipping Cloudflare edge checks (SKIP_EDGE=true)"
    return 0
  fi

  code="$(curl_code 30 "https://${DOMAIN}/health")"
  [[ "$code" == "200" ]] || die "Edge HTTPS https://${DOMAIN}/health returned HTTP ${code} (expected 200)"
  log "Edge HTTPS: OK (HTTP 200)"

  code="$(curl_code 30 "http://${DOMAIN}/health")"
  [[ "$code" == "301" || "$code" == "308" ]] \
    || die "HTTP http://${DOMAIN}/health returned HTTP ${code} (expected 301 or 308 redirect)"
  log "HTTP → HTTPS redirect: OK (HTTP ${code})"
}

main "$@"
