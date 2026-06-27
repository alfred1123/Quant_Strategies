#!/usr/bin/env bash
# Run Liquibase verify or deploy on prod EC2 via SSM Run Command.
#
# EC2 loads /quant/prod/* from SSM and connects to Aurora directly (port 5432).
# Laptop tunnel deploys use DB_TARGET=prod PROD_DB_PORT=5433 instead.
#
# Usage:
#   bash aws/scripts/liquibase-ssm-run.sh verify [git-ref]
#   bash aws/scripts/liquibase-ssm-run.sh deploy [git-ref]
#
# Environment:
#   AWS_REGION              (default ap-southeast-1)
#   EC2_INSTANCE_ID         optional fallback if CFN output missing
#   SSM_TIMEOUT_SECONDS     send-command timeout (default 900)
#   SSM_POLL_ATTEMPTS       poll loop count (default 90, 10s interval)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACTION="${1:?verify or deploy}"
GIT_REF="${2:-main}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
TIMEOUT="${SSM_TIMEOUT_SECONDS:-900}"
MAX_ATTEMPTS="${SSM_POLL_ATTEMPTS:-90}"

log() { echo "[liquibase-ssm] $*"; }
die() { echo "[liquibase-ssm] ERROR: $*" >&2; exit 1; }

case "$ACTION" in
  verify|deploy) ;;
  *) die "ACTION must be verify or deploy (got: $ACTION)" ;;
esac

resolve_instance_id() {
  local id
  id=$(aws cloudformation describe-stacks \
    --stack-name quant-compute \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
    --output text 2>/dev/null || true)
  if [[ -z "$id" || "$id" == "None" ]]; then
    id="${EC2_INSTANCE_ID:-}"
  fi
  [[ -n "$id" ]] || die "No EC2 instance id (quant-compute InstanceId output or EC2_INSTANCE_ID)"
  echo "$id"
}

run_liquibase_cmd() {
  local instance_id="$1"
  local liquibase_action="$2"
  local git_ref="$3"

  log "Target instance: $instance_id"
  log "Action: $liquibase_action  Git ref: $git_ref"

  local run_script
  if [[ "$liquibase_action" == "verify" ]]; then
    run_script="./scripts/liquibase-verify.sh"
  else
    run_script="./scripts/liquibase-deploy.sh"
  fi

  # JSON array for SSM — keep commands short; heredoc-style via jq.
  local commands_json
  commands_json=$(jq -n \
    --arg ref "$git_ref" \
    --arg run "$run_script" \
    '[
      "set -euo pipefail",
      "mkdir -p /opt/quant",
      "if [ ! -d /opt/quant/.git ]; then git clone https://github.com/alfred1123/Quant_Strategies.git /opt/quant; fi",
      "cd /opt/quant",
      "git config --system --add safe.directory /opt/quant",
      "echo \"── BEFORE ──\"",
      "git rev-parse --short HEAD || true",
      "git fetch --prune origin " + $ref,
      "git reset --hard FETCH_HEAD",
      "echo \"── AFTER  ──\"",
      "git rev-parse --short HEAD",
      "bash aws/scripts/install-liquibase.sh",
      "APP_ENV=prod USE_SSM=1 " + $run
    ]')

  local command_id
  command_id=$(aws ssm send-command \
    --instance-ids "$instance_id" \
    --document-name AWS-RunShellScript \
    --timeout-seconds "$TIMEOUT" \
    --parameters "commands=${commands_json}" \
    --region "$AWS_REGION" \
    --query Command.CommandId \
    --output text)

  log "SSM command id: $command_id"
  poll_ssm "$instance_id" "$command_id"
}

poll_ssm() {
  local instance_id="$1"
  local command_id="$2"
  local invocation status

  for i in $(seq 1 "$MAX_ATTEMPTS"); do
    sleep 10
    if ! invocation=$(aws ssm get-command-invocation \
      --command-id "$command_id" \
      --instance-id "$instance_id" \
      --region "$AWS_REGION" \
      --output json 2>&1); then
      if echo "$invocation" | grep -q "InvocationDoesNotExist"; then
        log "Attempt $i: invocation not yet visible"
      else
        log "Attempt $i: aws CLI error (retrying):"
        echo "$invocation" | sed 's/^/    /'
      fi
      continue
    fi

    status=$(echo "$invocation" | jq -r .Status)
    log "Attempt $i: $status"

    case "$status" in
      Success)
        log "── Succeeded ──"
        echo "$invocation" | jq -r .StandardOutputContent | tail -80
        return 0
        ;;
      Failed|TimedOut|Cancelled)
        log "── Failed: $status ──"
        echo "stdout:"
        echo "$invocation" | jq -r .StandardOutputContent | tail -80
        echo "stderr:"
        echo "$invocation" | jq -r .StandardErrorContent | tail -80
        die "SSM command $status"
        ;;
    esac
  done

  die "Timed out after $MAX_ATTEMPTS polls — command may still be running on EC2"
}

INSTANCE_ID="$(resolve_instance_id)"
run_liquibase_cmd "$INSTANCE_ID" "$ACTION" "$GIT_REF"
