#!/usr/bin/env bash
# Step 2 (+ optional Step 3) — Cloudflare Origin Certificate
# See docs/guides/https-cloudflare.md
#
# Generates an RSA key locally, requests a signed Origin CA cert from Cloudflare,
# and writes origin.pem + origin-key.pem. Optionally uploads to SSM.
#
# Usage:
#   export CLOUDFLARE_API_TOKEN=<token with Zone SSL and Certificates Edit>
#   bash aws/scripts/cloudflare-origin-cert.sh
#   bash aws/scripts/cloudflare-origin-cert.sh --upload-ssm
#
# Auth (one of):
#   CLOUDFLARE_API_TOKEN  — Zone → SSL and Certificates → Edit (recommended)
#   CLOUDFLARE_ORIGIN_CA_KEY — legacy Origin CA key (v1.0-...)
#
# Optional env:
#   DOMAIN=algodaemon.com
#   ORIGIN_VALIDITY_DAYS=5475   (15 years — Cloudflare Origin CA max)
#   OUTPUT_DIR=./secrets
#   APP_ENV=prod                  (SSM prefix /quant/prod/)
#   AWS_REGION=ap-southeast-1
#
# Verify SSM only (no Cloudflare call):
#   bash aws/scripts/cloudflare-origin-cert.sh --check-ssm
set -euo pipefail

CF_API="https://api.cloudflare.com/client/v4"
DOMAIN="${DOMAIN:-algodaemon.com}"
WILDCARD="*.${DOMAIN}"
VALIDITY_DAYS="${ORIGIN_VALIDITY_DAYS:-5475}"
OUTPUT_DIR="${OUTPUT_DIR:-./secrets}"
APP_ENV="${APP_ENV:-prod}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
SSM_PREFIX="/quant/${APP_ENV}"
UPLOAD_SSM=false
CHECK_SSM=false

for arg in "$@"; do
  case "$arg" in
    --upload-ssm) UPLOAD_SSM=true ;;
    --check-ssm) CHECK_SSM=true ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

log() { echo "[cloudflare-origin-cert] $*"; }
die() { echo "[cloudflare-origin-cert] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null || die "$1 is required"
}

auth_header() {
  if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    echo "Bearer ${CLOUDFLARE_API_TOKEN}"
  elif [[ -n "${CLOUDFLARE_ORIGIN_CA_KEY:-}" ]]; then
    echo "Bearer ${CLOUDFLARE_ORIGIN_CA_KEY}"
  else
    die "Set CLOUDFLARE_API_TOKEN (Zone SSL and Certificates Edit) or CLOUDFLARE_ORIGIN_CA_KEY"
  fi
}

check_ssm() {
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
  if [[ -n "$cert" && "$cert" != "None" && -n "$key" && "$key" != "None" ]]; then
    log "SSM OK: ${SSM_PREFIX}/ORIGIN_TLS_{CERT,KEY} present"
    return 0
  fi
  log "SSM MISSING: ${SSM_PREFIX}/ORIGIN_TLS_CERT and/or ORIGIN_TLS_KEY"
  return 1
}

upload_to_ssm() {
  local cert_file="$1" key_file="$2"
  [[ -f "$cert_file" && -f "$key_file" ]] || die "cert/key files missing for SSM upload"

  log "Uploading certificate to ${SSM_PREFIX}/ORIGIN_TLS_CERT"
  aws ssm put-parameter \
    --name "${SSM_PREFIX}/ORIGIN_TLS_CERT" \
    --type String \
    --value "file://${cert_file}" \
    --region "$AWS_REGION" \
    --overwrite \
    --no-cli-pager

  log "Uploading private key to ${SSM_PREFIX}/ORIGIN_TLS_KEY (SecureString)"
  aws ssm put-parameter \
    --name "${SSM_PREFIX}/ORIGIN_TLS_KEY" \
    --type SecureString \
    --value "file://${key_file}" \
    --region "$AWS_REGION" \
    --overwrite \
    --no-cli-pager

  log "SSM upload complete"
}

request_origin_cert() {
  local tmp key csr
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  key="${tmp}/origin-key.pem"
  csr="${tmp}/origin.csr"

  log "Generating RSA-2048 private key and CSR for ${DOMAIN}, ${WILDCARD}"
  openssl genrsa -out "$key" 2048 2>/dev/null
  openssl req -new -key "$key" -out "$csr" -subj "/O=AlgoDaemon/CN=${DOMAIN}" \
    -addext "subjectAltName=DNS:${DOMAIN},DNS:${WILDCARD}"

  local payload resp http body cert_pem
  payload="$(jq -n \
    --arg csr "$(cat "$csr")" \
    --arg domain "$DOMAIN" \
    --arg wildcard "$WILDCARD" \
    --argjson validity "$VALIDITY_DAYS" \
    '{
      csr: $csr,
      hostnames: [$domain, $wildcard],
      request_type: "origin-rsa",
      requested_validity: $validity
    }')"

  body="${tmp}/response.json"
  http="$(curl -sS -w '%{http_code}' -o "$body" -X POST "${CF_API}/certificates" \
    -H "Authorization: $(auth_header)" \
    -H "Content-Type: application/json" \
    --data "$payload")"

  if [[ "$http" -lt 200 || "$http" -ge 300 ]]; then
    echo "[cloudflare-origin-cert] API POST /certificates → HTTP ${http}" >&2
    cat "$body" >&2
    die "Origin CA certificate request failed"
  fi

  if ! jq -e '.success == true' "$body" >/dev/null; then
    cat "$body" >&2
    die "Cloudflare API returned success=false"
  fi

  cert_pem="$(jq -r '.result.certificate' "$body")"
  [[ -n "$cert_pem" && "$cert_pem" != "null" ]] || die "No certificate in API response"

  mkdir -p "$OUTPUT_DIR"
  chmod 700 "$OUTPUT_DIR"
  local cert_out="${OUTPUT_DIR}/origin.pem"
  local key_out="${OUTPUT_DIR}/origin-key.pem"

  printf '%s\n' "$cert_pem" > "$cert_out"
  cp "$key" "$key_out"
  chmod 644 "$cert_out"
  chmod 600 "$key_out"

  log "Wrote ${cert_out}"
  log "Wrote ${key_out} (mode 600 — keep secret)"

  jq -r '.result | "id=\(.id) expires=\(.expires_on)"' "$body"

  if [[ "$UPLOAD_SSM" == true ]]; then
    upload_to_ssm "$cert_out" "$key_out"
    log "Local key retained at ${key_out} — delete securely when no longer needed"
  else
    log "Next: bash aws/scripts/cloudflare-origin-cert.sh --upload-ssm"
    log "  or upload manually (see docs/guides/https-cloudflare.md Step 3)"
  fi
}

main() {
  require_cmd openssl
  require_cmd curl
  require_cmd jq

  if [[ "$CHECK_SSM" == true ]]; then
    check_ssm
    exit $?
  fi

  if [[ "$UPLOAD_SSM" == true ]] && check_ssm 2>/dev/null; then
    log "SSM already has origin cert/key — skip generation (delete SSM params to re-issue)"
    exit 0
  fi

  if [[ -f "${OUTPUT_DIR}/origin.pem" && -f "${OUTPUT_DIR}/origin-key.pem" && "$UPLOAD_SSM" == true ]]; then
    log "Using existing ${OUTPUT_DIR}/origin.pem and origin-key.pem for SSM upload"
    upload_to_ssm "${OUTPUT_DIR}/origin.pem" "${OUTPUT_DIR}/origin-key.pem"
    exit 0
  fi

  request_origin_cert
}

main "$@"
