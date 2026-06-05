#!/usr/bin/env bash
# Step 1 — Cloudflare DNS for HTTPS via Origin Certificate (see docs/guides/https-cloudflare.md)
#
# Idempotent: ensure proxied A records for apex + www → EC2 Elastic IP.
#
# Usage:
#   export CLOUDFLARE_API_TOKEN=<token with Zone.DNS Edit on algodaemon.com>
#   bash aws/scripts/cloudflare-dns.sh
#
# Optional env:
#   DOMAIN=algodaemon.com          (default)
#   ORIGIN_IP=52.221.3.230         (default prod EIP)
#   CLOUDFLARE_PROXIED=true        (orange cloud; set false for DNS-only / grey)
#   AWS_PROFILE / AWS_REGION       (used when ORIGIN_IP unset — resolve from CFN/EIP)
#
# Verify only (no writes):
#   bash aws/scripts/cloudflare-dns.sh --check
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CF_API="https://api.cloudflare.com/client/v4"
DOMAIN="${DOMAIN:-algodaemon.com}"
PROXIED="${CLOUDFLARE_PROXIED:-true}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
CHECK_ONLY=false
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

log() { echo "[cloudflare-dns] $*"; }
die() { echo "[cloudflare-dns] ERROR: $*" >&2; exit 1; }

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
  if [[ -n "$ip" && "$ip" != "None" ]]; then
    echo "$ip"
    return
  fi
  ip="$(aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name quant-compute \
    --query 'Stacks[0].Outputs[?OutputKey==`PublicIp`].OutputValue' \
    --output text 2>/dev/null || true)"
  if [[ -n "$ip" && "$ip" != "None" ]]; then
    echo "$ip"
    return
  fi
  die "ORIGIN_IP unset and could not resolve EIP (set ORIGIN_IP or configure AWS CLI)"
}

cf_api() {
  local method="$1" path="$2"
  shift 2
  local body="${1:-}"
  local tmp http code
  tmp="$(mktemp)"
  if [[ -n "$body" ]]; then
    http="$(curl -sS -w '%{http_code}' -o "$tmp" -X "$method" "${CF_API}${path}" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H "Content-Type: application/json" \
      --data "$body")"
  else
    http="$(curl -sS -w '%{http_code}' -o "$tmp" -X "$method" "${CF_API}${path}" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H "Content-Type: application/json")"
  fi
  code="$http"
  if [[ "$code" -lt 200 || "$code" -ge 300 ]]; then
    echo "[cloudflare-dns] API ${method} ${path} → HTTP ${code}" >&2
    cat "$tmp" >&2
    rm -f "$tmp"
    exit 1
  fi
  cat "$tmp"
  rm -f "$tmp"
}

get_zone_id() {
  local resp
  resp="$(cf_api GET "/zones?name=${DOMAIN}&status=active")"
  echo "$resp" | jq -r '.result[0].id // empty'
}

record_needs_update() {
  local existing="$1" target_ip="$2" target_proxied="$3"
  local cur_ip cur_proxied
  cur_ip="$(echo "$existing" | jq -r '.content')"
  cur_proxied="$(echo "$existing" | jq -r '.proxied')"
  [[ "$cur_ip" != "$target_ip" || "$cur_proxied" != "$target_proxied" ]]
}

upsert_a_record() {
  local record_name="$1"   # apex FQDN or www FQDN
  local target_ip="$2"
  local target_proxied="$3"

  local resp existing id
  resp="$(cf_api GET "/zones/${ZONE_ID}/dns_records?type=A&name=${record_name}")"
  existing="$(echo "$resp" | jq -c '.result[0] // empty')"

  local payload
  payload="$(jq -n \
    --arg type "A" \
    --arg name "$record_name" \
    --arg content "$target_ip" \
    --argjson proxied "$target_proxied" \
    '{type: $type, name: $name, content: $content, proxied: $proxied, ttl: 1}')"

  if [[ -z "$existing" || "$existing" == "null" ]]; then
    if [[ "$CHECK_ONLY" == true ]]; then
      log "MISSING A ${record_name} → ${target_ip} (proxied=${target_proxied})"
      return 1
    fi
    cf_api POST "/zones/${ZONE_ID}/dns_records" "$payload" >/dev/null
    log "CREATED A ${record_name} → ${target_ip} (proxied=${target_proxied})"
    return 0
  fi

  id="$(echo "$existing" | jq -r '.id')"
  if record_needs_update "$existing" "$target_ip" "$target_proxied"; then
    if [[ "$CHECK_ONLY" == true ]]; then
      log "DRIFT  A ${record_name} (have $(echo "$existing" | jq -r '.content'), proxied=$(echo "$existing" | jq -r '.proxied'))"
      return 1
    fi
    cf_api PUT "/zones/${ZONE_ID}/dns_records/${id}" "$payload" >/dev/null
    log "UPDATED A ${record_name} → ${target_ip} (proxied=${target_proxied})"
    return 0
  fi

  log "OK     A ${record_name} → ${target_ip} (proxied=${target_proxied})"
  return 0
}

main() {
  require_cmd curl
  require_cmd jq

  [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]] || die "CLOUDFLARE_API_TOKEN is required (Zone.DNS Edit on ${DOMAIN})"

  ORIGIN_IP="$(resolve_origin_ip)"
  local proxied_json="false"
  [[ "$PROXIED" == "true" || "$PROXIED" == "1" ]] && proxied_json="true"

  log "Domain=${DOMAIN} origin=${ORIGIN_IP} proxied=${proxied_json} check_only=${CHECK_ONLY}"

  ZONE_ID="$(get_zone_id)"
  [[ -n "$ZONE_ID" ]] || die "No active Cloudflare zone for ${DOMAIN}"

  local apex="${DOMAIN}"
  local www="www.${DOMAIN}"
  local rc=0
  upsert_a_record "$apex" "$ORIGIN_IP" "$proxied_json" || rc=1
  upsert_a_record "$www" "$ORIGIN_IP" "$proxied_json" || rc=1

  if [[ "$CHECK_ONLY" == true ]]; then
    [[ "$rc" -eq 0 ]] && log "DNS check passed" || die "DNS check failed — run without --check to apply"
  else
    log "Done. Verify: dig ${DOMAIN} +short   (Cloudflare anycast IP when proxied)"
  fi
}

main "$@"
