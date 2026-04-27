#!/usr/bin/env bash
# Bootstrap SSM parameters for /quant/<env>/.
# Run once per environment.  SecureString values are prompted interactively.
#
# Usage:
#   bash aws/scripts/init-ssm-params.sh          # defaults to env=prod
#   APP_ENV=dev bash aws/scripts/init-ssm-params.sh
set -euo pipefail

ENV="${APP_ENV:-prod}"
PREFIX="/quant/${ENV}"
REGION="${AWS_REGION:-ap-southeast-1}"

put() {
  local name="$1" value="$2" type="${3:-String}"
  local path="${PREFIX}/${name}"
  if aws ssm get-parameter --name "$path" --region "$REGION" >/dev/null 2>&1; then
    echo "  SKIP  $path (already exists)"
  else
    aws ssm put-parameter \
      --name "$path" \
      --value "$value" \
      --type "$type" \
      --region "$REGION" \
      --no-cli-pager
    echo "  SET   $path ($type)"
  fi
}

put_secret() {
  local name="$1" prompt="$2"
  local path="${PREFIX}/${name}"
  if aws ssm get-parameter --name "$path" --region "$REGION" >/dev/null 2>&1; then
    echo "  SKIP  $path (already exists)"
    return
  fi
  read -rsp "$prompt: " value; echo
  aws ssm put-parameter \
    --name "$path" \
    --value "$value" \
    --type SecureString \
    --region "$REGION" \
    --no-cli-pager
  echo "  SET   $path (SecureString)"
}

echo "=== Bootstrapping SSM parameters under ${PREFIX}/ ==="
echo ""

# Environment-aware defaults
if [[ "$ENV" == "dev" ]]; then
  DB_HOST="localhost"
  DB_PORT="5433"
  CORS="http://localhost:5173"
else
  DB_HOST="quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com"
  DB_PORT="5432"
  CORS="https://yourdomain.com"
fi

# Plain-text parameters
put "QUANTDB_HOST"    "$DB_HOST"
put "QUANTDB_PORT"    "$DB_PORT"
put "FUTU_HOST"       "127.0.0.1"
put "FUTU_PORT"       "11111"
put "CORS_ORIGINS"    "$CORS"

# Secrets (prompted)
put_secret "QUANTDB_USERNAME" "DB username"
put_secret "QUANTDB_PASSWORD" "DB password"
put_secret "JWT_SECRET"       "JWT secret (generate with: openssl rand -base64 32)"

echo ""
echo "Done.  Verify with:"
echo "  aws ssm get-parameters-by-path --path ${PREFIX}/ --with-decryption --region ${REGION} --output table"
